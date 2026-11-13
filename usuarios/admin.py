from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from .models import Rol, Usuario


class UsuarioCreationForm(AdminUserCreationForm):
    class Meta:
        model = Usuario
        fields = ('email', 'nombre', 'rol')


class UsuarioChangeForm(UserChangeForm):
    class Meta:
        model = Usuario
        fields = '__all__'


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre')


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    form = UsuarioChangeForm
    add_form = UsuarioCreationForm

    list_display = ('email', 'nombre', 'rol', 'tipo_conductor', 'activo', 'creado_en')
    list_filter = ('rol', 'tipo_conductor', 'activo', 'is_superuser')
    search_fields = ('email', 'nombre', 'telefono')
    ordering = ('email',)
    readonly_fields = ('creado_en', 'last_login')
    filter_horizontal = ('groups', 'user_permissions')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Datos personales', {'fields': ('nombre', 'telefono', 'rol', 'tipo_conductor')}),
        ('Permisos', {'fields': ('activo', 'is_superuser', 'groups', 'user_permissions')}),
        ('Fechas', {'fields': ('last_login', 'creado_en')}),
    )
    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': (
                    'email',
                    'nombre',
                    'rol',
                    'usable_password',
                    'password1',
                    'password2',
                ),
            },
        ),
    )
