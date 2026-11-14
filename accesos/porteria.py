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
    """Hora actual. Las pruebas la reemplazan para simular el paso del tiempo.

    Devuelve:
        datetime: hora actual con zona horaria (``django.utils.timezone.now``).
    """
    return timezone.now()


# --- Errores ------------------------------------------------------------------------


class ErrorPorteria(Exception):
    """Error de negocio de la portería, con su código HTTP y un `codigo` estable.

    Las vistas de portería lo capturan y responden con ``como_respuesta()`` y el
    código HTTP de ``status``. Las subclases solo cambian ``status``.
    """

    status = 400

    def __init__(self, mensaje, codigo, **extra):
        """Crea el error.

        Parámetros:
            mensaje (str): texto para mostrar al guarda.
            codigo (str): identificador estable del caso (p. ej. 'vehiculo_adentro').
            **extra: campos adicionales que se agregan a la respuesta JSON.
        """
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo
        self.extra = extra

    def como_respuesta(self):
        """Cuerpo JSON de la respuesta de error.

        Devuelve:
            dict: ``{'detail': ..., 'codigo': ..., **extra}``.
        """
        return {'detail': self.mensaje, 'codigo': self.codigo, **self.extra}


class QRInvalido(ErrorPorteria):
    """El QR está vencido, alterado o ilegible (HTTP 400)."""

    status = 400


class NoEncontrado(ErrorPorteria):
    """No existe el vehículo, el ticket o el ticket abierto buscado (HTTP 404)."""

    status = 404


class Conflicto(ErrorPorteria):
    """La operación choca con el estado actual: vehículo adentro, ticket cerrado, etc. (HTTP 409)."""

    status = 409


class SinTarifaVigente(ErrorPorteria):
    """No hay tarifa vigente para calcular el cobro; es un problema de configuración (HTTP 503)."""

    status = 503


# --- Auxiliares ---------------------------------------------------------------------


def _leer_qr(token):
    """Valida el token y devuelve el vehículo (con su usuario) que lo generó.

    Parámetros:
        token (str): texto leído del QR del conductor.

    Devuelve:
        Vehiculo: el vehículo del token, con ``usuario`` ya cargado.

    Lanza:
        QRInvalido: con codigo 'qr_vencido', 'qr_alterado' o 'qr_ilegible'.
        NoEncontrado: si el vehículo ya no existe o cambió de dueño ('vehiculo_no_existe').
    """
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
    """Arma el error de "ya tiene un vehículo adentro", con la placa si se encuentra.

    No lanza el error: lo devuelve para que quien llama haga ``raise``.

    Parámetros:
        usuario_id: id del conductor que intenta ingresar.

    Devuelve:
        Conflicto: con codigo 'vehiculo_adentro' y ``placa_adentro`` (o None).
    """
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
    """Código de 8 caracteres que no repite el de ningún invitado que esté adentro.

    Devuelve:
        str: código aleatorio con caracteres de ``ALFABETO_CODIGO``.
    """
    while True:
        codigo = ''.join(secrets.choice(ALFABETO_CODIGO) for _ in range(LARGO_CODIGO))
        if not Ticket.objects.filter(codigo_salida=codigo, hora_salida__isnull=True).exists():
            return codigo


def _cobrar(ticket, hora_salida):
    """Aplica el motor de cobro a un ticket y traduce la falta de tarifa a error de portería.

    Parámetros:
        ticket (Ticket): ticket abierto, con ``vehiculo`` y ``usuario`` disponibles.
        hora_salida (datetime): momento de salida con el que se calcula.

    Devuelve:
        dict: el resultado de ``calcular_cobro`` (valor, minutos, tarifa, motivo).

    Lanza:
        SinTarifaVigente: si no hay tarifa vigente para el caso ('sin_tarifa_vigente').
    """
    try:
        return calcular_cobro(
            ticket.hora_entrada, hora_salida, ticket.vehiculo.tipo, usuario=ticket.usuario
        )
    except TarifaNoVigenteError as exc:
        raise SinTarifaVigente(str(exc), 'sin_tarifa_vigente') from None


def _liquidacion(ticket, hora_salida, cobro):
    """Arma el dict de liquidación que se muestra al guarda antes de cobrar.

    Parámetros:
        ticket (Ticket): ticket que se liquida.
        hora_salida (datetime): hora de salida usada en el cálculo.
        cobro (dict): resultado de ``calcular_cobro``.

    Devuelve:
        dict: con la forma de ``LiquidacionSerializer``.
    """
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
    """Ingreso de un conductor registrado con su QR. Devuelve el Ticket creado.

    Parámetros:
        token (str): texto leído del QR del conductor.
        guarda (Usuario): guarda que registra el ingreso.

    Devuelve:
        Ticket: ticket abierto con ``tipo_ingreso='registrado'`` y ``metodo_ingreso='qr'``.

    Lanza:
        QRInvalido: si el QR está vencido, alterado o ilegible.
        NoEncontrado: si el vehículo del QR ya no existe.
        Conflicto: si la cuenta o el vehículo están desactivados, o si el conductor ya
            tiene un vehículo adentro.
    """
    vehiculo = _leer_qr(token)
    conductor = vehiculo.usuario
    if not conductor.activo:
        raise Conflicto('La cuenta del conductor está desactivada.', 'usuario_inactivo')
    if not vehiculo.activo:
        raise Conflicto('El vehículo está desactivado.', 'vehiculo_inactivo')

    # Regla TDR (flujo 4): un usuario no puede tener dos vehículos dentro a la vez. Se
    # revisa antes de crear para responder 409 con la placa del vehículo que está adentro.
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
    """Busca el ticket abierto del conductor que presenta su QR en la salida.

    Parámetros:
        token (str): texto leído del QR del conductor.

    Devuelve:
        Ticket: el ticket abierto del conductor (sea cual sea el vehículo).

    Lanza:
        QRInvalido: si el QR está vencido, alterado o ilegible.
        NoEncontrado: si el vehículo no existe o el conductor no tiene ticket abierto.
    """
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
    """Busca el ticket abierto de un invitado por su código de salida.

    Parámetros:
        codigo (str): código impreso en el ticket; se aceptan minúsculas y espacios.

    Devuelve:
        Ticket: el ticket de invitado abierto con ese código.

    Lanza:
        NoEncontrado: si no hay un invitado adentro con ese código ('sin_ticket_abierto').
    """
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
    """Calcula lo que se cobraría si el vehículo sale ahora. No modifica el ticket.

    Parámetros:
        ticket (Ticket): ticket abierto.

    Devuelve:
        dict: liquidación con la forma de ``LiquidacionSerializer``.

    Lanza:
        SinTarifaVigente: si no hay tarifa vigente para el caso.
    """
    hora_salida = ahora()
    return _liquidacion(ticket, hora_salida, _cobrar(ticket, hora_salida))


def confirmar_salida(ticket_id, metodo_pago=Pago.Metodo.EFECTIVO):
    """Cierra el ticket con el cobro calculado en este momento y registra el pago.

    El cobro se recalcula aquí (no se confía en el valor que mostró la liquidación),
    así que si entre liquidar y confirmar se cruzan los 120 minutos, se cobra mas_2h.

    Parámetros:
        ticket_id: id (UUID) del ticket a cerrar.
        metodo_pago (str): método del pago si hay cobro; por defecto, efectivo.

    Devuelve:
        Ticket: el ticket cerrado, con hora de salida, minutos, valor, tarifa y pago.

    Lanza:
        NoEncontrado: si el ticket no existe ('ticket_no_existe').
        Conflicto: si el ticket ya estaba cerrado ('ticket_cerrado').
        SinTarifaVigente: si no hay tarifa vigente para el caso.
    """
    with transaction.atomic():
        ticket = (
            # of=('self',): solo se bloquea la fila del ticket. `usuario` es nulo en los
            # invitados (LEFT JOIN) y PostgreSQL no admite FOR UPDATE sobre ese lado.
            Ticket.objects.select_for_update(of=('self',))
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

        # Regla TDR (motor de cobro, paso 1): con mensualidad activa el cobro es 0, así
        # que no se crea ningún pago.
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
        # Regla TDR (motor de cobro, paso 4): el ticket guarda qué tarifa_id se aplicó.
        ticket.tarifa = cobro['tarifa']
        ticket.save(
            update_fields=['hora_salida', 'minutos', 'valor_cobrado', 'tarifa', 'pago']
        )
    return ticket


def registrar_invitado(placa, tipo, guarda):
    """Ingreso de un invitado. `placa` ya viene normalizada y validada contra `tipo`.

    Parámetros:
        placa (str): placa normalizada (mayúsculas, sin guion).
        tipo (str): 'carro' o 'moto'.
        guarda (Usuario): guarda que registra el ingreso.

    Devuelve:
        Ticket: ticket abierto de tipo 'invitado', método 'manual' y con
        ``codigo_salida`` de 8 caracteres.

    Lanza:
        Conflicto: si la placa es de un conductor registrado ('placa_registrada') o el
            vehículo ya está adentro ('vehiculo_adentro').
    """
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
        # Regla TDR (motor de cobro, paso 3; flujo 3): el ticket va con usuario=None, así
        # el motor de cobro nunca encuentra mensualidad y el invitado paga tarifa completa.
        return Ticket.objects.create(
            vehiculo=vehiculo,
            usuario=None,
            guarda=guarda,
            tipo_ingreso=Ticket.TipoIngreso.INVITADO,
            metodo_ingreso=Ticket.MetodoIngreso.MANUAL,
            hora_entrada=ahora(),
            codigo_salida=_nuevo_codigo_salida(),
        )
