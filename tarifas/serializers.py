from rest_framework import serializers

from .models import Tarifa

# Límite de INTEGER en PostgreSQL: un valor mayor daría 500 en vez de 400.
VALOR_MAXIMO = 2_147_483_647


class TarifaSerializer(serializers.ModelSerializer):
    """Tarifa vigente, tal como la muestra la app del conductor."""

    class Meta:
        model = Tarifa
        fields = ['id', 'tipo_vehiculo', 'concepto', 'valor', 'vigente_desde']
        read_only_fields = fields


class TarifaHistorialSerializer(serializers.ModelSerializer):
    creado_por_nombre = serializers.CharField(
        source='creado_por.nombre', read_only=True, allow_null=True
    )

    class Meta:
        model = Tarifa
        fields = [
            'id',
            'tipo_vehiculo',
            'concepto',
            'valor',
            'vigente_desde',
            'vigente_hasta',
            'creado_por',
            'creado_por_nombre',
        ]
        read_only_fields = fields


def campo_valor():
    return serializers.IntegerField(
        min_value=1,
        max_value=VALOR_MAXIMO,
        help_text='Pesos colombianos, mayor que 0.',
        error_messages={'min_value': 'El valor debe ser mayor que 0.'},
    )


class ValoresPorConceptoSerializer(serializers.Serializer):
    hasta_2h = campo_valor()
    mas_2h = campo_valor()
    mensualidad = campo_valor()


class ActualizarTarifasSerializer(serializers.Serializer):
    """Los seis valores son obligatorios: carro y moto, cada uno con sus tres conceptos."""

    carro = ValoresPorConceptoSerializer()
    moto = ValoresPorConceptoSerializer()
