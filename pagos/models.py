import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q

from vehiculos.models import TipoVehiculo

DURACION_MENSUALIDAD = timedelta(days=30)


class ConceptoPago(models.TextChoices):
    MENSUALIDAD = 'mensualidad', 'Mensualidad'
    FRACCION = 'fraccion', 'Fracción'


class MetodoPago(models.TextChoices):
    PSE = 'pse', 'PSE'
    TARJETA = 'tarjeta', 'Tarjeta'
    EFECTIVO = 'efectivo', 'Efectivo'


class EstadoPago(models.TextChoices):
    PENDIENTE = 'pendiente', 'Pendiente'
    APROBADO = 'aprobado', 'Aprobado'
    RECHAZADO = 'rechazado', 'Rechazado'


class Pago(models.Model):
    Concepto = ConceptoPago
    Metodo = MetodoPago
    Estado = EstadoPago

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='pagos',
        help_text='NULL si paga un invitado.',
    )
    concepto = models.CharField(max_length=15, choices=ConceptoPago.choices)
    valor = models.IntegerField(help_text='Pesos colombianos.')
    metodo = models.CharField(max_length=10, choices=MetodoPago.choices)
    referencia_pasarela = models.CharField(
        max_length=60,
        null=True,
        blank=True,
        help_text='Id de la transacción en la pasarela.',
    )
    estado = models.CharField(
        max_length=10, choices=EstadoPago.choices, default=EstadoPago.PENDIENTE
    )
    pagado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'pagos'
        verbose_name = 'pago'
        verbose_name_plural = 'pagos'
        constraints = [
            models.CheckConstraint(
                condition=Q(concepto__in=ConceptoPago.values),
                name='pagos_concepto_valido',
            ),
            models.CheckConstraint(
                condition=Q(metodo__in=MetodoPago.values),
                name='pagos_metodo_valido',
            ),
            models.CheckConstraint(
                condition=Q(estado__in=EstadoPago.values),
                name='pagos_estado_valido',
            ),
        ]

    def __str__(self):
        return f'{self.get_concepto_display()} ${self.valor} ({self.estado})'


class Mensualidad(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='mensualidades',
    )
    pago = models.OneToOneField(
        Pago, on_delete=models.PROTECT, related_name='mensualidad'
    )
    tipo_vehiculo = models.CharField(max_length=5, choices=TipoVehiculo.choices)
    inicia_en = models.DateTimeField()
    vence_en = models.DateTimeField(
        blank=True, help_text='inicia_en + 30 días (se calcula si se deja vacío).'
    )

    class Meta:
        db_table = 'mensualidades'
        verbose_name = 'mensualidad'
        verbose_name_plural = 'mensualidades'
        constraints = [
            models.CheckConstraint(
                condition=Q(tipo_vehiculo__in=TipoVehiculo.values),
                name='mensualidades_tipo_vehiculo_valido',
            ),
        ]

    def __str__(self):
        return f'{self.usuario} - {self.tipo_vehiculo} hasta {self.vence_en:%Y-%m-%d}'

    def save(self, *args, **kwargs):
        if self.vence_en is None and self.inicia_en is not None:
            self.vence_en = self.inicia_en + DURACION_MENSUALIDAD
        super().save(*args, **kwargs)
