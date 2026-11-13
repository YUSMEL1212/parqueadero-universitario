"""
Token del QR dinámico (CLAUDE.md, "Reglas de negocio").

El token se cifra con AES-256-GCM, contiene usuario, vehículo, placa y vencimiento, y
vence a los 60 segundos. GCM cifra y autentica a la vez: si alguien cambia un solo byte
del token, el descifrado falla y el servidor lo rechaza.

Formato del token (texto apto para un QR):

    base64url_sin_relleno( nonce[12 bytes] || texto_cifrado || etiqueta_gcm[16 bytes] )

El texto plano es un JSON compacto:

    {"u": "<id usuario>", "v": "<id vehículo>", "p": "<placa>", "iat": 1794000000, "exp": 1794000060}

La llave (32 bytes) sale de la variable de entorno QR_SECRET_KEY, codificada en base64.
Para generar una:

    python -c "import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
"""

import base64
import binascii
import json
import os
from datetime import datetime, timezone as dt_timezone

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

VIGENCIA_SEGUNDOS = 60
TAMANO_NONCE = 12
TAMANO_ETIQUETA = 16
TAMANO_LLAVE = 32  # AES-256
CAMPOS = ('u', 'v', 'p', 'iat', 'exp')


class TokenQRError(Exception):
    """Base de los errores del token QR. Capture esta si no importa el motivo."""


class TokenQRVencido(TokenQRError):
    """El token es auténtico pero ya pasó su vencimiento (60 segundos)."""

    def __init__(self, vencio_en):
        self.vencio_en = vencio_en
        super().__init__(f'El código QR venció el {vencio_en.isoformat()}. Genere uno nuevo.')


class TokenQRAlterado(TokenQRError):
    """La etiqueta GCM no coincide: el token fue modificado o no se generó con esta llave.

    AES-GCM no distingue entre un byte cambiado y una llave distinta; en los dos casos
    el token no es de confianza y se rechaza igual.
    """

    def __init__(self):
        super().__init__('El código QR fue alterado o no lo generó este servidor.')


class TokenQRIlegible(TokenQRError):
    """El token no tiene el formato esperado y no se puede descifrar."""

    def __init__(self, detalle):
        super().__init__(f'El código QR no se puede descifrar: {detalle}.')


def ahora():
    """Hora actual. Las pruebas la reemplazan para simular el paso del tiempo."""
    return timezone.now()


def _llave():
    valor = getattr(settings, 'QR_SECRET_KEY', '') or ''
    if not valor:
        raise ImproperlyConfigured('Falta QR_SECRET_KEY en el entorno (.env).')
    try:
        llave = base64.urlsafe_b64decode(valor + '=' * (-len(valor) % 4))
    except (binascii.Error, ValueError) as exc:
        raise ImproperlyConfigured('QR_SECRET_KEY no es base64 válido.') from exc
    if len(llave) != TAMANO_LLAVE:
        raise ImproperlyConfigured(
            f'QR_SECRET_KEY debe tener {TAMANO_LLAVE} bytes (AES-256); tiene {len(llave)}.'
        )
    return llave


def _a_base64(datos):
    return base64.urlsafe_b64encode(datos).rstrip(b'=').decode('ascii')


def _de_base64(texto):
    texto = texto.strip()
    return base64.b64decode(texto + '=' * (-len(texto) % 4), altchars=b'-_', validate=True)


def generar_token(usuario, vehiculo) -> str:
    """Cifra un token QR para `vehiculo` de `usuario`, válido por 60 segundos.

    Lanza ValueError si el vehículo no es del usuario o está inactivo.
    """
    if vehiculo.usuario_id != usuario.pk:
        raise ValueError('El vehículo no pertenece a este usuario.')
    if not vehiculo.activo:
        raise ValueError('El vehículo está inactivo.')

    emitido = int(ahora().timestamp())
    contenido = {
        'u': str(usuario.pk),
        'v': str(vehiculo.pk),
        'p': vehiculo.placa,
        'iat': emitido,
        'exp': emitido + VIGENCIA_SEGUNDOS,
    }
    texto_plano = json.dumps(contenido, separators=(',', ':')).encode('utf-8')
    nonce = os.urandom(TAMANO_NONCE)  # nunca se repite un nonce con la misma llave
    cifrado = AESGCM(_llave()).encrypt(nonce, texto_plano, None)
    return _a_base64(nonce + cifrado)


def validar_token(token) -> dict:
    """Descifra y valida un token QR.

    Devuelve un dict con:
      - usuario_id, vehiculo_id: str (UUID)
      - placa: str
      - emitido_en, vence_en: datetime con zona horaria (UTC)

    Lanza:
      - TokenQRIlegible si el texto no es un token con el formato esperado.
      - TokenQRAlterado si la autenticación GCM falla (byte cambiado u otra llave).
      - TokenQRVencido si es auténtico pero ya venció.
    Todas heredan de TokenQRError.
    """
    if not isinstance(token, str) or not token.strip():
        raise TokenQRIlegible('el token está vacío')
    try:
        crudo = _de_base64(token)
    except (binascii.Error, ValueError):
        raise TokenQRIlegible('no es base64url válido') from None
    if len(crudo) <= TAMANO_NONCE + TAMANO_ETIQUETA:
        raise TokenQRIlegible('el token es demasiado corto')

    nonce, cifrado = crudo[:TAMANO_NONCE], crudo[TAMANO_NONCE:]
    try:
        texto_plano = AESGCM(_llave()).decrypt(nonce, cifrado, None)
    except InvalidTag:
        raise TokenQRAlterado() from None

    # Desde aquí el contenido es auténtico (lo cifró este servidor), pero se valida
    # igual por si cambia el formato entre versiones.
    try:
        contenido = json.loads(texto_plano)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TokenQRIlegible('el contenido no es JSON') from None
    if not isinstance(contenido, dict) or any(c not in contenido for c in CAMPOS):
        raise TokenQRIlegible('faltan campos en el contenido')
    if not isinstance(contenido['exp'], int) or not isinstance(contenido['iat'], int):
        raise TokenQRIlegible('el vencimiento no es válido')

    vence_en = datetime.fromtimestamp(contenido['exp'], tz=dt_timezone.utc)
    if ahora() >= vence_en:
        raise TokenQRVencido(vence_en)

    return {
        'usuario_id': contenido['u'],
        'vehiculo_id': contenido['v'],
        'placa': contenido['p'],
        'emitido_en': datetime.fromtimestamp(contenido['iat'], tz=dt_timezone.utc),
        'vence_en': vence_en,
    }


def segundos_restantes(vence_en):
    """Segundos enteros que le quedan a un token (0 si ya venció)."""
    return max(0, int((vence_en - ahora()).total_seconds()))
