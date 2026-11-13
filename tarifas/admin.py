from django.contrib import admin

from .models import Tarifa


@admin.register(Tarifa)
class TarifaAdmin(admin.ModelAdmin):
    list_display = (
        'tipo_vehiculo',
        'concepto',
        'valor',
        'vigente_desde',
        'vigente_hasta',
        'creado_por',
    )
    list_filter = ('tipo_vehiculo', 'concepto')
    search_fields = ('tipo_vehiculo', 'concepto')
    autocomplete_fields = ('creado_por',)
