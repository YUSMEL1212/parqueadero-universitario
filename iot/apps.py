from django.apps import AppConfig


class IotConfig(AppConfig):
    name = 'iot'

    def ready(self):
        from . import signals  # noqa: F401  (registra los receptores)
