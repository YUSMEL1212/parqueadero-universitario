"""
Serializers de la API de accesos.

Validan los cuerpos que envía la PWA del guarda (entrada, salida, confirmación e
invitados) y dan forma a las respuestas (ticket abierto, liquidación y recibo). Los de
entrada no guardan nada: las reglas de negocio se aplican en accesos/porteria.py.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from pagos.models import MetodoPago
from vehiculos.models import TipoVehiculo, normalizar_placa, validar_placa

from .models import Ticket


class EntradaSerializer(serializers.Serializer):
    """Cuerpo de POST /api/accesos/entrada: el token leído del QR del conductor."""

    token = serializers.CharField(help_text='Texto leído del QR del conductor.')


class SalidaSerializer(serializers.Serializer):
    """Cuerpo de POST /api/accesos/salida: el QR del conductor o el código del invitado."""

    token = serializers.CharField(
        required=False, help_text='QR del conductor registrado.'
    )
    codigo_salida = serializers.CharField(
        required=False, help_text='Código de 8 caracteres del ticket de invitado.'
    )

    def validate(self, attrs):
        """Exige exactamente uno de los dos campos: `token` o `codigo_salida`.

        Parámetros:
            attrs (dict): datos ya validados campo por campo.

        Devuelve:
            dict: los mismos ``attrs``.

        Lanza:
            serializers.ValidationError: si llegan los dos o ninguno.
        """
        if bool(attrs.get('token')) == bool(attrs.get('codigo_salida')):
            raise serializers.ValidationError(
                'Envíe el token del QR o el codigo_salida del invitado (uno de los dos).'
            )
        return attrs


class ConfirmarSalidaSerializer(serializers.Serializer):
    """Cuerpo de POST /api/accesos/salida/confirmar: ticket a cerrar y método de pago."""

    ticket_id = serializers.UUIDField()
    metodo_pago = serializers.ChoiceField(
        choices=MetodoPago.choices,
        default=MetodoPago.EFECTIVO,
        help_text='Solo se usa si hay cobro. Por defecto, efectivo.',
    )


class InvitadoSerializer(serializers.Serializer):
    """Cuerpo de POST /api/accesos/invitados: tipo de vehículo y placa del invitado."""

    tipo = serializers.ChoiceField(choices=TipoVehiculo.choices)
    placa = serializers.CharField(max_length=10)

    def validate(self, attrs):
        """Normaliza la placa y verifica que su formato corresponda al tipo.

        Regla de negocio: carro ``ABC123`` y moto ``ABC12D``, guardadas sin guion y en
        mayúsculas.

        Parámetros:
            attrs (dict): datos con ``tipo`` y ``placa`` tal como llegaron.

        Devuelve:
            dict: los ``attrs`` con la placa normalizada.

        Lanza:
            serializers.ValidationError: si la placa no corresponde al tipo de vehículo.
        """
        attrs['placa'] = normalizar_placa(attrs['placa'])
        try:
            validar_placa(attrs['placa'], attrs['tipo'])
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from None
        return attrs


class TarifaAplicadaSerializer(serializers.Serializer):
    """Tarifa que se aplicó al cobro: id de la fila, concepto y valor en pesos."""

    id = serializers.IntegerField()
    concepto = serializers.CharField()
    valor = serializers.IntegerField()


class LiquidacionSerializer(serializers.Serializer):
    """Respuesta de POST /api/accesos/salida (documentación; la vista arma el dict)."""

    ticket_id = serializers.UUIDField()
    placa = serializers.CharField()
    tipo_vehiculo = serializers.CharField()
    tipo_ingreso = serializers.CharField()
    hora_entrada = serializers.DateTimeField()
    hora_salida = serializers.DateTimeField()
    minutos = serializers.IntegerField()
    valor = serializers.IntegerField()
    motivo = serializers.CharField(help_text='mensualidad_activa, hasta_2h o mas_2h.')
    tarifa = TarifaAplicadaSerializer(allow_null=True)


class TicketSerializer(serializers.ModelSerializer):
    """Ticket recién abierto (entrada de conductor o de invitado)."""

    placa = serializers.CharField(source='vehiculo.placa')
    tipo_vehiculo = serializers.CharField(source='vehiculo.tipo')
    conductor = serializers.CharField(source='usuario.nombre', default=None)

    class Meta:
        """Campos del ticket abierto que se devuelven a la PWA del guarda."""

        model = Ticket
        fields = [
            'id',
            'placa',
            'tipo_vehiculo',
            'conductor',
            'tipo_ingreso',
            'metodo_ingreso',
            'hora_entrada',
            'codigo_salida',
        ]


class ReciboSerializer(serializers.ModelSerializer):
    """Ticket cerrado: lo que devuelve la confirmación de salida y el historial."""

    placa = serializers.CharField(source='vehiculo.placa')
    tipo_vehiculo = serializers.CharField(source='vehiculo.tipo')
    tarifa = TarifaAplicadaSerializer(allow_null=True)
    metodo_pago = serializers.CharField(source='pago.metodo', default=None)

    class Meta:
        """Campos del recibo: estadía, valor cobrado, tarifa aplicada y pago."""

        model = Ticket
        fields = [
            'id',
            'placa',
            'tipo_vehiculo',
            'tipo_ingreso',
            'hora_entrada',
            'hora_salida',
            'minutos',
            'valor_cobrado',
            'tarifa',
            'pago',
            'metodo_pago',
        ]
