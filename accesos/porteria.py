"""
Servicios de portería: entrada por QR, liquidación y cierre de salida, e invitados.

Las vistas (accesos/views.py) solo traducen HTTP; las reglas viven aquí. Cada función
lanza una subclase de ErrorPorteria con el código HTTP y un `codigo` estable que la
PWA del guarda puede usar para mostrar el mensaje correcto.
"""

import secrets

from django.db import IntegrityError, transaction
from django.utils import timezone

from pagos.models import Pago
from vehiculos.models import Vehiculo

from .models import Ticket
from .qr import TokenQRAlterado, TokenQRError, TokenQRVencido, validar_token
from .services import TarifaNoVigenteError, calcular_cobro

# Sin 0/O ni 1/I para que el guarda no los confunda al leerlos del ticket impreso.
ALFABETO_CODIGO = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
LARGO_CODIGO = 8


def ahora():
    """Hora actual. Las pruebas la reemplazan para simular el paso del tiempo."""
    return timezone.now()


# --- Errores ------------------------------------------------------------------------


class ErrorPorteria(Exception):
    status = 400

    def __init__(self, mensaje, codigo, **extra):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo
        self.extra = extra

    def como_respuesta(self):
        return {'detail': self.mensaje, 'codigo': self.codigo, **self.extra}


class QRInvalido(ErrorPorteria):
    status = 400


class NoEncontrado(ErrorPorteria):
    status = 404


class Conflicto(ErrorPorteria):
    status = 409


class SinTarifaVigente(ErrorPorteria):
    status = 503


# --- Auxiliares ---------------------------------------------------------------------


def _leer_qr(token):
    """Valida el token y devuelve el vehículo (con su usuario) que lo generó."""
    try:
        datos = validar_token(token)
    except TokenQRVencido as exc:
        raise QRInvalido(str(exc), 'qr_vencido') from None
    except TokenQRAlterado as exc:
        raise QRInvalido(str(exc), 'qr_alterado') from None
    except TokenQRError as exc:
        raise QRInvalido(str(exc), 'qr_ilegible') from None

    vehiculo = (
        Vehiculo.objects.select_related('usuario')
        .filter(pk=datos['vehiculo_id'], usuario_id=datos['usuario_id'])
        .first()
    )
    if vehiculo is None:
        raise NoEncontrado('El vehículo del QR ya no está registrado.', 'vehiculo_no_existe')
    return vehiculo


def _conflicto_vehiculo_adentro(usuario_id):
    abierto = (
        Ticket.objects.select_related('vehiculo')
        .filter(usuario_id=usuario_id, hora_salida__isnull=True)
        .first()
    )
    placa = abierto.vehiculo.placa if abierto else None
    return Conflicto(
        f'El conductor ya tiene un vehículo adentro ({placa}). Debe salir antes de ingresar otro.'
        if placa
        else 'El conductor ya tiene un vehículo adentro.',
        'vehiculo_adentro',
        placa_adentro=placa,
    )


def _nuevo_codigo_salida():
    """Código de 8 caracteres que no repite el de ningún invitado que esté adentro."""
    while True:
        codigo = ''.join(secrets.choice(ALFABETO_CODIGO) for _ in range(LARGO_CODIGO))
        if not Ticket.objects.filter(codigo_salida=codigo, hora_salida__isnull=True).exists():
            return codigo


def _cobrar(ticket, hora_salida):
    try:
        return calcular_cobro(
            ticket.hora_entrada, hora_salida, ticket.vehiculo.tipo, usuario=ticket.usuario
        )
    except TarifaNoVigenteError as exc:
        raise SinTarifaVigente(str(exc), 'sin_tarifa_vigente') from None


def _liquidacion(ticket, hora_salida, cobro):
    return {
        'ticket_id': ticket.pk,
        'placa': ticket.vehiculo.placa,
        'tipo_vehiculo': ticket.vehiculo.tipo,
        'tipo_ingreso': ticket.tipo_ingreso,
        'hora_entrada': ticket.hora_entrada,
        'hora_salida': hora_salida,
        'minutos': cobro['minutos'],
        'valor': cobro['valor'],
        'motivo': cobro['motivo'],
        'tarifa': (
            {
                'id': cobro['tarifa'].pk,
                'concepto': cobro['tarifa'].concepto,
                'valor': cobro['tarifa'].valor,
            }
            if cobro['tarifa']
            else None
        ),
    }


# --- Servicios ----------------------------------------------------------------------


def registrar_entrada(token, guarda):
    """Ingreso de un conductor registrado con su QR. Devuelve el Ticket creado."""
    vehiculo = _leer_qr(token)
    conductor = vehiculo.usuario
    if not conductor.activo:
        raise Conflicto('La cuenta del conductor está desactivada.', 'usuario_inactivo')
    if not vehiculo.activo:
        raise Conflicto('El vehículo está desactivado.', 'vehiculo_inactivo')

    if Ticket.objects.filter(usuario=conductor, hora_salida__isnull=True).exists():
        raise _conflicto_vehiculo_adentro(conductor.pk)

    try:
        # La restricción única de la base cubre dos lecturas casi simultáneas del QR.
        with transaction.atomic():
            return Ticket.objects.create(
                vehiculo=vehiculo,
                usuario=conductor,
                guarda=guarda,
                tipo_ingreso=Ticket.TipoIngreso.REGISTRADO,
                metodo_ingreso=Ticket.MetodoIngreso.QR,
                hora_entrada=ahora(),
            )
    except IntegrityError:
        raise _conflicto_vehiculo_adentro(conductor.pk) from None


def buscar_ticket_por_qr(token):
    vehiculo = _leer_qr(token)
    ticket = (
        Ticket.objects.select_related('vehiculo', 'usuario')
        .filter(usuario=vehiculo.usuario, hora_salida__isnull=True)
        .first()
    )
    if ticket is None:
        raise NoEncontrado('El conductor no tiene un vehículo adentro.', 'sin_ticket_abierto')
    return ticket


def buscar_ticket_por_codigo(codigo):
    ticket = (
        Ticket.objects.select_related('vehiculo')
        .filter(
            codigo_salida=codigo.strip().upper(),
            tipo_ingreso=Ticket.TipoIngreso.INVITADO,
            hora_salida__isnull=True,
        )
        .first()
    )
    if ticket is None:
        raise NoEncontrado(
            'No hay un invitado adentro con ese código de salida.', 'sin_ticket_abierto'
        )
    return ticket


def liquidar_salida(ticket):
    """Calcula lo que se cobraría si el vehículo sale ahora. No modifica el ticket."""
    hora_salida = ahora()
    return _liquidacion(ticket, hora_salida, _cobrar(ticket, hora_salida))


def confirmar_salida(ticket_id, metodo_pago=Pago.Metodo.EFECTIVO):
    """Cierra el ticket con el cobro calculado en este momento y registra el pago.

    El cobro se recalcula aquí (no se confía en el valor que mostró la liquidación),
    así que si entre liquidar y confirmar se cruzan los 120 minutos, se cobra mas_2h.
    """
    with transaction.atomic():
        ticket = (
            Ticket.objects.select_for_update()
            .select_related('vehiculo', 'usuario')
            .filter(pk=ticket_id)
            .first()
        )
        if ticket is None:
            raise NoEncontrado('El ticket no existe.', 'ticket_no_existe')
        if ticket.hora_salida is not None:
            raise Conflicto('Este ticket ya fue cerrado.', 'ticket_cerrado')

        hora_salida = ahora()
        cobro = _cobrar(ticket, hora_salida)

        if cobro['valor'] > 0:
            ticket.pago = Pago.objects.create(
                usuario=ticket.usuario,
                concepto=Pago.Concepto.FRACCION,
                valor=cobro['valor'],
                metodo=metodo_pago,
                estado=Pago.Estado.APROBADO,
                pagado_en=hora_salida,
            )
        ticket.hora_salida = hora_salida
        ticket.minutos = cobro['minutos']
        ticket.valor_cobrado = cobro['valor']
        ticket.tarifa = cobro['tarifa']
        ticket.save(
            update_fields=['hora_salida', 'minutos', 'valor_cobrado', 'tarifa', 'pago']
        )
    return ticket


def registrar_invitado(placa, tipo, guarda):
    """Ingreso de un invitado. `placa` ya viene normalizada y validada contra `tipo`."""
    vehiculo = Vehiculo.objects.filter(placa=placa).first()
    if vehiculo is not None and vehiculo.usuario_id is not None:
        raise Conflicto(
            f'La placa {placa} es de un conductor registrado; debe ingresar con su QR.',
            'placa_registrada',
        )
    if vehiculo is not None and vehiculo.tiene_ticket_abierto():
        raise Conflicto(f'El vehículo {placa} ya está adentro.', 'vehiculo_adentro')

    with transaction.atomic():
        if vehiculo is None:
            # Vehículo sin usuario; si el invitado vuelve otro día se reutiliza.
            vehiculo = Vehiculo.objects.create(placa=placa, tipo=tipo, usuario=None)
        return Ticket.objects.create(
            vehiculo=vehiculo,
            usuario=None,
            guarda=guarda,
            tipo_ingreso=Ticket.TipoIngreso.INVITADO,
            metodo_ingreso=Ticket.MetodoIngreso.MANUAL,
            hora_entrada=ahora(),
            codigo_salida=_nuevo_codigo_salida(),
        )
