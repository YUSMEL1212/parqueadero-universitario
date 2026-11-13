from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from vehiculos.models import TipoVehiculo


class ConceptoTarifa(models.TextChoices):
    HASTA_2H = 'hasta_2h', 'Hasta 2 horas'
    MAS_2H = 'mas_2h', 'Más de 2 horas'
    MENSUALIDAD = 'mensualidad', 'Mensualidad'


class Tarifa(models.Model):
    Concepto = ConceptoTarifa

    id = models.AutoField(primary_key=True)
    tipo_vehiculo = models.CharField(max_length=5, choices=TipoVehiculo.choices)
    concepto = models.CharField(max_length=20, choices=ConceptoTarifa.choices)
    valor = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text='Pesos colombianos.',
    )
    vigente_desde = models.DateTimeField()
    vigente_hasta = models.DateTimeField(
        null=True, blank=True, help_text='NULL = tarifa vigente.'
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column='creado_por',
        related_name='tarifas_creadas',
    )

    class Meta:
        db_table = 'tarifas'
        verbose_name = 'tarifa'
        verbose_name_plural = 'tarifas'
        constraints = [
            models.UniqueConstraint(
                fields=['tipo_vehiculo', 'concepto'],
                condition=Q(vigente_hasta__isnull=True),
                name='tarifas_una_vigente_por_tipo_concepto',
                violation_error_message=(
                    'Ya existe una tarifa vigente para ese tipo de vehículo y concepto.'
                ),
            ),
            models.CheckConstraint(
                condition=Q(valor__gt=0),
                name='tarifas_valor_mayor_que_cero',
                violation_error_message='El valor de la tarifa debe ser mayor que 0.',
            ),
            models.CheckConstraint(
                condition=Q(tipo_vehiculo__in=TipoVehiculo.values),
                name='tarifas_tipo_vehiculo_valido',
            ),
            models.CheckConstraint(
                condition=Q(concepto__in=ConceptoTarifa.values),
                name='tarifas_concepto_valido',
            ),
        ]

    def __str__(self):
        estado = 'vigente' if self.vigente_hasta is None else 'histórica'
        return f'{self.tipo_vehiculo} {self.concepto}: ${self.valor} ({estado})'
