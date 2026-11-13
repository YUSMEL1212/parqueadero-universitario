from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from pagos.models import MetodoPago
from vehiculos.models import TipoVehiculo, normalizar_placa, validar_placa

from .models import Ticket


class EntradaSerializer(serializers.Serializer):
    token = serializers.CharField(help_text='Texto leído del QR del conductor.')


class SalidaSerializer(serializers.Serializer):
    token = serializers.CharField(
        required=False, help_text='QR del conductor registrado.'
    )
    codigo_salida = serializers.CharField(
        required=False, help_text='Código de 8 caracteres del ticket de invitado.'
    )

    def validate(self, attrs):
        if bool(attrs.get('token')) == bool(attrs.get('codigo_salida')):
            raise serializers.ValidationError(
                'Envíe el token del QR o el codigo_salida del invitado (uno de los dos).'
            )
        return attrs


class ConfirmarSalidaSerializer(serializers.Serializer):
    ticket_id = serializers.UUIDField()
    metodo_pago = serializers.ChoiceField(
        choices=MetodoPago.choices,
        default=MetodoPago.EFECTIVO,
        help_text='Solo se usa si hay cobro. Por defecto, efectivo.',
    )


class InvitadoSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=TipoVehiculo.choices)
    placa = serializers.CharField(max_length=10)

    def validate(self, attrs):
        attrs['placa'] = normalizar_placa(attrs['placa'])
        try:
            validar_placa(attrs['placa'], attrs['tipo'])
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from None
        return attrs


class TarifaAplicadaSerializer(serializers.Serializer):
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
