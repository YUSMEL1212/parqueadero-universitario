from django.contrib import admin

from .models import Vehiculo


@admin.register(Vehiculo)
class VehiculoAdmin(admin.ModelAdmin):
    list_display = ('placa', 'tipo', 'usuario', 'activo', 'creado_en')
    list_filter = ('tipo', 'activo')
    search_fields = ('placa', 'usuario__email', 'usuario__nombre')
    autocomplete_fields = ('usuario',)
