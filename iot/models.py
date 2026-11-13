from django.db import models
from django.db.models import Q

from vehiculos.models import TipoVehiculo


class EstadoBahia(models.TextChoices):
    LIBRE = 'libre', 'Libre'
    OCUPADA = 'ocupada', 'Ocupada'
    FUERA_SERVICIO = 'fuera_servicio', 'Fuera de servicio'


class Bahia(models.Model):
    Estado = EstadoBahia

    id = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=10, unique=True, help_text='Ej. C-01, M-01.')
    tipo_vehiculo = models.CharField(max_length=5, choices=TipoVehiculo.choices)
    estado = models.CharField(
        max_length=15, choices=EstadoBahia.choices, default=EstadoBahia.LIBRE
    )
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bahias'
        verbose_name = 'bahía'
        verbose_name_plural = 'bahías'
        ordering = ['codigo']
        constraints = [
            models.CheckConstraint(
                condition=Q(tipo_vehiculo__in=TipoVehiculo.values),
                name='bahias_tipo_vehiculo_valido',
            ),
            models.CheckConstraint(
                condition=Q(estado__in=EstadoBahia.values),
                name='bahias_estado_valido',
            ),
        ]

    def __str__(self):
        return f'{self.codigo} ({self.estado})'


class EstadoSensor(models.TextChoices):
    OK = 'ok', 'OK'
    DESCONECTADO = 'desconectado', 'Desconectado'
    FALLA = 'falla', 'Falla'


class Sensor(models.Model):
    Estado = EstadoSensor

    id = models.AutoField(primary_key=True)
    bahia = models.OneToOneField(
        Bahia, on_delete=models.PROTECT, related_name='sensor'
    )
    device_uid = models.CharField(max_length=40, unique=True)
    estado = models.CharField(
        max_length=15, choices=EstadoSensor.choices, default=EstadoSensor.DESCONECTADO
    )
    ultimo_pulso = models.DateTimeField(
        null=True, blank=True, help_text='Último mensaje o latido recibido.'
    )

    class Meta:
        db_table = 'sensores'
        verbose_name = 'sensor'
        verbose_name_plural = 'sensores'
        constraints = [
            models.CheckConstraint(
                condition=Q(estado__in=EstadoSensor.values),
                name='sensores_estado_valido',
            ),
        ]

    def __str__(self):
        return f'{self.device_uid} ({self.estado})'


class EventoSensor(models.Model):
    id = models.BigAutoField(primary_key=True)
    sensor = models.ForeignKey(
        Sensor, on_delete=models.CASCADE, related_name='eventos'
    )
    ocupado = models.BooleanField()
    distancia_cm = models.IntegerField(
        null=True, blank=True, help_text='Distancia medida.'
    )
    recibido_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'eventos_sensor'
        verbose_name = 'evento de sensor'
        verbose_name_plural = 'eventos de sensor'

    def __str__(self):
        estado = 'ocupado' if self.ocupado else 'libre'
        return f'{self.sensor.device_uid} {estado} @ {self.recibido_en:%Y-%m-%d %H:%M:%S}'


class ResultadoLPR(models.TextChoices):
    ABIERTA = 'abierta', 'Abierta'
    RECHAZADA = 'rechazada', 'Rechazada'
    NO_LEIDA = 'no_leida', 'No leída'


class LecturaLPR(models.Model):
    Resultado = ResultadoLPR

    id = models.BigAutoField(primary_key=True)
    ticket = models.ForeignKey(
        'accesos.Ticket',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='lecturas_lpr',
        help_text='NULL si no abrió.',
    )
    placa_leida = models.CharField(max_length=10, null=True, blank=True)
    confianza = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Nivel de confianza de la lectura.',
    )
    foto_url = models.TextField(null=True, blank=True)
    resultado = models.CharField(max_length=12, choices=ResultadoLPR.choices)
    leido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'lecturas_lpr'
        verbose_name = 'lectura LPR'
        verbose_name_plural = 'lecturas LPR'
        constraints = [
            models.CheckConstraint(
                condition=Q(resultado__in=ResultadoLPR.values),
                name='lecturas_lpr_resultado_valido',
            ),
        ]

    def __str__(self):
        return f'{self.placa_leida or "—"} {self.resultado}'
