"""Pruebas de la app iot: sensores, cámara LPR, cupos, WebSocket y reporte de sensores."""

from datetime import timedelta
from unittest import mock

from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from accesos.models import Ticket
from accesos.tests import crear_conductor, crear_mensualidad
from config.asgi import application
from usuarios.models import Rol, Usuario
from vehiculos.models import Vehiculo

from .models import Bahia, EventoSensor, LecturaLPR, Sensor
from .servicios import GRUPO_CUPOS

LLAVE = 'llave-de-prueba-iot'
URL_ESTADO = '/api/iot/sensores/estado'
URL_SENSORES = '/api/iot/sensores'
URL_CUPOS = '/api/iot/cupos'
URL_LPR = '/api/lpr/lecturas'


def crear_bahias():
    """C-01 y C-02 de carro, M-01 de moto, cada una con su sensor (como el seed)."""
    sensores = {}
    for codigo, tipo in (('C-01', 'carro'), ('C-02', 'carro'), ('M-01', 'moto')):
        bahia = Bahia.objects.create(codigo=codigo, tipo_vehiculo=tipo)
        uid = f"ESP32-{codigo.replace('-', '')}"
        sensores[uid] = Sensor.objects.create(bahia=bahia, device_uid=uid)
    return sensores


@override_settings(IOT_DEVICE_KEY=LLAVE)
class DispositivoTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sensores = crear_bahias()

    def setUp(self):
        self.momento = timezone.now().replace(microsecond=0)
        parche = mock.patch('iot.servicios.ahora', lambda: self.momento)
        parche.start()
        self.addCleanup(parche.stop)

    def enviar(self, url, datos, llave=LLAVE):
        headers = {'X-Device-Key': llave} if llave is not None else {}
        return self.client.post(url, datos, format='json', headers=headers)


class SensorEstadoTests(DispositivoTestCase):
    def setUp(self):
        super().setUp()
        # Un canal suscrito al grupo de cupos, para ver lo que se emite por WebSocket.
        self.capa = get_channel_layer()
        async_to_sync(self.capa.flush)()
        self.canal = async_to_sync(self.capa.new_channel)()
        async_to_sync(self.capa.group_add)(GRUPO_CUPOS, self.canal)

    def test_mensaje_de_ocupacion_cambia_la_bahia(self):
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.enviar(
                URL_ESTADO,
                {
                    'device_uid': 'ESP32-C01',
                    'ocupado': True,
                    'distancia_cm': 42,
                    'ts': '2026-11-13T09:10:00Z',
                },
            )

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['codigo'], 'C-01')
        self.assertEqual(resp.data['estado'], 'ocupada')
        self.assertEqual(Bahia.objects.get(codigo='C-01').estado, Bahia.Estado.OCUPADA)

        sensor = Sensor.objects.get(device_uid='ESP32-C01')
        self.assertEqual(sensor.ultimo_pulso, self.momento)
        evento = EventoSensor.objects.get(sensor=sensor)
        self.assertTrue(evento.ocupado)
        self.assertEqual(evento.distancia_cm, 42)

        # Se emitió el nuevo conteo: queda 1 carro libre (C-02) y 1 moto.
        mensaje = async_to_sync(self.capa.receive)(self.canal)
        self.assertEqual(mensaje['type'], 'cupos.actualizados')
        self.assertEqual(mensaje['cupos']['libres'], {'carro': 1, 'moto': 1})

    def test_el_endpoint_emite_una_sola_vez(self):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            self.enviar(URL_ESTADO, {'device_uid': 'ESP32-C01', 'ocupado': True})
        # La señal es la única que emite: el servicio ya no registra su propio envío.
        self.assertEqual(len(callbacks), 1)

    def test_bahia_que_se_libera(self):
        Bahia.objects.filter(codigo='M-01').update(estado=Bahia.Estado.OCUPADA)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.enviar(URL_ESTADO, {'device_uid': 'ESP32-M01', 'ocupado': False})
        self.assertEqual(resp.data['estado'], 'libre')
        mensaje = async_to_sync(self.capa.receive)(self.canal)
        self.assertEqual(mensaje['cupos']['libres'], {'carro': 2, 'moto': 1})

    def test_mensaje_repetido_no_emite(self):
        Bahia.objects.filter(codigo='C-01').update(estado=Bahia.Estado.OCUPADA)
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            resp = self.enviar(URL_ESTADO, {'device_uid': 'ESP32-C01', 'ocupado': True})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(callbacks, [])
        self.assertEqual(EventoSensor.objects.count(), 1)  # el evento sí se guarda

    def test_bahia_fuera_de_servicio_no_cambia(self):
        Bahia.objects.filter(codigo='C-01').update(estado=Bahia.Estado.FUERA_SERVICIO)
        resp = self.enviar(URL_ESTADO, {'device_uid': 'ESP32-C01', 'ocupado': True})
        self.assertEqual(resp.data['estado'], 'fuera_servicio')

    def test_latido_solo_actualiza_el_pulso(self):
        bahia_antes = Bahia.objects.get(codigo='C-01')

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            resp = self.enviar(
                URL_ESTADO,
                {'device_uid': 'ESP32-C01', 'latido': True, 'ts': '2026-11-13T09:10:30Z'},
            )

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        sensor = Sensor.objects.get(device_uid='ESP32-C01')
        self.assertEqual(sensor.ultimo_pulso, self.momento)
        bahia = Bahia.objects.get(codigo='C-01')
        self.assertEqual(bahia.estado, Bahia.Estado.LIBRE)
        self.assertEqual(bahia.actualizado_en, bahia_antes.actualizado_en)
        self.assertFalse(EventoSensor.objects.exists())
        self.assertEqual(callbacks, [])

    def test_llave_de_dispositivo_equivocada_da_401(self):
        resp = self.enviar(
            URL_ESTADO, {'device_uid': 'ESP32-C01', 'ocupado': True}, llave='otra-llave'
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Bahia.objects.get(codigo='C-01').estado, Bahia.Estado.LIBRE)
        self.assertIsNone(Sensor.objects.get(device_uid='ESP32-C01').ultimo_pulso)
        self.assertFalse(EventoSensor.objects.exists())

    def test_sin_llave_da_401(self):
        resp = self.enviar(URL_ESTADO, {'device_uid': 'ESP32-C01', 'ocupado': True}, llave=None)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(IOT_DEVICE_KEY='')
    def test_sin_llave_configurada_rechaza_todo(self):
        resp = self.enviar(URL_ESTADO, {'device_uid': 'ESP32-C01', 'ocupado': True}, llave='')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_jwt_no_sirve_para_los_sensores(self):
        token = RefreshToken.for_user(crear_admin()).access_token
        resp = self.client.post(
            URL_ESTADO,
            {'device_uid': 'ESP32-C01', 'ocupado': True},
            format='json',
            headers={'Authorization': f'Bearer {token}'},
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_sensor_desconocido_da_404(self):
        resp = self.enviar(URL_ESTADO, {'device_uid': 'ESP32-X99', 'ocupado': True})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_mensaje_sin_ocupado_ni_latido_da_400(self):
        resp = self.enviar(URL_ESTADO, {'device_uid': 'ESP32-C01'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('ocupado', resp.data)


def crear_admin():
    rol, _ = Rol.objects.get_or_create(nombre=Rol.Nombre.ADMINISTRADOR)
    return Usuario.objects.create_user(
        'admin@parqueadero.test', 'Parqueo.Seguro2026', rol=rol, nombre='Admin'
    )


class ReporteSensoresTests(DispositivoTestCase):
    def test_sensor_con_pulso_viejo_sale_desconectado(self):
        Sensor.objects.filter(device_uid='ESP32-C01').update(
            ultimo_pulso=self.momento - timedelta(seconds=91)
        )
        Sensor.objects.filter(device_uid='ESP32-C02').update(
            ultimo_pulso=self.momento - timedelta(seconds=30)
        )
        # ESP32-M01 nunca ha enviado nada.
        self.client.force_authenticate(crear_admin())

        resp = self.client.get(URL_SENSORES)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        filas = {f['device_uid']: f for f in resp.data['bahias']}
        self.assertEqual(filas['ESP32-C01']['estado_sensor'], 'desconectado')
        self.assertEqual(filas['ESP32-C01']['segundos_sin_pulso'], 91)
        self.assertEqual(filas['ESP32-C01']['bahia'], 'C-01')
        self.assertEqual(filas['ESP32-C02']['estado_sensor'], 'ok')
        self.assertEqual(filas['ESP32-M01']['estado_sensor'], 'desconectado')
        self.assertIsNone(filas['ESP32-M01']['ultimo_pulso'])
        self.assertEqual(resp.data['desconectados'], 2)

    def test_exactamente_90_segundos_sigue_ok(self):
        Sensor.objects.filter(device_uid='ESP32-C01').update(
            ultimo_pulso=self.momento - timedelta(seconds=90)
        )
        self.client.force_authenticate(crear_admin())
        resp = self.client.get(URL_SENSORES)
        fila = next(f for f in resp.data['bahias'] if f['device_uid'] == 'ESP32-C01')
        self.assertEqual(fila['estado_sensor'], 'ok')

    def test_solo_administrador(self):
        self.client.force_authenticate(crear_conductor('laura@unimonserrate.edu.co'))
        self.assertEqual(self.client.get(URL_SENSORES).status_code, status.HTTP_403_FORBIDDEN)


class CuposTests(DispositivoTestCase):
    def test_conteo_de_libres_sin_autenticacion(self):
        Bahia.objects.filter(codigo='C-02').update(estado=Bahia.Estado.OCUPADA)
        resp = self.client.get(URL_CUPOS)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['libres'], {'carro': 1, 'moto': 1})


class LecturaLPRTests(DispositivoTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.laura = crear_conductor('laura@unimonserrate.edu.co')
        cls.carro = Vehiculo.objects.create(usuario=cls.laura, placa='ABC123', tipo='carro')

    def leer(self, placa='ABC123', confianza=0.94, **extra):
        return self.enviar(
            URL_LPR,
            {
                'camara_id': 'CAM-ENTRADA',
                'placa': placa,
                'confianza': confianza,
                'foto': 'https://fotos.test/lpr/1.jpg',
                **extra,
            },
        )

    def test_lpr_con_mensualidad_activa_abre(self):
        crear_mensualidad(self.laura, 'carro', vence_en=self.momento + timedelta(days=10))

        resp = self.leer()

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertTrue(resp.data['abrir'])
        self.assertEqual(resp.data['motivo'], 'mensualidad_activa')
        ticket = Ticket.objects.get(pk=resp.data['ticket_id'])
        self.assertEqual(ticket.metodo_ingreso, Ticket.MetodoIngreso.LPR)
        self.assertEqual(ticket.tipo_ingreso, Ticket.TipoIngreso.REGISTRADO)
        self.assertEqual(ticket.usuario, self.laura)
        self.assertEqual(ticket.vehiculo, self.carro)
        self.assertIsNone(ticket.guarda)
        self.assertEqual(ticket.hora_entrada, self.momento)
        self.assertEqual(ticket.foto_ingreso_url, 'https://fotos.test/lpr/1.jpg')

        lectura = LecturaLPR.objects.get()
        self.assertEqual(lectura.resultado, LecturaLPR.Resultado.ABIERTA)
        self.assertEqual(lectura.ticket, ticket)
        self.assertEqual(lectura.placa_leida, 'ABC123')
        self.assertEqual(str(lectura.confianza), '0.94')

    def test_lpr_sin_mensualidad_no_abre_pero_registra_la_lectura(self):
        resp = self.leer()

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(
            resp.data, {'abrir': False, 'motivo': 'sin_mensualidad', 'ticket_id': None}
        )
        self.assertFalse(Ticket.objects.exists())
        lectura = LecturaLPR.objects.get()
        self.assertEqual(lectura.resultado, LecturaLPR.Resultado.RECHAZADA)
        self.assertIsNone(lectura.ticket)
        self.assertEqual(lectura.placa_leida, 'ABC123')

    def test_mensualidad_vencida_no_abre(self):
        crear_mensualidad(self.laura, 'carro', vence_en=self.momento - timedelta(minutes=1))
        self.assertEqual(self.leer().data['motivo'], 'sin_mensualidad')

    def test_mensualidad_de_moto_no_abre_para_el_carro(self):
        crear_mensualidad(self.laura, 'moto', vence_en=self.momento + timedelta(days=10))
        self.assertEqual(self.leer().data['motivo'], 'sin_mensualidad')

    def test_placa_no_registrada(self):
        resp = self.leer(placa='ZZZ999')
        self.assertEqual(resp.data['motivo'], 'placa_no_registrada')
        self.assertEqual(LecturaLPR.objects.get().resultado, LecturaLPR.Resultado.RECHAZADA)

    def test_conductor_ya_adentro_no_abre(self):
        crear_mensualidad(self.laura, 'carro', vence_en=self.momento + timedelta(days=10))
        self.assertTrue(self.leer().data['abrir'])
        resp = self.leer()
        self.assertFalse(resp.data['abrir'])
        self.assertEqual(resp.data['motivo'], 'vehiculo_adentro')
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(LecturaLPR.objects.count(), 2)

    def test_lectura_mala_queda_como_no_leida(self):
        crear_mensualidad(self.laura, 'carro', vence_en=self.momento + timedelta(days=10))
        self.assertEqual(self.leer(placa='').data['motivo'], 'lectura_invalida')
        self.assertEqual(self.leer(confianza=0.40).data['motivo'], 'confianza_baja')
        self.assertFalse(Ticket.objects.exists())
        resultados = set(LecturaLPR.objects.values_list('resultado', flat=True))
        self.assertEqual(resultados, {LecturaLPR.Resultado.NO_LEIDA})

    def test_placa_con_guion_y_minusculas(self):
        crear_mensualidad(self.laura, 'carro', vence_en=self.momento + timedelta(days=10))
        self.assertTrue(self.leer(placa='abc-123').data['abrir'])

    def test_llave_equivocada_da_401(self):
        resp = self.enviar(URL_LPR, {'camara_id': 'CAM-ENTRADA', 'placa': 'ABC123'}, llave='x')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(LecturaLPR.objects.exists())


class BahiaDesdeAdminTests(APITestCase):
    """Un cambio guardado desde el admin de Django también emite por ws/cupos."""

    @classmethod
    def setUpTestData(cls):
        crear_bahias()
        cls.admin = Usuario.objects.create_superuser(
            email='admin@parquing.test', password='x', nombre='Admin'
        )

    def setUp(self):
        self.capa = get_channel_layer()
        async_to_sync(self.capa.flush)()
        self.canal = async_to_sync(self.capa.new_channel)()
        async_to_sync(self.capa.group_add)(GRUPO_CUPOS, self.canal)
        self.client.force_login(self.admin)
        self.bahia = Bahia.objects.get(codigo='C-01')
        self.url = f'/admin/iot/bahia/{self.bahia.pk}/change/'

    def guardar(self, **cambios):
        datos = {
            'codigo': self.bahia.codigo,
            'tipo_vehiculo': self.bahia.tipo_vehiculo,
            'estado': self.bahia.estado,
            **cambios,
        }
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            resp = self.client.post(self.url, datos)
        self.assertEqual(resp.status_code, 302)  # redirige a la lista: se guardó
        return callbacks

    def test_cambio_de_estado_emite(self):
        callbacks = self.guardar(estado=Bahia.Estado.FUERA_SERVICIO)
        self.assertEqual(len(callbacks), 1)
        mensaje = async_to_sync(self.capa.receive)(self.canal)
        self.assertEqual(mensaje['cupos']['libres'], {'carro': 1, 'moto': 1})

    def test_cambio_de_tipo_emite(self):
        callbacks = self.guardar(tipo_vehiculo='moto')
        self.assertEqual(len(callbacks), 1)
        mensaje = async_to_sync(self.capa.receive)(self.canal)
        self.assertEqual(mensaje['cupos']['libres'], {'carro': 1, 'moto': 2})

    def test_guardar_sin_cambios_no_emite(self):
        self.assertEqual(self.guardar(), [])

    def test_cambio_de_codigo_no_emite(self):
        self.assertEqual(self.guardar(codigo='C-99'), [])


@override_settings(IOT_DEVICE_KEY=LLAVE)
class CuposWebSocketTests(TransactionTestCase):
    """Prueba de punta a punta: un sensor cambia una bahía y el WebSocket lo recibe."""

    def setUp(self):
        crear_bahias()
        async_to_sync(get_channel_layer().flush)()

    async def test_al_conectar_recibe_el_estado_y_luego_los_cambios(self):
        ws = WebsocketCommunicator(application, '/ws/cupos')
        conectado, _ = await ws.connect()
        self.assertTrue(conectado)

        inicial = await ws.receive_json_from()
        self.assertEqual(inicial['tipo'], 'cupos')
        self.assertEqual(inicial['libres'], {'carro': 2, 'moto': 1})

        resp = await sync_to_async(APIClient().post)(
            URL_ESTADO,
            {'device_uid': 'ESP32-M01', 'ocupado': True},
            format='json',
            headers={'X-Device-Key': LLAVE},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        cambio = await ws.receive_json_from()
        self.assertEqual(cambio['libres'], {'carro': 2, 'moto': 0})
        await ws.disconnect()
