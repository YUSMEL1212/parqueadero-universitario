from django.urls import path

from .views import (
    BancosPSEView,
    EstadoPagoView,
    MensualidadesVigentesView,
    PagoMensualidadView,
    PrecioMensualidadView,
    WebhookView,
    simulador_pasarela,
)

app_name = 'pagos'

# Sin barra final, como el resto de la API.
urlpatterns = [
    path('mensualidades/vigentes', MensualidadesVigentesView.as_view(), name='mensualidades-vigentes'),
    path('pagos/mensualidad/precio', PrecioMensualidadView.as_view(), name='precio-mensualidad'),
    path('pagos/mensualidad', PagoMensualidadView.as_view(), name='pago-mensualidad'),
    path('pagos/mensualidad/<str:referencia>', EstadoPagoView.as_view(), name='estado-pago'),
    path('pagos/pse/bancos', BancosPSEView.as_view(), name='bancos-pse'),
    path('pagos/webhook', WebhookView.as_view(), name='webhook'),
    path('pagos/simulacion/<str:referencia>', simulador_pasarela, name='simulador'),
]
