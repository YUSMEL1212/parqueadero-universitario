import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class TipoIngreso(models.TextChoices):
    REGISTRADO = 'registrado', 'Registrado'
    INVITADO = 'invitado', 'Invitado'


class MetodoIngreso(models.TextChoices):
    LPR = 'lpr', 'LPR'
    QR = 'qr', 'QR'
    MANUAL = 'manual', 'Manual'


class Ticket(models.Model):
    TipoIngreso = TipoIngreso
    MetodoIngreso = MetodoIngreso

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vehiculo = models.ForeignKey(
        'vehiculos.Vehiculo', on_delete=models.PROTECT, related_name='tickets'
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='tickets',
        help_text='NULL si es invitado.',
    )
    guarda = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='tickets_atendidos',
        help_text='NULL si entró por LPR.',
    )
    tipo_ingreso = models.CharField(max_length=10, choices=TipoIngreso.choices)
    metodo_ingreso = models.CharField(max_length=6, choices=MetodoIngreso.choices)
    hora_entrada = models.DateTimeField()
    hora_salida = models.DateTimeField(
        null=True, blank=True, help_text='NULL mientras el vehículo está adentro.'
    )
    minutos = models.IntegerField(
        null=True, blank=True, help_text='Tiempo total de estadía.'
    )
    valor_cobrado = models.IntegerField(
        null=True, blank=True, help_text='0 si tiene mensualidad activa.'
    )
    tarifa = models.ForeignKey(
        'tarifas.Tarifa',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='tickets',
        help_text='Tarifa aplicada.',
    )
    pago = models.ForeignKey(
        'pagos.Pago',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='tickets',
    )
    foto_ingreso_url = models.TextField(
        null=True, blank=True, help_text='Foto tomada por la cámara LPR.'
    )
    codigo_salida = models.CharField(
        max_length=12, null=True, blank=True, help_text='Código del ticket de invitado.'
    )

    class Meta:
        db_table = 'tickets'
        verbose_name = 'ticket'
        verbose_name_plural = 'tickets'
        constraints = [
            models.UniqueConstraint(
                fields=['usuario'],
                condition=Q(hora_salida__isnull=True),
                name='tickets_un_vehiculo_adentro_por_usuario',
                violation_error_message='El usuario ya tiene un vehículo adentro.',
            ),
            models.CheckConstraint(
                condition=Q(tipo_ingreso__in=TipoIngreso.values),
                name='tickets_tipo_ingreso_valido',
            ),
            models.CheckConstraint(
                condition=Q(metodo_ingreso__in=MetodoIngreso.values),
                name='tickets_metodo_ingreso_valido',
            ),
        ]

    def __str__(self):
        return f'{self.vehiculo} - {self.hora_entrada:%Y-%m-%d %H:%M}'
