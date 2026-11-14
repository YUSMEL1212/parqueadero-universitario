"""Gestión de usuarios por el administrador, montada bajo /api/ en config/urls.py.

Va aparte de usuarios/urls.py porque esas rutas cuelgan de /api/auth/.
"""
from django.urls import path

from .views import RolUsuarioView, UsuariosView, UsuarioView

app_name = 'usuarios-gestion'

# Sin barra final, como el resto de la API.
urlpatterns = [
    path('usuarios', UsuariosView.as_view(), name='lista'),
    path('usuarios/<uuid:pk>', UsuarioView.as_view(), name='detalle'),
    path('usuarios/<uuid:pk>/rol', RolUsuarioView.as_view(), name='rol'),
]
