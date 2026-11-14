"""
Modelos de la app accesos: el ticket de estadía y sus catálogos.

Un `Ticket` registra una estadía completa de un vehículo en el parqueadero: se abre al
entrar (por LPR, QR o registro manual del guarda) y se cierra al salir con los minutos,
el valor cobrado, la tarifa aplicada y el pago. Es la tabla central sobre la que trabajan
el motor de cobro (accesos/services.py) y los servicios de portería (accesos/porteria.py).
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class TipoIngreso(models.TextChoices):
    """Quién ingresa: un conductor registrado (con cuenta) o un invitado (sin cuenta)."""

    REGISTRADO = 'registrado', 'Registrado'
    INVITADO = 'invitado', 'Invitado'


class MetodoIngreso(models.TextChoices):
    """Cómo se autorizó el ingreso: cámara de placas (LPR), QR dinámico o registro manual."""

    LPR = 'lpr', 'LPR'
    QR = 'qr', 'QR'
    MANUAL = 'manual', 'Manual'


class Ticket(models.Model):
    """Estadía de un vehículo, desde que entra hasta que sale (tabla `tickets`).

    Mientras el vehículo está adentro, `hora_salida`, `minutos`, `valor_cobrado`,
    `tarifa` y `pago` son NULL. Al confirmar la salida se llenan con el resultado del
    motor de cobro. Los tickets de invitado no tienen `usuario` y llevan un
    `codigo_salida` que el invitado presenta para salir.
    """

    TipoIngreso = TipoIngreso
    MetodoIngreso = MetodoIngreso

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vehiculo = models.ForeignKey(
        'vehiculos.Vehiculo', on_delete=models.PROTECT, related_name='tickets'
    )
    # Regla de negocio (motor de cobro, paso 3): los invitados no tienen usuario y por
    # eso nunca tienen mensualidad; siempre pagan tarifa completa.
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
    # Regla de negocio (motor de cobro, paso 1): con mensualidad activa el cobro es 0.
    valor_cobrado = models.IntegerField(
        null=True, blank=True, help_text='0 si tiene mensualidad activa.'
    )
    # Regla de negocio (motor de cobro, paso 4): el ticket guarda qué tarifa_id se
    # aplicó, para que el recibo no cambie si después se modifica la tarifa. Queda NULL
    # cuando no se aplicó tarifa (mensualidad activa).
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
        """Tabla `tickets` y sus restricciones de integridad en la base de datos."""

        db_table = 'tickets'
        verbose_name = 'ticket'
        verbose_name_plural = 'tickets'
        constraints = [
            # Regla de negocio: un usuario no puede tener dos vehículos dentro a la vez.
            # Se impone en la base (única sobre usuario_id con hora_salida IS NULL) para
            # que ni dos lecturas simultáneas del QR puedan abrir dos tickets. Los
            # invitados (usuario NULL) no chocan entre sí porque NULL no se compara igual.
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
        """Representación legible: vehículo y hora de entrada.

        Devuelve:
            str: por ejemplo ``'ABC123 (carro) - 2026-11-13 08:00'``.
        """
        return f'{self.vehiculo} - {self.hora_entrada:%Y-%m-%d %H:%M}'
