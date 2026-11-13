from django.urls import re_path

from .consumers import CuposConsumer

websocket_urlpatterns = [
    re_path(r'^ws/cupos/?$', CuposConsumer.as_asgi()),
]
