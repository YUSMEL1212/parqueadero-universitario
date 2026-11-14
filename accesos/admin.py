"""Registro del modelo Ticket en el panel de administración de Django."""

from django.contrib import admin

from .models import Ticket


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    """Listado de tickets con filtros por tipo y método de ingreso, y búsqueda por placa,
    correo del conductor o código de salida del invitado."""

    list_display = (
        'vehiculo',
        'usuario',
        'tipo_ingreso',
        'metodo_ingreso',
        'hora_entrada',
        'hora_salida',
        'valor_cobrado',
    )
    list_filter = ('tipo_ingreso', 'metodo_ingreso')
    search_fields = ('vehiculo__placa', 'usuario__email', 'codigo_salida')
    autocomplete_fields = ('vehiculo', 'usuario', 'guarda', 'tarifa', 'pago')
    date_hierarchy = 'hora_entrada'
