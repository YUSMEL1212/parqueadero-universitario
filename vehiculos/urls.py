from rest_framework.routers import SimpleRouter

from .views import VehiculoViewSet

app_name = 'vehiculos'

# Sin barra final, igual que /api/auth/...: /api/vehiculos y /api/vehiculos/{id}
router = SimpleRouter(trailing_slash=False)
router.register('vehiculos', VehiculoViewSet, basename='vehiculo')

urlpatterns = router.urls
