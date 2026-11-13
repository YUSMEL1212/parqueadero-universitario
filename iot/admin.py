from django.contrib import admin

from .models import Bahia, EventoSensor, LecturaLPR, Sensor


@admin.register(Bahia)
class BahiaAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'tipo_vehiculo', 'estado', 'actualizado_en')
    list_filter = ('tipo_vehiculo', 'estado')
    search_fields = ('codigo',)


@admin.register(Sensor)
class SensorAdmin(admin.ModelAdmin):
    list_display = ('device_uid', 'bahia', 'estado', 'ultimo_pulso')
    list_filter = ('estado',)
    search_fields = ('device_uid', 'bahia__codigo')


@admin.register(EventoSensor)
class EventoSensorAdmin(admin.ModelAdmin):
    list_display = ('sensor', 'ocupado', 'distancia_cm', 'recibido_en')
    list_filter = ('ocupado',)
    search_fields = ('sensor__device_uid',)
    date_hierarchy = 'recibido_en'


@admin.register(LecturaLPR)
class LecturaLPRAdmin(admin.ModelAdmin):
    list_display = ('placa_leida', 'confianza', 'resultado', 'ticket', 'leido_en')
    list_filter = ('resultado',)
    search_fields = ('placa_leida',)
    date_hierarchy = 'leido_en'
