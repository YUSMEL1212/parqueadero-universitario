import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class TipoVehiculo(models.TextChoices):
    """Tipos de vehículo; se reutiliza en tarifas, mensualidades y bahías."""

    CARRO = 'carro', 'Carro'
    MOTO = 'moto', 'Moto'


PATRONES_PLACA = {
    TipoVehiculo.CARRO: r'^[A-Z]{3}[0-9]{3}$',  # ABC123
    TipoVehiculo.MOTO: r'^[A-Z]{3}[0-9]{2}[A-Z]$',  # ABC12D
}


def normalizar_placa(placa):
    """Quita guiones y espacios y pasa a mayúsculas."""
    return re.sub(r'[\s-]', '', placa or '').upper()


def validar_placa(placa, tipo):
    """Valida la placa contra el patrón de su tipo de vehículo."""
    patron = PATRONES_PLACA.get(tipo)
    if patron is None:
        raise ValidationError({'tipo': 'Tipo de vehículo no válido.'})
    if not re.fullmatch(patron, placa or ''):
        ejemplo = 'ABC123' if tipo == TipoVehiculo.CARRO else 'ABC12D'
        raise ValidationError(
            {'placa': f'Placa no válida para {tipo}: debe tener el formato {ejemplo}.'}
        )


class Vehiculo(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='vehiculos',
        help_text='NULL si es de un invitado.',
    )
    placa = models.CharField(
        max_length=6,
        unique=True,
        help_text='Sin guion y en mayúsculas.',
    )
    tipo = models.CharField(max_length=5, choices=TipoVehiculo.choices)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'vehiculos'
        verbose_name = 'vehículo'
        verbose_name_plural = 'vehículos'
        constraints = [
            models.CheckConstraint(
                condition=Q(tipo__in=TipoVehiculo.values),
                name='vehiculos_tipo_valido',
            ),
            models.CheckConstraint(
                condition=(
                    Q(tipo=TipoVehiculo.CARRO, placa__regex=PATRONES_PLACA[TipoVehiculo.CARRO])
                    | Q(tipo=TipoVehiculo.MOTO, placa__regex=PATRONES_PLACA[TipoVehiculo.MOTO])
                ),
                name='vehiculos_placa_segun_tipo',
                violation_error_message=(
                    'La placa no corresponde al tipo: carro ABC123, moto ABC12D.'
                ),
            ),
        ]

    def __str__(self):
        return f'{self.placa} ({self.tipo})'

    def clean(self):
        super().clean()
        self.placa = normalizar_placa(self.placa)
        validar_placa(self.placa, self.tipo)

    def save(self, *args, **kwargs):
        self.placa = normalizar_placa(self.placa)
        super().save(*args, **kwargs)

    def tiene_ticket_abierto(self):
        """True si el vehículo está adentro: tiene un ticket con hora_salida nula.

        Lo usan el ingreso (regla de un solo vehículo adentro por usuario) y el
        borrado de vehículos.
        """
        return self.tickets.filter(hora_salida__isnull=True).exists()
