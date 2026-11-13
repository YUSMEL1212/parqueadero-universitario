"""Permisos de DRF por rol, reutilizables en las vistas de todas las apps.

Uso:
    from comun.permisos import EsAdministrador, EsGuarda

    class MiVista(APIView):
        permission_classes = [EsAdministrador]

    # Varios roles a la vez: los permisos de DRF se combinan con | y &.
    permission_classes = [EsGuarda | EsAdministrador]

Si la petición no trae un token válido la respuesta es 401; si el usuario está
autenticado pero no tiene el rol, es 403.
"""
from rest_framework.permissions import BasePermission

from usuarios.models import NombreRol


class _TieneRol(BasePermission):
    rol = None
    message = 'No tienes permiso para realizar esta acción.'

    def has_permission(self, request, view):
        usuario = request.user
        if not (usuario and usuario.is_authenticated):
            return False
        return usuario.rol.nombre == self.rol


class EsAdministrador(_TieneRol):
    rol = NombreRol.ADMINISTRADOR
    message = 'Solo un administrador puede realizar esta acción.'

    def has_permission(self, request, view):
        usuario = request.user
        if usuario and usuario.is_authenticated and usuario.is_superuser:
            return True
        return super().has_permission(request, view)


class EsGuarda(_TieneRol):
    rol = NombreRol.GUARDA
    message = 'Solo un guarda puede realizar esta acción.'


class EsConductor(_TieneRol):
    rol = NombreRol.CONDUCTOR
    message = 'Solo un conductor puede realizar esta acción.'
