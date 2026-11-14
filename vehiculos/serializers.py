from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .models import Vehiculo, normalizar_placa, validar_placa

MENSAJE_PLACA_DUPLICADA = 'Ya existe un vehículo registrado con esta placa.'


class PlacaField(serializers.CharField):
    """Normaliza la placa (sin guion, sin espacios, en mayúsculas) antes de validarla.

    Los validadores del campo (largo máximo y placa única) corren sobre el valor ya
    normalizado, así que "abc-123" se compara como "ABC123".
    """

    def to_internal_value(self, data):
        return normalizar_placa(super().to_internal_value(data))


class VehiculoSerializer(serializers.ModelSerializer):
    placa = PlacaField(
        max_length=6,
        validators=[
            UniqueValidator(queryset=Vehiculo.objects.all(), message=MENSAJE_PLACA_DUPLICADA)
        ],
        help_text='Se acepta con guion, espacios o minúsculas; se guarda como ABC123.',
    )

    adentro = serializers.SerializerMethodField(
        help_text='True si el vehículo tiene un ingreso abierto (está dentro del parqueadero).'
    )

    class Meta:
        model = Vehiculo
        fields = ['id', 'placa', 'tipo', 'activo', 'adentro', 'usuario', 'creado_en']
        read_only_fields = ['id', 'usuario', 'creado_en']

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_adentro(self, vehiculo):
        # La lista anota `esta_adentro` en una sola consulta (VehiculoViewSet.get_queryset);
        # un vehículo recién creado no trae la anotación y se consulta directamente.
        anotado = getattr(vehiculo, 'esta_adentro', None)
        if anotado is not None:
            return anotado
        return vehiculo.tiene_ticket_abierto()

    def validate(self, attrs):
        # En un PATCH puede llegar solo la placa o solo el tipo: se valida la
        # combinación final contra los valores actuales del vehículo.
        placa = attrs.get('placa', getattr(self.instance, 'placa', None))
        tipo = attrs.get('tipo', getattr(self.instance, 'tipo', None))
        if (
            self.instance is not None
            and (placa, tipo) != (self.instance.placa, self.instance.tipo)
            and self.instance.tiene_ticket_abierto()
        ):
            # El cobro y la lectura LPR de salida dependen de la placa y el tipo.
            raise serializers.ValidationError(
                'No se puede cambiar la placa ni el tipo mientras el vehículo está '
                'dentro del parqueadero.'
            )
        try:
            validar_placa(placa, tipo)
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict)
        return attrs

    def save(self, **kwargs):
        # Dos peticiones simultáneas con la misma placa pasan el UniqueValidator;
        # la restricción UNIQUE de la base decide y se responde 400, no 500.
        try:
            with transaction.atomic():
                return super().save(**kwargs)
        except IntegrityError:
            otros = Vehiculo.objects.exclude(pk=getattr(self.instance, 'pk', None))
            if otros.filter(placa=self.validated_data.get('placa')).exists():
                raise serializers.ValidationError({'placa': [MENSAJE_PLACA_DUPLICADA]})
            raise
