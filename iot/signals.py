"""Señales de IoT: cualquier guardado que cambie una bahía emite el conteo por ws/cupos.

Es el único lugar que emite cuando cambia una bahía, venga del endpoint de sensores, del
admin de Django o de cualquier otro `save()`. Así el endpoint IoT no emite por su cuenta
y el mensaje nunca sale duplicado.

`QuerySet.update()` no dispara señales: lo que cambie bahías por esa vía no emite.
"""

from django.db import transaction
from django.db.models.signals import post_init, post_save
from django.dispatch import receiver

from .models import Bahia

# Campos que cambian el conteo de cupos libres por tipo.
CAMPOS_CUPOS = ('estado', 'tipo_vehiculo')


def _valores_cupos(instancia):
    # Se lee de __dict__ para no disparar una consulta si el campo vino diferido (.only()).
    return {campo: instancia.__dict__.get(campo) for campo in CAMPOS_CUPOS}


@receiver(post_init, sender=Bahia)
def recordar_valores_originales(sender, instance, **kwargs):
    instance._valores_cupos_originales = _valores_cupos(instance)


@receiver(post_save, sender=Bahia)
def emitir_cupos_si_cambio(sender, instance, created, update_fields, raw, **kwargs):
    if raw:  # loaddata: no hay clientes que avisar
        return
    originales = instance._valores_cupos_originales
    actuales = _valores_cupos(instance)
    instance._valores_cupos_originales = actuales  # un segundo save() sin cambios no emite

    if created:
        return
    campos = CAMPOS_CUPOS if update_fields is None else set(CAMPOS_CUPOS) & set(update_fields)
    if not any(originales[c] != actuales[c] for c in campos):
        return

    from .servicios import emitir_cupos  # servicios importa modelos de otras apps

    # Se emite al confirmar la transacción, para que el conteo ya vea el cambio.
    # robust=True: si la capa de canales falla, se registra en el log y el guardado
    # (o la respuesta al sensor) no se ve afectado.
    transaction.on_commit(emitir_cupos, robust=True)
