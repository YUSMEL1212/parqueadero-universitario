from rest_framework import serializers


class MensajeSensorSerializer(serializers.Serializer):
    """Contrato fijo (CLAUDE.md): mensaje de ocupación o latido del ESP32."""

    device_uid = serializers.CharField(max_length=40)
    latido = serializers.BooleanField(
        default=False, help_text='true = solo informa que el sensor sigue vivo.'
    )
    ocupado = serializers.BooleanField(
        required=False, help_text='Obligatorio si no es latido.'
    )
    distancia_cm = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    ts = serializers.DateTimeField(
        required=False,
        help_text='Hora del dispositivo. Se valida pero no se usa: el último pulso y los '
        'eventos se registran con la hora del servidor.',
    )

    def validate(self, attrs):
        if not attrs['latido'] and 'ocupado' not in attrs:
            raise serializers.ValidationError(
                {'ocupado': 'Obligatorio en un mensaje de ocupación (sin latido=true).'}
            )
        return attrs


class SensorDeBahiaSerializer(serializers.Serializer):
    device_uid = serializers.CharField()
    ultimo_pulso = serializers.DateTimeField()


class BahiaSerializer(serializers.Serializer):
    """Respuesta de /api/iot/sensores/estado: la bahía actualizada."""

    codigo = serializers.CharField()
    tipo_vehiculo = serializers.CharField()
    estado = serializers.CharField()
    actualizado_en = serializers.DateTimeField()
    sensor = SensorDeBahiaSerializer()


class LecturaLPRSerializer(serializers.Serializer):
    """Contrato fijo (CLAUDE.md): lectura de la cámara LPR."""

    camara_id = serializers.CharField(max_length=40)
    placa = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=20,
        help_text='Vacía o nula si la cámara no logró leer la placa.',
    )
    confianza = serializers.FloatField(
        required=False, allow_null=True, min_value=0, max_value=1
    )
    foto = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, help_text='Base64 o URL.'
    )


class RespuestaLPRSerializer(serializers.Serializer):
    abrir = serializers.BooleanField()
    motivo = serializers.CharField()
    ticket_id = serializers.UUIDField(allow_null=True)


class CuposSerializer(serializers.Serializer):
    tipo = serializers.CharField()
    libres = serializers.DictField(child=serializers.IntegerField())
    actualizado_en = serializers.DateTimeField()


class FilaReporteSensorSerializer(serializers.Serializer):
    bahia = serializers.CharField()
    tipo_vehiculo = serializers.CharField()
    estado_bahia = serializers.CharField()
    device_uid = serializers.CharField(allow_null=True)
    estado_sensor = serializers.CharField(allow_null=True)
    ultimo_pulso = serializers.DateTimeField(allow_null=True)
    segundos_sin_pulso = serializers.IntegerField(allow_null=True)


class ReporteSensoresSerializer(serializers.Serializer):
    generado_en = serializers.DateTimeField()
    desconectados = serializers.IntegerField()
    bahias = FilaReporteSensorSerializer(many=True)
