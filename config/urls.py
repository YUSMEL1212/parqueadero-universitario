"""Rutas principales del proyecto."""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),
    # Autenticación: registro, login/refresh JWT y perfil
    path('api/auth/', include('usuarios.urls')),
    # Vehículos del conductor autenticado (el administrador ve todos)
    path('api/', include('vehiculos.urls')),
    # Documentación OpenAPI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
