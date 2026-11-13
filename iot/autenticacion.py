"""Autenticación de dispositivos (sensores ESP32 y cámara LPR) por llave compartida.

Los dispositivos no tienen usuario ni JWT: envían la llave de `IOT_DEVICE_KEY` en la
cabecera `X-Device-Key` (CLAUDE.md, "Contrato de mensajes IoT").

Uso en una vista:
    authentication_classes = [LlaveDispositivo]
    permission_classes = [EsDispositivo]

Sin cabecera o con una llave equivocada la respuesta es 401.
"""

import hmac

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

CABECERA = 'X-Device-Key'


class Dispositivo:
    """Marca que queda en `request.auth` cuando la llave es válida."""

    def __repr__(self):
        return '<Dispositivo IoT>'


class LlaveDispositivo(BaseAuthentication):
    def authenticate(self, request):
        llave = request.headers.get(CABECERA)
        if llave is None:
            return None  # EsDispositivo responde 401 (NotAuthenticated)
        esperada = settings.IOT_DEVICE_KEY
        # Sin llave configurada no se acepta ninguna; compare_digest evita ataques de tiempo.
        if not esperada or not hmac.compare_digest(llave.encode(), esperada.encode()):
            raise AuthenticationFailed('Llave de dispositivo inválida.')
        return AnonymousUser(), Dispositivo()

    def authenticate_header(self, request):
        # Hace que DRF responda 401 (y no 403) cuando falta la llave.
        return CABECERA


class EsDispositivo(BasePermission):
    message = f'Falta la cabecera {CABECERA}.'

    def has_permission(self, request, view):
        return isinstance(request.auth, Dispositivo)


class LlaveDispositivoEsquema(OpenApiAuthenticationExtension):
    """Muestra la llave en /api/docs (botón Authorize) como apiKey en cabecera."""

    target_class = LlaveDispositivo
    name = 'LlaveDispositivo'

    def get_security_definition(self, auto_schema):
        return {'type': 'apiKey', 'in': 'header', 'name': CABECERA}
