from django.urls import path

from .views import HistorialTarifasView, TarifasView

app_name = 'tarifas'

# Sin barra final, igual que el resto de la API.
urlpatterns = [
    path('tarifas', TarifasView.as_view(), name='tarifas'),
    path('tarifas/historial', HistorialTarifasView.as_view(), name='historial'),
]
