"""
Motor de cálculo de cobro (CLAUDE.md, "Reglas de negocio" > "Motor de cobro").

`calcular_cobro` no depende de vistas, requests ni del modelo Ticket: recibe las horas,
el tipo de vehículo y (opcionalmente) el usuario, y devuelve qué cobrar. Solo consulta
la base para leer mensualidades y la tarifa vigente; no escribe nada.

Las tarifas nunca van en el código: se leen de la tabla `tarifas` (fila con
`vigente_hasta` NULL).
"""

import math

from pagos.models import Mensualidad
from tarifas.models import ConceptoTarifa, Tarifa

# Límite de la tarifa corta: hasta este número de minutos (inclusive) aplica hasta_2h.
# Es una regla de negocio, no un valor de tarifa.
LIMITE_MINUTOS_HASTA_2H = 120

MOTIVO_MENSUALIDAD_ACTIVA = 'mensualidad_activa'


class TarifaNoVigenteError(Exception):
    """No hay una tarifa vigente (vigente_hasta NULL) para el tipo y concepto pedidos."""

    def __init__(self, tipo_vehiculo, concepto):
        self.tipo_vehiculo = tipo_vehiculo
        self.concepto = concepto
        super().__init__(
            f'No hay tarifa vigente para tipo_vehiculo={tipo_vehiculo!r}, '
            f'concepto={concepto!r}. Revise la tabla tarifas (fila con vigente_hasta NULL).'
        )


def calcular_minutos(hora_entrada, hora_salida):
    """Minutos de estadía. Un minuto empezado cuenta completo (120 min 1 s = 121)."""
    if hora_salida < hora_entrada:
        raise ValueError('La hora de salida no puede ser anterior a la hora de entrada.')
    segundos = (hora_salida - hora_entrada).total_seconds()
    return math.ceil(segundos / 60)


def tiene_mensualidad_activa(usuario, tipo_vehiculo, momento):
    """True si el usuario tiene una mensualidad de ese tipo con vence_en > momento."""
    if usuario is None:  # los invitados nunca tienen mensualidad
        return False
    return Mensualidad.objects.filter(
        usuario=usuario, tipo_vehiculo=tipo_vehiculo, vence_en__gt=momento
    ).exists()


def tarifa_vigente(tipo_vehiculo, concepto):
    """La fila de `tarifas` con vigente_hasta NULL para ese tipo y concepto."""
    tarifa = Tarifa.objects.filter(
        tipo_vehiculo=tipo_vehiculo, concepto=concepto, vigente_hasta__isnull=True
    ).first()
    if tarifa is None:
        raise TarifaNoVigenteError(tipo_vehiculo, concepto)
    return tarifa


def calcular_cobro(hora_entrada, hora_salida, tipo_vehiculo, usuario=None) -> dict:
    """Calcula el cobro de una estadía.

    Devuelve un dict con:
      - valor:   pesos a cobrar (0 con mensualidad activa).
      - minutos: minutos de estadía.
      - tarifa:  instancia de Tarifa aplicada, o None si no se aplicó tarifa
                 (mensualidad activa). Es lo que se guarda en ticket.tarifa.
      - motivo:  'mensualidad_activa', 'hasta_2h' o 'mas_2h'.

    Lanza TarifaNoVigenteError si no hay tarifa vigente para el caso, y ValueError
    si la salida es anterior a la entrada.
    """
    minutos = calcular_minutos(hora_entrada, hora_salida)

    # 1. Mensualidad activa: cobro 0 y termina. usuario=None (invitado) nunca entra aquí.
    if tiene_mensualidad_activa(usuario, tipo_vehiculo, hora_salida):
        return {
            'valor': 0,
            'minutos': minutos,
            'tarifa': None,
            'motivo': MOTIVO_MENSUALIDAD_ACTIVA,
        }

    # 2. Tarifa por tiempo: hasta 120 min inclusive -> hasta_2h; desde 121 -> mas_2h.
    if minutos <= LIMITE_MINUTOS_HASTA_2H:
        concepto = ConceptoTarifa.HASTA_2H
    else:
        concepto = ConceptoTarifa.MAS_2H
    tarifa = tarifa_vigente(tipo_vehiculo, concepto)

    return {
        'valor': tarifa.valor,
        'minutos': minutos,
        'tarifa': tarifa,
        'motivo': str(concepto),
    }
