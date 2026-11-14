from django.urls import path

from .views import MensualidadesVigentesView

app_name = 'pagos'

# Sin barra final, como el resto de la API.
urlpatterns = [
    path('mensualidades/vigentes', MensualidadesVigentesView.as_view(), name='mensualidades-vigentes'),
]
