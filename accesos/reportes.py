"""
Reporte de ingresos por día para el administrador (GET /api/reportes/ingresos).

Para cada día del rango, en la hora de Colombia (TIME_ZONE):
  - ingresos: tickets cuya `hora_entrada` cae ese día, separados en registrados e
    invitados (`tipo_ingreso`).
  - cobrado: suma de `valor_cobrado` de los tickets cuya `hora_salida` cae ese día. La
    plata se cuenta el día en que se cobra, que es al salir; un vehículo que entra un día
    y sale al siguiente suma su ingreso al primero y su cobro al segundo.

Solo cuenta tickets (cobros por fracción en portería). El pago de mensualidades no entra
en este reporte.
"""

from datetime import datetime, time, timedelta

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import Ticket, TipoIngreso

# Rango máximo de una consulta, para que una fecha mal escrita no recorra años.
MAX_DIAS = 366

CAMPOS_DIA = (
    'ingresos',
    'ingresos_registrados',
    'ingresos_invitados',
    'cobrado',
    'cobrado_registrados',
    'cobrado_invitados',
)

SUFIJO = {TipoIngreso.REGISTRADO: 'registrados', TipoIngreso.INVITADO: 'invitados'}


def hoy():
    """Fecha local actual. Las pruebas la reemplazan."""
    return timezone.localdate()


def _inicio_del_dia(fecha, zona):
    return datetime.combine(fecha, time.min, tzinfo=zona)


def _por_dia_y_tipo(campo_hora, inicio, fin, zona, **agregados):
    """Tickets con `campo_hora` en [inicio, fin), agrupados por día local y tipo_ingreso."""
    return (
        Ticket.objects.filter(**{f'{campo_hora}__gte': inicio, f'{campo_hora}__lt': fin})
        .annotate(dia=TruncDate(campo_hora, tzinfo=zona))
        .values('dia', 'tipo_ingreso')
        .annotate(**agregados)
        .order_by()
    )


def ingresos_por_dia(desde, hasta):
    """Devuelve `{desde, hasta, dias: [...], totales: {...}}`.

    `dias` trae una fila por cada fecha del rango (incluidos los días sin movimiento,
    en cero), de la más antigua a la más reciente.
    """
    zona = timezone.get_current_timezone()
    inicio = _inicio_del_dia(desde, zona)
    fin = _inicio_del_dia(hasta + timedelta(days=1), zona)

    dias = {}
    fecha = desde
    while fecha <= hasta:
        dias[fecha] = {'fecha': fecha, **{campo: 0 for campo in CAMPOS_DIA}}
        fecha += timedelta(days=1)

    for fila in _por_dia_y_tipo('hora_entrada', inicio, fin, zona, n=Count('id')):
        dia = dias[fila['dia']]
        dia['ingresos'] += fila['n']
        dia[f"ingresos_{SUFIJO[fila['tipo_ingreso']]}"] += fila['n']

    cobros = _por_dia_y_tipo(
        'hora_salida', inicio, fin, zona, total=Sum('valor_cobrado')
    )
    for fila in cobros:
        total = fila['total'] or 0
        dia = dias[fila['dia']]
        dia['cobrado'] += total
        dia[f"cobrado_{SUFIJO[fila['tipo_ingreso']]}"] += total

    filas = list(dias.values())
    return {
        'desde': desde,
        'hasta': hasta,
        'dias': filas,
        'totales': {campo: sum(f[campo] for f in filas) for campo in CAMPOS_DIA},
    }
