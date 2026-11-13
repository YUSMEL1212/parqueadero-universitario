"""
Servicios de IoT: mensajes de sensores, lecturas de la cámara LPR, conteo de cupos y
reporte de sensores para el administrador.

Las vistas (iot/views.py) solo traducen HTTP; las reglas viven aquí.
"""

import re
from decimal import ROUND_HALF_UP, Decimal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone

from accesos.models import Ticket
from accesos.services import MOTIVO_MENSUALIDAD_ACTIVA, tiene_mensualidad_activa
from vehiculos.models import PATRONES_PLACA, TipoVehiculo, Vehiculo, normalizar_placa

from .models import Bahia, EstadoBahia, EstadoSensor, EventoSensor, LecturaLPR, Sensor

# Grupo de Channels al que se suscribe cada conexión de ws/cupos.
GRUPO_CUPOS = 'cupos'


def ahora():
    """Hora actual. Las pruebas la reemplazan para simular el paso del tiempo."""
    return timezone.now()


class SensorNoRegistrado(Exception):
    def __init__(self, device_uid):
        super().__init__(f'No hay un sensor registrado con device_uid={device_uid!r}.')
        self.device_uid = device_uid


# --- Cupos y WebSocket --------------------------------------------------------------


def contar_cupos():
    """Bahías libres por tipo de vehículo. Es el mensaje que reciben ws/cupos y /api/iot/cupos."""
    libres = {tipo: 0 for tipo in TipoVehiculo.values}
    filas = (
        Bahia.objects.filter(estado=EstadoBahia.LIBRE)
        .values('tipo_vehiculo')
        .annotate(n=Count('id'))
    )
    for fila in filas:
        libres[fila['tipo_vehiculo']] = fila['n']
    return {'tipo': 'cupos', 'libres': libres, 'actualizado_en': ahora().isoformat()}


def emitir_cupos():
    """Envía el conteo actual a todas las conexiones de ws/cupos."""
    async_to_sync(get_channel_layer().group_send)(
        GRUPO_CUPOS, {'type': 'cupos.actualizados', 'cupos': contar_cupos()}
    )


# --- Sensores -----------------------------------------------------------------------


def procesar_mensaje_sensor(datos):
    """Aplica un mensaje del sensor y devuelve la bahía (con su sensor) actualizada.

    `datos` ya viene validado por MensajeSensorSerializer:
      - latido=True: solo actualiza `ultimo_pulso`.
      - si no: guarda el evento, actualiza `ultimo_pulso` y el estado de la bahía. Si
        la bahía cambió, emite el nuevo conteo de cupos cuando la transacción confirma.

    Una bahía `fuera_servicio` no cambia por el sensor: la saca de servicio el
    administrador. El evento sí se guarda.
    """
    momento = ahora()
    with transaction.atomic():
        sensor = (
            Sensor.objects.select_for_update()
            .select_related('bahia')
            .filter(device_uid=datos['device_uid'])
            .first()
        )
        if sensor is None:
            raise SensorNoRegistrado(datos['device_uid'])

        sensor.ultimo_pulso = momento
        sensor.save(update_fields=['ultimo_pulso'])
        bahia = sensor.bahia
        if datos.get('latido'):
            return bahia

        EventoSensor.objects.create(
            sensor=sensor, ocupado=datos['ocupado'], distancia_cm=datos.get('distancia_cm')
        )
        nuevo_estado = EstadoBahia.OCUPADA if datos['ocupado'] else EstadoBahia.LIBRE
        if bahia.estado not in (nuevo_estado, EstadoBahia.FUERA_SERVICIO):
            bahia.estado = nuevo_estado
            bahia.save(update_fields=['estado', 'actualizado_en'])
            # robust=True: si la capa de canales falla, se registra en el log pero el
            # sensor recibe su 200 (el cambio ya quedó guardado).
            transaction.on_commit(emitir_cupos, robust=True)
    return bahia


def reporte_sensores():
    """Cada bahía con su sensor y el estado del sensor calculado en este momento."""
    momento = ahora()
    filas = []
    for bahia in Bahia.objects.select_related('sensor').order_by('codigo'):
        sensor = getattr(bahia, 'sensor', None)
        filas.append(
            {
                'bahia': bahia.codigo,
                'tipo_vehiculo': bahia.tipo_vehiculo,
                'estado_bahia': bahia.estado,
                'device_uid': sensor.device_uid if sensor else None,
                'estado_sensor': sensor.estado_en(momento) if sensor else None,
                'ultimo_pulso': sensor.ultimo_pulso if sensor else None,
                'segundos_sin_pulso': (
                    int((momento - sensor.ultimo_pulso).total_seconds())
                    if sensor and sensor.ultimo_pulso
                    else None
                ),
            }
        )
    return {
        'generado_en': momento,
        'desconectados': sum(
            1 for f in filas if f['estado_sensor'] == EstadoSensor.DESCONECTADO
        ),
        'bahias': filas,
    }


# --- Cámara LPR ---------------------------------------------------------------------

# Motivos de la respuesta (`motivo`). Con abrir=false el ingreso pasa al lector QR.
MOTIVO_LECTURA_INVALIDA = 'lectura_invalida'  # placa vacía o sin formato de placa
MOTIVO_CONFIANZA_BAJA = 'confianza_baja'
MOTIVO_PLACA_NO_REGISTRADA = 'placa_no_registrada'  # no existe o es de un invitado
MOTIVO_VEHICULO_INACTIVO = 'vehiculo_inactivo'
MOTIVO_USUARIO_INACTIVO = 'usuario_inactivo'
MOTIVO_SIN_MENSUALIDAD = 'sin_mensualidad'
MOTIVO_VEHICULO_ADENTRO = 'vehiculo_adentro'  # el dueño ya tiene un vehículo adentro

MOTIVOS_NO_LEIDA = {MOTIVO_LECTURA_INVALIDA, MOTIVO_CONFIANZA_BAJA}


def _es_placa(placa):
    return any(re.fullmatch(patron, placa) for patron in PATRONES_PLACA.values())


def _decidir_ingreso(placa, confianza, foto, momento):
    """Devuelve (motivo, ticket). Hay ticket solo si se abre la talanquera."""
    if not _es_placa(placa):
        return MOTIVO_LECTURA_INVALIDA, None
    if confianza is not None and confianza < settings.LPR_CONFIANZA_MINIMA:
        return MOTIVO_CONFIANZA_BAJA, None

    vehiculo = Vehiculo.objects.select_related('usuario').filter(placa=placa).first()
    if vehiculo is None or vehiculo.usuario is None:
        return MOTIVO_PLACA_NO_REGISTRADA, None
    dueno = vehiculo.usuario
    if not vehiculo.activo:
        return MOTIVO_VEHICULO_INACTIVO, None
    if not dueno.activo:
        return MOTIVO_USUARIO_INACTIVO, None
    if not tiene_mensualidad_activa(dueno, vehiculo.tipo, momento):
        return MOTIVO_SIN_MENSUALIDAD, None
    if Ticket.objects.filter(usuario=dueno, hora_salida__isnull=True).exists():
        return MOTIVO_VEHICULO_ADENTRO, None

    try:
        # La restricción única de la base cubre dos lecturas casi simultáneas.
        with transaction.atomic():
            ticket = Ticket.objects.create(
                vehiculo=vehiculo,
                usuario=dueno,
                guarda=None,
                tipo_ingreso=Ticket.TipoIngreso.REGISTRADO,
                metodo_ingreso=Ticket.MetodoIngreso.LPR,
                hora_entrada=momento,
                foto_ingreso_url=foto,
            )
    except IntegrityError:
        return MOTIVO_VEHICULO_ADENTRO, None
    return MOTIVO_MENSUALIDAD_ACTIVA, ticket


def procesar_lectura_lpr(datos):
    """Decide si se abre la talanquera y registra la lectura en cualquier caso.

    `datos` viene validado por LecturaLPRSerializer. Devuelve
    `{'abrir', 'motivo', 'ticket_id'}`, la respuesta del contrato.
    """
    momento = ahora()
    placa = normalizar_placa(datos.get('placa'))
    confianza = datos.get('confianza')
    foto = datos.get('foto') or None

    with transaction.atomic():
        motivo, ticket = _decidir_ingreso(placa, confianza, foto, momento)
        if ticket is not None:
            resultado = LecturaLPR.Resultado.ABIERTA
        elif motivo in MOTIVOS_NO_LEIDA:
            resultado = LecturaLPR.Resultado.NO_LEIDA
        else:
            resultado = LecturaLPR.Resultado.RECHAZADA
        LecturaLPR.objects.create(
            ticket=ticket,
            placa_leida=placa[:10] or None,
            confianza=(
                Decimal(str(confianza)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                if confianza is not None
                else None
            ),
            foto_url=foto,
            resultado=resultado,
        )
    return {
        'abrir': ticket is not None,
        'motivo': motivo,
        'ticket_id': ticket.pk if ticket else None,
    }
