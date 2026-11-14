from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from vehiculos.models import TipoVehiculo

from .models import Mensualidad, MetodoPago, Pago
from .servicios import url_retorno_valida

# El conductor paga en línea: el efectivo solo existe en portería.
METODOS_EN_LINEA = [
    (MetodoPago.PSE, MetodoPago.PSE.label),
    (MetodoPago.TARJETA, MetodoPago.TARJETA.label),
]


class MensualidadVigenteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Mensualidad
        fields = ['id', 'tipo_vehiculo', 'inicia_en', 'vence_en']
        read_only_fields = fields


class PrecioMensualidadSerializer(serializers.Serializer):
    tipo_vehiculo = serializers.CharField()
    valor = serializers.IntegerField(help_text='Pesos colombianos.')
    tarifa_id = serializers.IntegerField()
    vigente_desde = serializers.DateTimeField()
    duracion_dias = serializers.IntegerField()


class IniciarPagoSerializer(serializers.Serializer):
    tipo_vehiculo = serializers.ChoiceField(choices=TipoVehiculo.choices)
    metodo = serializers.ChoiceField(choices=METODOS_EN_LINEA)
    banco = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=20,
        help_text='Código del banco (GET /api/pagos/pse/bancos). Obligatorio con PSE.',
    )
    correo = serializers.EmailField(
        required=False,
        allow_blank=True,
        max_length=160,
        help_text='Correo para el comprobante. Vacío = el correo de la cuenta.',
    )
    url_retorno = serializers.URLField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text='Pantalla del frontend a la que vuelve el conductor tras pagar. Debe ser '
        'un origen de CORS_ALLOWED_ORIGINS.',
    )

    def validate(self, attrs):
        if attrs['metodo'] == MetodoPago.PSE and not attrs.get('banco'):
            raise serializers.ValidationError({'banco': 'Elige tu banco para pagar con PSE.'})
        if attrs.get('url_retorno') and not url_retorno_valida(attrs['url_retorno']):
            raise serializers.ValidationError(
                {'url_retorno': 'La URL de retorno no pertenece a la aplicación.'}
            )
        return attrs


class PagoMensualidadSerializer(serializers.ModelSerializer):
    """Estado de un pago de mensualidad, con la mensualidad creada si se aprobó."""

    referencia = serializers.CharField(source='referencia_pasarela')
    mensualidad = serializers.SerializerMethodField()

    class Meta:
        model = Pago
        fields = [
            'referencia',
            'estado',
            'valor',
            'tipo_vehiculo',
            'metodo',
            'pagado_en',
            'mensualidad',
        ]
        read_only_fields = fields

    @extend_schema_field(MensualidadVigenteSerializer(allow_null=True))
    def get_mensualidad(self, pago):
        mensualidad = Mensualidad.objects.filter(pago=pago).first()
        return MensualidadVigenteSerializer(mensualidad).data if mensualidad else None


class PagoIniciadoSerializer(PagoMensualidadSerializer):
    modo = serializers.CharField(help_text='`wompi` o `simulacion`.')
    url_pago = serializers.URLField(help_text='A dónde redirigir al conductor para pagar.')

    class Meta(PagoMensualidadSerializer.Meta):
        fields = PagoMensualidadSerializer.Meta.fields + ['modo', 'url_pago']
        read_only_fields = fields


class BancoSerializer(serializers.Serializer):
    codigo = serializers.CharField()
    nombre = serializers.CharField()
