"""
Integración con la pasarela Wompi (Web Checkout y consulta de transacciones).

Dos modos, según el .env:
  - Wompi: con WOMPI_PUBLIC_KEY y WOMPI_PRIVATE_KEY. El conductor paga en el checkout de
    Wompi; la confirmación llega a POST /api/pagos/webhook y se verifica consultando la
    transacción en la API de Wompi con la llave privada (no se confía en el cuerpo).
  - Simulación: sin llaves. El checkout es una página interna (/api/pagos/simulacion/…)
    que arma un evento con el mismo formato de Wompi, firmado con un secreto derivado de
    SECRET_KEY, y lo pasa por el mismo procesamiento del webhook.

La configuración se lee en cada llamada (no al importar) para que las pruebas puedan
cambiarla con override_settings.
"""

import hashlib
import hmac
import json
import logging
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)

MONEDA = 'COP'
URL_CHECKOUT = 'https://checkout.wompi.co/p/'
API_SANDBOX = 'https://sandbox.wompi.co/v1'
API_PRODUCCION = 'https://production.wompi.co/v1'
TIEMPO_ESPERA = 10  # segundos

# Estados de una transacción en Wompi.
APROBADA = 'APPROVED'
PENDIENTE = 'PENDING'
ESTADOS_RECHAZO = {'DECLINED', 'VOIDED', 'ERROR'}

# Propiedades firmadas en un evento, igual que los eventos reales de Wompi.
PROPIEDADES_FIRMA = ['transaction.id', 'transaction.status', 'transaction.amount_in_cents']

# Bancos del modo simulación (en modo Wompi la lista viene de su API).
BANCOS_SIMULACION = [
    {'codigo': '1007', 'nombre': 'Bancolombia'},
    {'codigo': '1001', 'nombre': 'Banco de Bogotá'},
    {'codigo': '1051', 'nombre': 'Davivienda'},
    {'codigo': '1013', 'nombre': 'BBVA Colombia'},
    {'codigo': '1023', 'nombre': 'Banco de Occidente'},
    {'codigo': '1507', 'nombre': 'Nequi'},
]


class PasarelaNoDisponible(Exception):
    """Wompi no respondió o respondió con error; la operación se puede reintentar."""


class PasarelaMalConfigurada(Exception):
    """Hay llaves de Wompi pero falta algo para operar (p. ej. el secreto de integridad)."""


class FirmaInvalida(Exception):
    """El evento no trae una firma válida del modo simulación."""


# --- Configuración ------------------------------------------------------------------


def en_simulacion():
    """True si no hay llaves de Wompi configuradas."""
    return not (settings.WOMPI_PUBLIC_KEY and settings.WOMPI_PRIVATE_KEY)


def modo():
    return 'simulacion' if en_simulacion() else 'wompi'


def _url_api():
    return API_SANDBOX if settings.WOMPI_SANDBOX else API_PRODUCCION


# --- Checkout -----------------------------------------------------------------------


def nueva_referencia():
    """Referencia única del pago: es lo que Wompi devuelve en su confirmación."""
    return f'MEN-{uuid.uuid4().hex.upper()}'


def firma_integridad(referencia, monto_centavos, secreto):
    """Firma que exige el Web Checkout: SHA-256 de referencia + monto + moneda + secreto."""
    cadena = f'{referencia}{monto_centavos}{MONEDA}{secreto}'
    return hashlib.sha256(cadena.encode()).hexdigest()


def url_checkout(referencia, monto_centavos, correo, url_retorno):
    """URL del Web Checkout de Wompi para pagar `monto_centavos` con esa referencia."""
    secreto = settings.WOMPI_INTEGRITY_SECRET
    if not secreto:
        raise PasarelaMalConfigurada(
            'Falta WOMPI_INTEGRITY_SECRET en el .env: Wompi lo exige para firmar el pago.'
        )
    parametros = {
        'public-key': settings.WOMPI_PUBLIC_KEY,
        'currency': MONEDA,
        'amount-in-cents': monto_centavos,
        'reference': referencia,
        'signature:integrity': firma_integridad(referencia, monto_centavos, secreto),
    }
    if correo:
        parametros['customer-data:email'] = correo
    if url_retorno:
        parametros['redirect-url'] = url_retorno
    return f'{URL_CHECKOUT}?{urlencode(parametros)}'


# --- API de Wompi -------------------------------------------------------------------


def _get(ruta, llave):
    peticion = Request(
        f'{_url_api()}{ruta}',
        headers={'Authorization': f'Bearer {llave}', 'Accept': 'application/json'},
    )
    try:
        with urlopen(peticion, timeout=TIEMPO_ESPERA) as respuesta:
            return json.load(respuesta)['data']
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError) as exc:
        logger.warning('Wompi GET %s falló: %s', ruta, exc)
        raise PasarelaNoDisponible('No fue posible consultar la pasarela de pagos.') from exc


def consultar_transaccion(transaccion_id):
    """La transacción tal como la tiene Wompi: id, reference, status, amount_in_cents…"""
    return _get(f'/transactions/{transaccion_id}', settings.WOMPI_PRIVATE_KEY)


def bancos_pse():
    """Bancos disponibles para PSE: [{codigo, nombre}]."""
    if en_simulacion():
        return BANCOS_SIMULACION
    datos = _get('/pse/financial_institutions', settings.WOMPI_PUBLIC_KEY)
    return [
        {'codigo': b['financial_institution_code'], 'nombre': b['financial_institution_name']}
        for b in datos
    ]


# --- Eventos del modo simulación ----------------------------------------------------


def _secreto_simulacion():
    return hmac.new(
        settings.SECRET_KEY.encode(), b'pagos.wompi.simulacion', hashlib.sha256
    ).hexdigest()


def _valor_propiedad(transaccion, propiedad):
    return str(transaccion[propiedad.removeprefix('transaction.')])


def _checksum(transaccion, propiedades, timestamp):
    """Igual que Wompi: SHA-256 de los valores firmados + timestamp + secreto."""
    cadena = ''.join(_valor_propiedad(transaccion, p) for p in propiedades)
    cadena += f'{timestamp}{_secreto_simulacion()}'
    return hashlib.sha256(cadena.encode()).hexdigest()


def evento_simulado(referencia, monto_centavos, aprobado, correo=''):
    """Evento `transaction.updated` con el formato de Wompi, firmado para el simulador."""
    timestamp = int(time.time())
    transaccion = {
        'id': f'SIM-{uuid.uuid4().hex[:16].upper()}',
        'reference': referencia,
        'amount_in_cents': monto_centavos,
        'currency': MONEDA,
        'status': APROBADA if aprobado else 'DECLINED',
        'customer_email': correo,
        'payment_method_type': 'SIMULACION',
    }
    return {
        'event': 'transaction.updated',
        'data': {'transaction': transaccion},
        'environment': 'simulacion',
        'signature': {
            'properties': PROPIEDADES_FIRMA,
            'checksum': _checksum(transaccion, PROPIEDADES_FIRMA, timestamp),
        },
        'timestamp': timestamp,
    }


def verificar_evento_simulado(evento):
    """Devuelve la transacción del evento si la firma es válida; si no, FirmaInvalida."""
    try:
        transaccion = evento['data']['transaction']
        firma = evento['signature']
        esperado = _checksum(transaccion, firma['properties'], evento['timestamp'])
        valido = set(firma['properties']) >= set(PROPIEDADES_FIRMA) and hmac.compare_digest(
            esperado, str(firma['checksum'])
        )
    except (KeyError, TypeError):
        valido = False
    if not valido:
        raise FirmaInvalida('La firma del evento no es válida.')
    return transaccion
