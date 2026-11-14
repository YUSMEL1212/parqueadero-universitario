"""Rutas principales del proyecto."""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),
    # Autenticación: registro, login/refresh JWT y perfil
    path('api/auth/', include('usuarios.urls')),
    # Gestión de usuarios: lista, rol y activación (administrador)
    path('api/', include('usuarios.urls_gestion')),
    # Vehículos del conductor autenticado (el administrador ve todos)
    path('api/', include('vehiculos.urls')),
    # Tarifas vigentes (cualquier autenticado), historial y cambio (administrador)
    path('api/', include('tarifas.urls')),
    # Accesos: QR del conductor, portería (entrada, salida, invitados), historial y
    # reporte de ingresos por día (administrador)
    path('api/', include('accesos.urls')),
    # IoT: sensores, cámara LPR (llave de dispositivo), cupos y reporte de sensores.
    # El WebSocket ws/cupos se enruta en config/asgi.py.
    path('api/', include('iot.urls')),
    # Pagos: mensualidades vigentes, precio, pago con Wompi (o simulado) y webhook
    path('api/', include('pagos.urls')),
    # Documentación OpenAPI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
