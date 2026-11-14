"""Configuración de la app accesos para el registro de aplicaciones de Django."""

from django.apps import AppConfig


class AccesosConfig(AppConfig):
    """Registra la app accesos (tickets, portería, QR y motor de cobro) en Django."""

    name = 'accesos'
