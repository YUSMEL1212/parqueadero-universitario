from django.urls import path

from .views import CuposView, LecturaLPRView, ReporteSensoresView, SensorEstadoView

app_name = 'iot'

# Rutas fijas del contrato IoT (CLAUDE.md). Sin barra final, como el resto de la API.
urlpatterns = [
    path('iot/sensores/estado', SensorEstadoView.as_view(), name='sensor-estado'),
    path('iot/sensores', ReporteSensoresView.as_view(), name='sensores'),
    path('iot/cupos', CuposView.as_view(), name='cupos'),
    path('lpr/lecturas', LecturaLPRView.as_view(), name='lpr-lecturas'),
]
