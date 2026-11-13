"""
Configuración ASGI: HTTP lo atiende Django y WebSocket lo enruta Channels.

Desarrollo: `python manage.py runserver` (daphne lo sirve todo en el mismo puerto).
Producción: `daphne config.asgi:application`.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Se inicializa Django antes de importar consumers (que importan modelos).
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from iot.routing import websocket_urlpatterns  # noqa: E402

# Sin AllowedHostsOriginValidator a propósito: ws/cupos es público, de solo lectura y no
# usa cookies, y la PWA puede servirse desde otro dominio que la API.
application = ProtocolTypeRouter(
    {
        'http': django_asgi_app,
        'websocket': URLRouter(websocket_urlpatterns),
    }
)
