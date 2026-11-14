"""Cambio de tarifas con historial (CLAUDE.md, regla 2).

Una tarifa nunca se edita: cambiar un valor cierra la vigencia de la fila actual
(`vigente_hasta = ahora`) y crea una fila nueva con `vigente_desde = ahora`. Así los
tickets cobrados antes siguen apuntando (por `tarifa_id`) a la fila con el valor viejo.
"""
from django.db import transaction
from django.utils import timezone

from .models import Tarifa


def ahora():
    return timezone.now()


def tarifas_vigentes():
    return Tarifa.objects.filter(vigente_hasta__isnull=True).order_by(
        'tipo_vehiculo', 'concepto'
    )


def actualizar_tarifas(valores, administrador):
    """Aplica los valores nuevos y devuelve la lista de filas creadas.

    `valores` es `{tipo_vehiculo: {concepto: valor}}`. Un valor igual al vigente no
    crea fila. Si no existía tarifa vigente para un tipo y concepto, se crea sin
    cerrar nada. Todo ocurre en una sola transacción: o se aplican todos los
    cambios o ninguno.

    Las filas vigentes se bloquean con SELECT ... FOR UPDATE para que dos
    administradores no cierren la misma fila a la vez; si aun así chocan, la
    restricción única de la base lanza IntegrityError y la transacción se revierte.
    """
    momento = ahora()
    creadas = []
    with transaction.atomic():
        vigentes = {
            (t.tipo_vehiculo, t.concepto): t
            for t in Tarifa.objects.select_for_update().filter(vigente_hasta__isnull=True)
        }
        for tipo_vehiculo, conceptos in valores.items():
            for concepto, valor in conceptos.items():
                anterior = vigentes.get((tipo_vehiculo, concepto))
                if anterior is not None:
                    if anterior.valor == valor:
                        continue
                    # Primero se cierra la anterior: la restricción única parcial
                    # no admite dos filas vigentes ni por un instante.
                    anterior.vigente_hasta = momento
                    anterior.save(update_fields=['vigente_hasta'])
                creadas.append(
                    Tarifa.objects.create(
                        tipo_vehiculo=tipo_vehiculo,
                        concepto=concepto,
                        valor=valor,
                        vigente_desde=momento,
                        creado_por=administrador,
                    )
                )
    return creadas
