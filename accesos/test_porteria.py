"""Pruebas de los servicios de portería (entrada, salida, invitados) y del historial.

Cubren los cuatro flujos del TDR:
  1. Ingreso y salida con mensualidad activa (cobro 0).
  2. Ingreso y salida por fracción (hasta_2h y mas_2h).
  3. Ingreso de invitado con cobro de tarifa completa.
  4. Rechazo del segundo vehículo simultáneo del mismo conductor.
"""

from datetime import timedelta
from unittest import mock

from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from pagos.models import Pago
from usuarios.models import Rol, Usuario
from vehiculos.models import Vehiculo

from .models import Ticket
from .porteria import ALFABETO_CODIGO
from .qr import generar_token
from .test_qr import LLAVE_PRUEBA, Reloj, b64_a_bytes, bytes_a_b64, crear_conductor
from .tests import cargar_tarifas_del_seed, crear_mensualidad

URL_ENTRADA = '/api/accesos/entrada'
URL_SALIDA = '/api/accesos/salida'
URL_CONFIRMAR = '/api/accesos/salida/confirmar'
URL_INVITADOS = '/api/accesos/invitados'
URL_HISTORIAL = '/api/accesos/historial'


def crear_guarda(email):
    rol, _ = Rol.objects.get_or_create(nombre=Rol.Nombre.GUARDA)
    return Usuario.objects.create_user(email, 'Parqueo.Seguro2026', rol=rol, nombre='Guarda')


@override_settings(QR_SECRET_KEY=LLAVE_PRUEBA)
class PorteriaTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cargar_tarifas_del_seed()
        cls.guarda = crear_guarda('guarda@parqueadero.test')
        cls.laura = crear_conductor('laura@unimonserrate.edu.co')
        cls.carro = Vehiculo.objects.create(usuario=cls.laura, placa='ABC123', tipo='carro')

    def setUp(self):
        # Un solo reloj para el token QR y para las horas de entrada y salida.
        self.reloj = Reloj(timezone.now().replace(microsecond=0))
        for objetivo in ('accesos.qr.ahora', 'accesos.porteria.ahora'):
            parche = mock.patch(objetivo, self.reloj)
            parche.start()
            self.addCleanup(parche.stop)
        self.client.force_authenticate(self.guarda)

    # Atajos: cada llamada genera un QR nuevo, como haría la PWA del conductor.
    def entrar(self, vehiculo):
        return self.client.post(
            URL_ENTRADA, {'token': generar_token(vehiculo.usuario, vehiculo)}, format='json'
        )

    def liquidar(self, vehiculo):
        return self.client.post(
            URL_SALIDA, {'token': generar_token(vehiculo.usuario, vehiculo)}, format='json'
        )

    def confirmar(self, ticket_id, **extra):
        return self.client.post(URL_CONFIRMAR, {'ticket_id': ticket_id, **extra}, format='json')


class FlujoMensualidadTests(PorteriaTestCase):
    """TDR 1: el conductor con mensualidad activa entra y sale sin pagar."""

    def test_ingreso_y_salida_con_mensualidad_cobra_cero(self):
        crear_mensualidad(self.laura, 'carro', vence_en=self.reloj.momento + timedelta(days=10))
        pagos_antes = Pago.objects.count()

        resp = self.entrar(self.carro)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['metodo_ingreso'], 'qr')
        self.assertEqual(resp.data['tipo_ingreso'], 'registrado')
        self.assertEqual(resp.data['placa'], 'ABC123')
        ticket = Ticket.objects.get(pk=resp.data['id'])
        self.assertEqual(ticket.usuario, self.laura)
        self.assertEqual(ticket.guarda, self.guarda)
        self.assertEqual(ticket.hora_entrada, self.reloj.momento)

        self.reloj.avanzar(9 * 3600)  # 9 horas: sin mensualidad serían 12.000
        liq = self.liquidar(self.carro)
        self.assertEqual(liq.status_code, status.HTTP_200_OK, liq.data)
        self.assertEqual(liq.data['valor'], 0)
        self.assertEqual(liq.data['motivo'], 'mensualidad_activa')
        self.assertEqual(liq.data['minutos'], 540)
        self.assertIsNone(liq.data['tarifa'])

        resp = self.confirmar(liq.data['ticket_id'])
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        ticket.refresh_from_db()
        self.assertEqual(ticket.hora_salida, self.reloj.momento)
        self.assertEqual(ticket.minutos, 540)
        self.assertEqual(ticket.valor_cobrado, 0)
        self.assertIsNone(ticket.tarifa)
        self.assertIsNone(ticket.pago)
        self.assertEqual(Pago.objects.count(), pagos_antes)  # sin cobro, sin pago

    def test_mensualidad_de_moto_no_cubre_el_carro(self):
        crear_mensualidad(self.laura, 'moto', vence_en=self.reloj.momento + timedelta(days=10))
        self.entrar(self.carro)
        self.reloj.avanzar(30 * 60)

        liq = self.liquidar(self.carro)
        self.assertEqual(liq.data['valor'], 7000)
        self.assertEqual(liq.data['motivo'], 'hasta_2h')


class FlujoFraccionTests(PorteriaTestCase):
    """TDR 2: sin mensualidad, se cobra la fracción según los minutos."""

    def test_ingreso_y_salida_hasta_2h(self):
        ticket_id = self.entrar(self.carro).data['id']
        self.reloj.avanzar(90 * 60)

        liq = self.liquidar(self.carro)
        self.assertEqual(liq.status_code, status.HTTP_200_OK, liq.data)
        self.assertEqual(str(liq.data['ticket_id']), ticket_id)
        self.assertEqual(liq.data['minutos'], 90)
        self.assertEqual(liq.data['valor'], 7000)
        self.assertEqual(liq.data['motivo'], 'hasta_2h')
        self.assertEqual(liq.data['tarifa']['concepto'], 'hasta_2h')

        resp = self.confirmar(ticket_id, metodo_pago='tarjeta')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['valor_cobrado'], 7000)
        self.assertEqual(resp.data['metodo_pago'], 'tarjeta')

        ticket = Ticket.objects.select_related('tarifa', 'pago').get(pk=ticket_id)
        self.assertEqual(ticket.minutos, 90)
        self.assertEqual(ticket.valor_cobrado, 7000)
        self.assertEqual(ticket.tarifa.concepto, 'hasta_2h')
        self.assertEqual(ticket.pago.valor, 7000)
        self.assertEqual(ticket.pago.concepto, Pago.Concepto.FRACCION)
        self.assertEqual(ticket.pago.estado, Pago.Estado.APROBADO)
        self.assertEqual(ticket.pago.metodo, Pago.Metodo.TARJETA)
        self.assertEqual(ticket.pago.usuario, self.laura)

    def test_ingreso_y_salida_mas_de_2h_en_moto(self):
        moto = Vehiculo.objects.create(usuario=self.laura, placa='XYZ45K', tipo='moto')
        ticket_id = self.entrar(moto).data['id']
        self.reloj.avanzar(150 * 60)

        self.assertEqual(self.liquidar(moto).data['valor'], 9000)
        resp = self.confirmar(ticket_id)
        self.assertEqual(resp.data['valor_cobrado'], 9000)
        self.assertEqual(resp.data['tarifa']['concepto'], 'mas_2h')
        self.assertEqual(resp.data['metodo_pago'], 'efectivo')  # método por defecto

    def test_la_liquidacion_no_cierra_el_ticket(self):
        ticket_id = self.entrar(self.carro).data['id']
        self.reloj.avanzar(60 * 60)
        self.liquidar(self.carro)
        self.liquidar(self.carro)

        ticket = Ticket.objects.get(pk=ticket_id)
        self.assertIsNone(ticket.hora_salida)
        self.assertIsNone(ticket.valor_cobrado)
        self.assertFalse(Pago.objects.exists())

    def test_la_confirmacion_recalcula_con_la_hora_real(self):
        ticket_id = self.entrar(self.carro).data['id']
        self.reloj.avanzar(119 * 60)
        self.assertEqual(self.liquidar(self.carro).data['valor'], 7000)

        self.reloj.avanzar(2 * 60)  # el guarda tardó 2 minutos en cobrar
        resp = self.confirmar(ticket_id)
        self.assertEqual(resp.data['minutos'], 121)
        self.assertEqual(resp.data['valor_cobrado'], 12000)

    def test_no_se_confirma_dos_veces(self):
        ticket_id = self.entrar(self.carro).data['id']
        self.reloj.avanzar(10 * 60)
        self.assertEqual(self.confirmar(ticket_id).status_code, status.HTTP_200_OK)

        resp = self.confirmar(ticket_id)
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(resp.data['codigo'], 'ticket_cerrado')
        self.assertEqual(Pago.objects.count(), 1)

    def test_salida_sin_vehiculo_adentro(self):
        resp = self.liquidar(self.carro)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(resp.data['codigo'], 'sin_ticket_abierto')


class FlujoInvitadoTests(PorteriaTestCase):
    """TDR 3: el invitado entra con placa, recibe un código y paga tarifa completa."""

    def test_ingreso_de_invitado_y_cobro_completo(self):
        resp = self.client.post(URL_INVITADOS, {'tipo': 'carro', 'placa': 'ghj-456'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['placa'], 'GHJ456')
        self.assertEqual(resp.data['tipo_ingreso'], 'invitado')
        self.assertIsNone(resp.data['conductor'])

        codigo = resp.data['codigo_salida']
        self.assertEqual(len(codigo), 8)
        self.assertTrue(set(codigo) <= set(ALFABETO_CODIGO))

        vehiculo = Vehiculo.objects.get(placa='GHJ456')
        self.assertIsNone(vehiculo.usuario)
        self.assertEqual(vehiculo.tipo, 'carro')
        ticket = Ticket.objects.get(pk=resp.data['id'])
        self.assertIsNone(ticket.usuario)
        self.assertEqual(ticket.guarda, self.guarda)
        self.assertEqual(ticket.tipo_ingreso, Ticket.TipoIngreso.INVITADO)

        self.reloj.avanzar(3 * 3600)
        liq = self.client.post(URL_SALIDA, {'codigo_salida': codigo.lower()}, format='json')
        self.assertEqual(liq.status_code, status.HTTP_200_OK, liq.data)
        self.assertEqual(liq.data['valor'], 12000)
        self.assertEqual(liq.data['motivo'], 'mas_2h')

        resp = self.confirmar(liq.data['ticket_id'])
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        ticket.refresh_from_db()
        self.assertEqual(ticket.valor_cobrado, 12000)
        self.assertEqual(ticket.minutos, 180)
        self.assertEqual(ticket.tarifa.concepto, 'mas_2h')
        self.assertIsNone(ticket.pago.usuario)
        self.assertEqual(ticket.pago.valor, 12000)

    def test_invitado_que_vuelve_reutiliza_el_vehiculo(self):
        primero = self.client.post(URL_INVITADOS, {'tipo': 'moto', 'placa': 'KLM12N'}, format='json')
        self.reloj.avanzar(20 * 60)
        self.confirmar(primero.data['id'])

        segundo = self.client.post(URL_INVITADOS, {'tipo': 'moto', 'placa': 'KLM12N'}, format='json')
        self.assertEqual(segundo.status_code, status.HTTP_201_CREATED, segundo.data)
        self.assertEqual(Vehiculo.objects.filter(placa='KLM12N').count(), 1)

    def test_invitado_ya_adentro_es_rechazado(self):
        self.client.post(URL_INVITADOS, {'tipo': 'moto', 'placa': 'KLM12N'}, format='json')
        resp = self.client.post(URL_INVITADOS, {'tipo': 'moto', 'placa': 'KLM12N'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(resp.data['codigo'], 'vehiculo_adentro')

    def test_placa_de_conductor_registrado_no_entra_como_invitado(self):
        resp = self.client.post(URL_INVITADOS, {'tipo': 'carro', 'placa': 'ABC123'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(resp.data['codigo'], 'placa_registrada')

    def test_placa_que_no_corresponde_al_tipo(self):
        resp = self.client.post(URL_INVITADOS, {'tipo': 'moto', 'placa': 'ABC123'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('placa', resp.data)

    def test_codigo_de_salida_inexistente(self):
        resp = self.client.post(URL_SALIDA, {'codigo_salida': 'ZZZZZZZZ'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class SegundoVehiculoTests(PorteriaTestCase):
    """TDR 4: un conductor no puede tener dos vehículos adentro a la vez."""

    def test_rechaza_el_segundo_vehiculo_simultaneo(self):
        moto = Vehiculo.objects.create(usuario=self.laura, placa='XYZ45K', tipo='moto')
        self.assertEqual(self.entrar(self.carro).status_code, status.HTTP_201_CREATED)

        resp = self.entrar(moto)
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(resp.data['codigo'], 'vehiculo_adentro')
        self.assertEqual(resp.data['placa_adentro'], 'ABC123')
        self.assertEqual(Ticket.objects.filter(usuario=self.laura).count(), 1)

    def test_el_mismo_vehiculo_no_entra_dos_veces(self):
        self.entrar(self.carro)
        self.assertEqual(self.entrar(self.carro).status_code, status.HTTP_409_CONFLICT)

    def test_tras_salir_puede_entrar_con_otro_vehiculo(self):
        moto = Vehiculo.objects.create(usuario=self.laura, placa='XYZ45K', tipo='moto')
        ticket_id = self.entrar(self.carro).data['id']
        self.reloj.avanzar(15 * 60)
        self.confirmar(ticket_id)

        self.assertEqual(self.entrar(moto).status_code, status.HTTP_201_CREATED)

    def test_otro_conductor_si_puede_entrar(self):
        pedro = crear_conductor('pedro@unimonserrate.edu.co')
        carro_pedro = Vehiculo.objects.create(usuario=pedro, placa='DEF456', tipo='carro')
        self.entrar(self.carro)
        self.assertEqual(self.entrar(carro_pedro).status_code, status.HTTP_201_CREATED)


class QREnPorteriaTests(PorteriaTestCase):
    def test_qr_vencido_es_rechazado(self):
        token = generar_token(self.laura, self.carro)
        self.reloj.avanzar(61)
        resp = self.client.post(URL_ENTRADA, {'token': token}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['codigo'], 'qr_vencido')
        self.assertFalse(Ticket.objects.exists())

    def test_qr_alterado_es_rechazado(self):
        crudo = bytearray(b64_a_bytes(generar_token(self.laura, self.carro)))
        crudo[20] ^= 0x01
        resp = self.client.post(URL_ENTRADA, {'token': bytes_a_b64(bytes(crudo))}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['codigo'], 'qr_alterado')

    def test_salida_pide_token_o_codigo(self):
        self.assertEqual(
            self.client.post(URL_SALIDA, {}, format='json').status_code,
            status.HTTP_400_BAD_REQUEST,
        )


class PermisosPorteriaTests(PorteriaTestCase):
    def test_solo_el_guarda_usa_la_porteria(self):
        self.client.force_authenticate(self.laura)
        token = generar_token(self.laura, self.carro)
        for url, datos in [
            (URL_ENTRADA, {'token': token}),
            (URL_SALIDA, {'token': token}),
            (URL_CONFIRMAR, {'ticket_id': '0c9e7f1a-2b3d-4e5f-8a9b-1c2d3e4f5a6b'}),
            (URL_INVITADOS, {'tipo': 'carro', 'placa': 'GHJ456'}),
        ]:
            with self.subTest(url=url):
                resp = self.client.post(url, datos, format='json')
                self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Ticket.objects.exists())

    def test_sin_autenticar_responde_401(self):
        self.client.force_authenticate(None)
        resp = self.client.post(URL_ENTRADA, {'token': 'x'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class HistorialTests(PorteriaTestCase):
    def test_conductor_ve_solo_sus_recibos_cerrados(self):
        pedro = crear_conductor('pedro@unimonserrate.edu.co')
        carro_pedro = Vehiculo.objects.create(usuario=pedro, placa='DEF456', tipo='carro')

        primero = self.entrar(self.carro).data['id']
        self.reloj.avanzar(90 * 60)
        self.confirmar(primero)
        self.reloj.avanzar(3600)
        segundo = self.entrar(self.carro).data['id']
        self.reloj.avanzar(130 * 60)
        self.confirmar(segundo)
        self.entrar(self.carro)  # adentro: no aparece todavía
        self.entrar(carro_pedro)  # de otro conductor: no aparece

        self.client.force_authenticate(self.laura)
        resp = self.client.get(URL_HISTORIAL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual([r['id'] for r in resp.data], [segundo, primero])  # más reciente primero

        recibo = resp.data[0]
        self.assertEqual(recibo['placa'], 'ABC123')
        self.assertEqual(recibo['minutos'], 130)
        self.assertEqual(recibo['valor_cobrado'], 12000)
        self.assertIsNotNone(recibo['hora_entrada'])
        self.assertIsNotNone(recibo['hora_salida'])

    def test_el_guarda_no_tiene_historial(self):
        self.assertEqual(self.client.get(URL_HISTORIAL).status_code, status.HTTP_403_FORBIDDEN)
