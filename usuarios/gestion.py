"""Gestión de usuarios por el administrador: cambio de rol y activación.

Las vistas (usuarios/views.py) solo traducen HTTP; las reglas viven aquí.
"""
from django.db import transaction
from django.db.models import Q

from .models import NombreRol, Rol, Usuario


class CambioNoPermitido(Exception):
    """El cambio pedido rompe una regla (p. ej. un administrador quitándose su rol)."""

    def __init__(self, mensaje, codigo):
        super().__init__(mensaje)
        self.codigo = codigo


def cambiar_rol(usuario, nombre_rol, administrador):
    """Asigna el rol `nombre_rol` a `usuario` y lo devuelve.

    Un administrador no puede quitarse a sí mismo el rol de administrador: se quedaría
    sin acceso al panel y, si es el único, nadie podría devolvérselo.
    """
    if usuario.pk == administrador.pk and nombre_rol != NombreRol.ADMINISTRADOR:
        raise CambioNoPermitido(
            'No puedes quitarte a ti mismo el rol de administrador. Pídeselo a otro '
            'administrador.',
            'propio_rol',
        )
    with transaction.atomic():
        rol, _ = Rol.objects.get_or_create(nombre=nombre_rol)
        if usuario.rol_id != rol.pk:
            usuario.rol = rol
            usuario.save(update_fields=['rol'])
    return usuario


def cambiar_estado(usuario, activo, administrador):
    """Activa o desactiva la cuenta de `usuario` y lo devuelve.

    Un usuario desactivado no puede iniciar sesión y sus tokens dejan de servir (SimpleJWT
    revisa `is_active` en cada petición). Un administrador no puede desactivarse a sí
    mismo, por la misma razón que no puede quitarse el rol.
    """
    if usuario.pk == administrador.pk and not activo:
        raise CambioNoPermitido(
            'No puedes desactivar tu propia cuenta.',
            'propia_cuenta',
        )
    if usuario.activo != activo:
        usuario.activo = activo
        usuario.save(update_fields=['activo'])
    return usuario


def buscar_usuarios(texto=''):
    """Usuarios cuyo nombre o correo contiene `texto` (sin distinguir mayúsculas)."""
    usuarios = Usuario.objects.select_related('rol').order_by('nombre', 'email')
    texto = (texto or '').strip()
    if texto:
        usuarios = usuarios.filter(Q(nombre__icontains=texto) | Q(email__icontains=texto))
    return usuarios
