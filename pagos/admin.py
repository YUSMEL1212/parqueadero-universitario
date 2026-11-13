from django.contrib import admin

from .models import Mensualidad, Pago


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ('id', 'usuario', 'concepto', 'valor', 'metodo', 'estado', 'pagado_en')
    list_filter = ('concepto', 'metodo', 'estado')
    search_fields = ('referencia_pasarela', 'usuario__email', 'usuario__nombre')
    autocomplete_fields = ('usuario',)


@admin.register(Mensualidad)
class MensualidadAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'tipo_vehiculo', 'inicia_en', 'vence_en', 'pago')
    list_filter = ('tipo_vehiculo',)
    search_fields = ('usuario__email', 'usuario__nombre')
    autocomplete_fields = ('usuario', 'pago')
