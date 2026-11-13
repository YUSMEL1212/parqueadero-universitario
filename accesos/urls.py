from django.urls import path

from .views import (
    ConfirmarSalidaView,
    EntradaView,
    HistorialView,
    InvitadoView,
    QRView,
    SalidaView,
)

app_name = 'accesos'

# Sin barra final, igual que /api/auth/... y /api/vehiculos
urlpatterns = [
    path('accesos/qr', QRView.as_view(), name='qr'),
    path('accesos/entrada', EntradaView.as_view(), name='entrada'),
    path('accesos/salida', SalidaView.as_view(), name='salida'),
    path('accesos/salida/confirmar', ConfirmarSalidaView.as_view(), name='salida-confirmar'),
    path('accesos/invitados', InvitadoView.as_view(), name='invitados'),
    path('accesos/historial', HistorialView.as_view(), name='historial'),
]
