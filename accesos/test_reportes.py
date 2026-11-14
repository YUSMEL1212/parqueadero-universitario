"""Pruebas del reporte de ingresos por día (GET /api/reportes/ingresos)."""

from datetime import date, datetime
from unittest import mock
from zoneinfo import ZoneInfo

from rest_framework import status
from rest_framework.test import APITestCase

from usuarios.models import Rol, Usuario
from vehiculos.models import Vehiculo

from .models import Ticket
from .test_porteria import crear_guarda
from .tests import crear_conductor

URL_REPORTE = '/api/reportes/ingresos'
BOGOTA = ZoneInfo('America/Bogota')


def hora(dia, hh, mm=0):
    """Hora local de Bogotá el `dia` de noviembre de 2026."""
    return datetime(2026, 11, dia, hh, mm, tzinfo=BOGOTA)


class ReporteIngresosTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        rol, _ = Rol.objects.get_or_create(nombre=Rol.Nombre.ADMINISTRADOR)
        cls.admin = Usuario.objects.create_user(
            'ana@parqueadero.test', 'Parqueo.Seguro2026', rol=rol, nombre='Ana Admin'
        )
        cls.guarda = crear_guarda('guarda@parqueadero.test')
        cls.laura = crear_conductor('laura@unimonserrate.edu.co')
        cls.mario = crear_conductor('mario@unimonserrate.edu.co')
        cls.carro_laura = Vehiculo.objects.create(usuario=cls.laura, placa='ABC123', tipo='carro')
        cls.moto_mario = Vehiculo.objects.create(usuario=cls.mario, placa='XYZ12A', tipo='moto')
        cls.carro_invitado = Vehiculo.objects.create(usuario=None, placa='INV001', tipo='carro')

        # 10 nov: Laura entra y sale (7000); el invitado entra a las 23:30 y sale el 11.
        cls.ticket(cls.laura, cls.carro_laura, hora(10, 8), hora(10, 9), 7000)
        cls.ticket(None, cls.carro_invitado, hora(10, 23, 30), hora(11, 1), 7000)
        # 11 nov: Mario con mensualidad (0) y Laura más de 2 h (12000).
        cls.ticket(cls.mario, cls.moto_mario, hora(11, 7), hora(11, 8), 0)
        cls.ticket(cls.laura, cls.carro_laura, hora(11, 10), hora(11, 14), 12000)
        # 12 nov: el invitado vuelve y sigue adentro (sin cobro todavía).
        cls.ticket(None, cls.carro_invitado, hora(12, 9), None, None)

    @classmethod
    def ticket(cls, usuario, vehiculo, entrada, salida, valor):
        return Ticket.objects.create(
            vehiculo=vehiculo,
            usuario=usuario,
            guarda=cls.guarda,
            tipo_ingreso='invitado' if usuario is None else 'registrado',
            metodo_ingreso='manual' if usuario is None else 'qr',
            hora_entrada=entrada,
            hora_salida=salida,
            valor_cobrado=valor,
            codigo_salida='K7MP2QXA' if usuario is None else None,
        )

    def setUp(self):
        self.client.force_authenticate(self.admin)

    def consultar(self, **params):
        return self.client.get(URL_REPORTE, params)

    def test_un_dia_por_fila_con_ingresos_cobros_y_desglose(self):
        resp = self.consultar(desde='2026-11-10', hasta='2026-11-12')

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['desde'], '2026-11-10')
        self.assertEqual(resp.data['hasta'], '2026-11-12')
        dias = {d['fecha']: d for d in resp.data['dias']}
        self.assertEqual(list(dias), ['2026-11-10', '2026-11-11', '2026-11-12'])

        # El ingreso del invitado de las 23:30 cuenta el 10 (hora de Colombia, no UTC)...
        self.assertEqual(
            dias['2026-11-10'],
            {
                'fecha': '2026-11-10',
                'ingresos': 2,
                'ingresos_registrados': 1,
                'ingresos_invitados': 1,
                'cobrado': 7000,
                'cobrado_registrados': 7000,
                'cobrado_invitados': 0,
            },
        )
        # ...y su cobro, el 11, el día en que salió.
        self.assertEqual(
            dias['2026-11-11'],
            {
                'fecha': '2026-11-11',
                'ingresos': 2,
                'ingresos_registrados': 2,
                'ingresos_invitados': 0,
                'cobrado': 19000,
                'cobrado_registrados': 12000,
                'cobrado_invitados': 7000,
            },
        )
        # Un vehículo adentro cuenta como ingreso pero aún no suma cobro.
        self.assertEqual(dias['2026-11-12']['ingresos_invitados'], 1)
        self.assertEqual(dias['2026-11-12']['cobrado'], 0)

    def test_totales_del_rango(self):
        resp = self.consultar(desde='2026-11-10', hasta='2026-11-12')

        self.assertEqual(
            resp.data['totales'],
            {
                'ingresos': 5,
                'ingresos_registrados': 3,
                'ingresos_invitados': 2,
                'cobrado': 26000,
                'cobrado_registrados': 19000,
                'cobrado_invitados': 7000,
            },
        )

    def test_incluye_los_dias_sin_movimiento_en_cero(self):
        resp = self.consultar(desde='2026-11-01', hasta='2026-11-03')

        self.assertEqual(len(resp.data['dias']), 3)
        for dia in resp.data['dias']:
            self.assertEqual(dia['ingresos'], 0)
            self.assertEqual(dia['cobrado'], 0)
        self.assertEqual(resp.data['totales']['cobrado'], 0)

    def test_el_rango_corta_en_la_medianoche_local(self):
        # Solo el 11: no entra el ingreso del 10 a las 23:30, sí su cobro de la 1:00.
        resp = self.consultar(desde='2026-11-11', hasta='2026-11-11')

        self.assertEqual(resp.data['totales']['ingresos'], 2)
        self.assertEqual(resp.data['totales']['cobrado_invitados'], 7000)

    def test_sin_fechas_devuelve_los_ultimos_siete_dias(self):
        with mock.patch('accesos.reportes.hoy', return_value=date(2026, 11, 12)):
            resp = self.consultar()

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['desde'], '2026-11-06')
        self.assertEqual(resp.data['hasta'], '2026-11-12')
        self.assertEqual(len(resp.data['dias']), 7)
        self.assertEqual(resp.data['totales']['ingresos'], 5)

    def test_rechaza_fechas_invalidas_o_rango_al_reves(self):
        self.assertEqual(
            self.consultar(desde='2026-11-31').status_code, status.HTTP_400_BAD_REQUEST
        )
        resp = self.consultar(desde='2026-11-12', hasta='2026-11-10')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('desde', resp.data)

    def test_rechaza_un_rango_de_mas_de_un_ano(self):
        resp = self.consultar(desde='2025-01-01', hasta='2026-11-12')

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('desde', resp.data)

    def test_solo_el_administrador_ve_el_reporte(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.consultar().status_code, status.HTTP_401_UNAUTHORIZED)
        for usuario in (self.guarda, self.laura):
            self.client.force_authenticate(usuario)
            self.assertEqual(self.consultar().status_code, status.HTTP_403_FORBIDDEN)
