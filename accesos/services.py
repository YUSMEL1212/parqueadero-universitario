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
# Regla TDR (motor de cobro, paso 2): "Hasta 120 minutos -> hasta_2h. Desde 121 minutos
# -> mas_2h". El TDR parte la estadía en dos tramos con la frontera en dos horas exactas:
# por eso la comparación es <= 120 (el minuto 120 todavía es tarifa corta). Va en el
# código y no en la tabla `tarifas` porque define el tramo, no el precio; los precios
# de cada tramo sí se leen de la base.
LIMITE_MINUTOS_HASTA_2H = 120

# Mismo texto que el campo `motivo` del contrato LPR (CLAUDE.md, "Contrato de mensajes
# IoT"); el contrato es fijo, así que este valor no se cambia.
MOTIVO_MENSUALIDAD_ACTIVA = 'mensualidad_activa'


class TarifaNoVigenteError(Exception):
    """No hay una tarifa vigente (vigente_hasta NULL) para el tipo y concepto pedidos."""

    def __init__(self, tipo_vehiculo, concepto):
        """Guarda el caso que no tiene tarifa y arma un mensaje que dice dónde revisar.

        Parámetros:
            tipo_vehiculo (str): tipo de vehículo pedido ('carro' o 'moto').
            concepto (str): concepto de tarifa pedido ('hasta_2h' o 'mas_2h').
        """
        self.tipo_vehiculo = tipo_vehiculo
        self.concepto = concepto
        super().__init__(
            f'No hay tarifa vigente para tipo_vehiculo={tipo_vehiculo!r}, '
            f'concepto={concepto!r}. Revise la tabla tarifas (fila con vigente_hasta NULL).'
        )


def calcular_minutos(hora_entrada, hora_salida):
    """Minutos de estadía. Un minuto empezado cuenta completo (120 min 1 s = 121).

    Parámetros:
        hora_entrada (datetime): momento en que el vehículo entró.
        hora_salida (datetime): momento en que el vehículo sale.

    Devuelve:
        int: minutos de estadía redondeados hacia arriba.

    Lanza:
        ValueError: si la salida es anterior a la entrada.
    """
    if hora_salida < hora_entrada:
        raise ValueError('La hora de salida no puede ser anterior a la hora de entrada.')
    segundos = (hora_salida - hora_entrada).total_seconds()
    # Regla de negocio: el redondeo hacia arriba hace que pasar de las 2 horas por un
    # solo segundo ya cuente como minuto 121 y, por tanto, como tarifa mas_2h.
    return math.ceil(segundos / 60)


def tiene_mensualidad_activa(usuario, tipo_vehiculo, momento):
    """True si el usuario tiene una mensualidad de ese tipo con vence_en > momento.

    Parámetros:
        usuario (Usuario | None): conductor dueño del ticket; None si es invitado.
        tipo_vehiculo (str): 'carro' o 'moto'. La mensualidad solo cubre su tipo.
        momento (datetime): instante contra el que se compara el vencimiento.

    Devuelve:
        bool: True si existe una mensualidad vigente para ese usuario y tipo.
    """
    # Regla TDR (motor de cobro, paso 3): los invitados nunca tienen mensualidad.
    if usuario is None:  # los invitados nunca tienen mensualidad
        return False
    # Regla TDR (motor de cobro, paso 1): mensualidad activa = mismo tipo de vehículo y
    # vence_en > ahora. Una mensualidad de moto no cubre un carro.
    return Mensualidad.objects.filter(
        usuario=usuario, tipo_vehiculo=tipo_vehiculo, vence_en__gt=momento
    ).exists()


def tarifa_vigente(tipo_vehiculo, concepto):
    """La fila de `tarifas` con vigente_hasta NULL para ese tipo y concepto.

    Parámetros:
        tipo_vehiculo (str): 'carro' o 'moto'.
        concepto (str): concepto de tarifa ('hasta_2h' o 'mas_2h').

    Devuelve:
        Tarifa: la tarifa vigente.

    Lanza:
        TarifaNoVigenteError: si no hay ninguna fila vigente para ese caso.
    """
    # Regla del sistema: las tarifas nunca van en el código. Un cambio de tarifa cierra
    # la fila anterior (vigente_hasta) y crea otra; la vigente es la que tiene NULL.
    tarifa = Tarifa.objects.filter(
        tipo_vehiculo=tipo_vehiculo, concepto=concepto, vigente_hasta__isnull=True
    ).first()
    if tarifa is None:
        raise TarifaNoVigenteError(tipo_vehiculo, concepto)
    return tarifa


def calcular_cobro(hora_entrada, hora_salida, tipo_vehiculo, usuario=None) -> dict:
    """Calcula el cobro de una estadía.

    Parámetros:
      - hora_entrada: datetime en que el vehículo entró.
      - hora_salida:  datetime en que el vehículo sale.
      - tipo_vehiculo: 'carro' o 'moto'.
      - usuario:      conductor dueño del ticket, o None si es invitado (por defecto).

    Devuelve un dict con:
      - valor:   pesos a cobrar (0 con mensualidad activa).
      - minutos: minutos de estadía.
      - tarifa:  instancia de Tarifa aplicada, o None si no se aplicó tarifa
                 (mensualidad activa). Es lo que se guarda en ticket.tarifa.
      - motivo:  'mensualidad_activa', 'hasta_2h' o 'mas_2h'.

    Lanza TarifaNoVigenteError si no hay tarifa vigente para el caso, y ValueError
    si la salida es anterior a la entrada.
    """
    # Los minutos se calculan siempre, también con mensualidad, porque el ticket guarda
    # la estadía (ticket.minutos) y porque así se rechaza una salida anterior a la
    # entrada. Pero el tiempo no decide nada hasta descartar la mensualidad.
    minutos = calcular_minutos(hora_entrada, hora_salida)

    # Regla TDR (motor de cobro, paso 1): la mensualidad se revisa ANTES de aplicar la
    # tarifa por tiempo porque con mensualidad activa el cobro es 0 sin importar cuánto
    # dure la estadía. Si se mirara primero el tiempo, un abonado que pase de 120
    # minutos caería en mas_2h. Se compara contra la hora de salida: una mensualidad que
    # vence durante la estadía ya no cubre esa salida.
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

    # Regla TDR (motor de cobro, paso 4): se devuelve la instancia de Tarifa para que el
    # ticket guarde qué tarifa_id se aplicó.
    return {
        'valor': tarifa.valor,
        'minutos': minutos,
        'tarifa': tarifa,
        'motivo': str(concepto),
    }
