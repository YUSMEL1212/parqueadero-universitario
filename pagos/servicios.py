"""
Pago de mensualidades: precio, inicio del pago y aplicación de la confirmación.

Flujo:
  1. POST /api/pagos/mensualidad → `iniciar_pago_mensualidad` crea un Pago `pendiente`
     con el valor vigente de la tarifa y una referencia única, y arma la URL de pago.
  2. La pasarela (o el simulador) confirma → `recibir_evento` verifica el evento y
     llama a `aplicar_transaccion`.
  3. Aprobado → el pago queda `aprobado` y se crea la Mensualidad de 30 días desde ese
     momento. Rechazado → queda `rechazado` y no se crea nada.

`aplicar_transaccion` es idempotente: un pago que ya no está pendiente no se toca, así
que una confirmación repetida no duplica la mensualidad. La fila del pago se bloquea
(SELECT … FOR UPDATE) y además Mensualidad.pago es único en la base.
"""

import logging
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from tarifas.models import ConceptoTarifa, Tarifa

from . import wompi
from .models import DURACION_MENSUALIDAD, Mensualidad, Pago

logger = logging.getLogger(__name__)


def ahora():
    """Hora actual. Las pruebas la reemplazan."""
    return timezone.now()


class SinTarifaVigente(Exception):
    def __init__(self, tipo_vehiculo):
        super().__init__(
            f'No hay una tarifa de mensualidad vigente para {tipo_vehiculo}. '
            'El administrador debe configurarla.'
        )


class ReferenciaDesconocida(Exception):
    pass


class MontoNoCoincide(Exception):
    pass


# --- Precio -------------------------------------------------------------------------


def tarifa_mensualidad(tipo_vehiculo):
    """Tarifa de mensualidad vigente (vigente_hasta NULL) para el tipo. Regla 2 de CLAUDE.md."""
    tarifa = Tarifa.objects.filter(
        tipo_vehiculo=tipo_vehiculo,
        concepto=ConceptoTarifa.MENSUALIDAD,
        vigente_hasta__isnull=True,
    ).first()
    if tarifa is None:
        raise SinTarifaVigente(tipo_vehiculo)
    return tarifa


# --- Inicio del pago ----------------------------------------------------------------


def url_retorno_valida(url):
    """True si `url` apunta al frontend (un origen de CORS_ALLOWED_ORIGINS).

    Evita que la pasarela termine redirigiendo a un sitio ajeno (open redirect).
    """
    partes = urlsplit(url or '')
    if partes.scheme not in ('http', 'https') or not partes.netloc:
        return False
    return f'{partes.scheme}://{partes.netloc}' in settings.CORS_ALLOWED_ORIGINS


def _con_parametros(url, **parametros):
    separador = '&' if urlsplit(url).query else '?'
    return f'{url}{separador}{urlencode(parametros)}'


def iniciar_pago_mensualidad(
    usuario, tipo_vehiculo, metodo, construir_url, correo='', url_retorno='', banco=''
):
    """Crea el Pago pendiente y devuelve `(pago, url_pago)`.

    `url_retorno` es la pantalla del frontend a la que vuelve el conductor; se le agrega
    `?referencia=`. `construir_url(ruta)` convierte una ruta en URL absoluta (la vista
    pasa request.build_absolute_uri) para la página del simulador. `banco` (PSE) solo
    se muestra en el simulador: en el checkout de Wompi el banco se elige allí.
    """
    tarifa = tarifa_mensualidad(tipo_vehiculo)
    pago = Pago.objects.create(
        usuario=usuario,
        concepto=Pago.Concepto.MENSUALIDAD,
        valor=tarifa.valor,
        metodo=metodo,
        estado=Pago.Estado.PENDIENTE,
        referencia_pasarela=wompi.nueva_referencia(),
        tipo_vehiculo=tipo_vehiculo,
    )
    retorno = (
        _con_parametros(url_retorno, referencia=pago.referencia_pasarela) if url_retorno else ''
    )
    if wompi.en_simulacion():
        ruta = f'/api/pagos/simulacion/{pago.referencia_pasarela}'
        datos = {'banco': banco, 'correo': correo, 'volver': retorno}
        parametros = {k: v for k, v in datos.items() if v}
        url = construir_url(_con_parametros(ruta, **parametros) if parametros else ruta)
    else:
        url = wompi.url_checkout(pago.referencia_pasarela, pago.valor * 100, correo, retorno)
    return pago, url


# --- Confirmación -------------------------------------------------------------------


def aplicar_transaccion(referencia, estado, monto_centavos, transaccion_id, moneda=wompi.MONEDA):
    """Aplica el resultado de la pasarela al pago con esa referencia.

    Devuelve `(pago, cambio)`; `cambio` es False si el pago ya estaba resuelto o la
    transacción sigue pendiente. Lanza ReferenciaDesconocida o MontoNoCoincide.
    """
    momento = ahora()
    with transaction.atomic():
        pago = (
            Pago.objects.select_for_update()
            .filter(referencia_pasarela=referencia, concepto=Pago.Concepto.MENSUALIDAD)
            .first()
        )
        if pago is None:
            raise ReferenciaDesconocida(referencia)
        if pago.estado != Pago.Estado.PENDIENTE or estado == wompi.PENDIENTE:
            return pago, False

        if estado == wompi.APROBADA:
            if int(monto_centavos) != pago.valor * 100 or moneda != wompi.MONEDA:
                logger.error(
                    'Pago %s aprobado por %s %s, se esperaban %s COP',
                    referencia, monto_centavos, moneda, pago.valor * 100,
                )
                raise MontoNoCoincide(referencia)
            pago.estado = Pago.Estado.APROBADO
            pago.pagado_en = momento
            pago.transaccion_pasarela = transaccion_id
            pago.save(update_fields=['estado', 'pagado_en', 'transaccion_pasarela'])
            # Activa de inmediato: 30 días desde la aprobación.
            Mensualidad.objects.create(
                usuario=pago.usuario,
                pago=pago,
                tipo_vehiculo=pago.tipo_vehiculo,
                inicia_en=momento,
                vence_en=momento + DURACION_MENSUALIDAD,
            )
        elif estado in wompi.ESTADOS_RECHAZO:
            pago.estado = Pago.Estado.RECHAZADO
            pago.transaccion_pasarela = transaccion_id
            pago.save(update_fields=['estado', 'transaccion_pasarela'])
        else:
            logger.warning('Estado de Wompi desconocido %r para %s', estado, referencia)
            return pago, False
    return pago, True


def _aplicar_datos_de_wompi(datos):
    return aplicar_transaccion(
        referencia=datos['reference'],
        estado=datos['status'],
        monto_centavos=datos['amount_in_cents'],
        transaccion_id=datos['id'],
        moneda=datos.get('currency', wompi.MONEDA),
    )


def recibir_evento(evento):
    """Procesa un evento del webhook. Devuelve `(pago | None, cambio)`.

    En modo Wompi no se confía en el cuerpo: se consulta la transacción en la API con la
    llave privada. En modo simulación se verifica la firma del evento.
    """
    if not isinstance(evento, dict) or evento.get('event') != 'transaction.updated':
        return None, False
    if wompi.en_simulacion():
        datos = wompi.verificar_evento_simulado(evento)
    else:
        try:
            transaccion_id = evento['data']['transaction']['id']
        except (KeyError, TypeError):
            return None, False
        datos = wompi.consultar_transaccion(transaccion_id)
    return _aplicar_datos_de_wompi(datos)


def sincronizar_con_wompi(pago, transaccion_id):
    """Si el pago sigue pendiente, consulta la transacción en Wompi y la aplica.

    Sirve cuando el webhook no llega (p. ej. el backend corre en localhost): el conductor
    vuelve del checkout con `?id=` y la pantalla de pago consulta el estado.
    """
    if pago.estado != Pago.Estado.PENDIENTE or wompi.en_simulacion() or not transaccion_id:
        return pago
    datos = wompi.consultar_transaccion(transaccion_id)
    if datos.get('reference') != pago.referencia_pasarela:
        return pago
    pago, _ = _aplicar_datos_de_wompi(datos)
    return pago
