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
    """Crea un usuario con rol guarda (y el rol, si no existe).

    Parámetros:
        email (str): correo del guarda.

    Devuelve:
        Usuario: el guarda creado.
    """
    rol, _ = Rol.objects.get_or_create(nombre=Rol.Nombre.GUARDA)
    return Usuario.objects.create_user(email, 'Parqueo.Seguro2026', rol=rol, nombre='Guarda')


@override_settings(QR_SECRET_KEY=LLAVE_PRUEBA)
class PorteriaTestCase(APITestCase):
    """Base de las pruebas de portería: tarifas, guarda autenticado, conductor y reloj."""

    @classmethod
    def setUpTestData(cls):
        """Carga las tarifas del seed y crea el guarda y a Laura con su carro ABC123."""
        cargar_tarifas_del_seed()
        cls.guarda = crear_guarda('guarda@parqueadero.test')
        cls.laura = crear_conductor('laura@unimonserrate.edu.co')
        cls.carro = Vehiculo.objects.create(usuario=cls.laura, placa='ABC123', tipo='carro')

    def setUp(self):
        """Reemplaza el reloj del QR y de la portería y autentica al guarda."""
        # Un solo reloj para el token QR y para las horas de entrada y salida.
        self.reloj = Reloj(timezone.now().replace(microsecond=0))
        for objetivo in ('accesos.qr.ahora', 'accesos.porteria.ahora'):
            parche = mock.patch(objetivo, self.reloj)
            parche.start()
            self.addCleanup(parche.stop)
        self.client.force_authenticate(self.guarda)

    # Atajos: cada llamada genera un QR nuevo, como haría la PWA del conductor.
    def entrar(self, vehiculo):
        """Registra la entrada de `vehiculo` con un QR recién generado.

        Parámetros:
            vehiculo (Vehiculo): vehículo de un conductor registrado.

        Devuelve:
            Response: respuesta de POST /api/accesos/entrada.
        """
        return self.client.post(
            URL_ENTRADA, {'token': generar_token(vehiculo.usuario, vehiculo)}, format='json'
        )

    def liquidar(self, vehiculo):
        """Pide la liquidación de salida de `vehiculo` con un QR recién generado.

        Parámetros:
            vehiculo (Vehiculo): vehículo de un conductor registrado.

        Devuelve:
            Response: respuesta de POST /api/accesos/salida.
        """
        return self.client.post(
            URL_SALIDA, {'token': generar_token(vehiculo.usuario, vehiculo)}, format='json'
        )

    def confirmar(self, ticket_id, **extra):
        """Confirma la salida de un ticket.

        Parámetros:
            ticket_id: id del ticket a cerrar.
            **extra: campos adicionales del cuerpo (p. ej. ``metodo_pago``).

        Devuelve:
            Response: respuesta de POST /api/accesos/salida/confirmar.
        """
        return self.client.post(URL_CONFIRMAR, {'ticket_id': ticket_id, **extra}, format='json')


class FlujoMensualidadTests(PorteriaTestCase):
    """TDR 1: el conductor con mensualidad activa entra y sale sin pagar."""

    def test_ingreso_y_salida_con_mensualidad_cobra_cero(self):
        """Flujo completo con mensualidad: 9 horas adentro, cobro 0, sin tarifa ni pago creado."""
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
        """Con mensualidad solo de moto, el carro paga la fracción hasta_2h."""
        crear_mensualidad(self.laura, 'moto', vence_en=self.reloj.momento + timedelta(days=10))
        self.entrar(self.carro)
        self.reloj.avanzar(30 * 60)

        liq = self.liquidar(self.carro)
        self.assertEqual(liq.data['valor'], 7000)
        self.assertEqual(liq.data['motivo'], 'hasta_2h')


class FlujoFraccionTests(PorteriaTestCase):
    """TDR 2: sin mensualidad, se cobra la fracción según los minutos."""

    def test_ingreso_y_salida_hasta_2h(self):
        """Flujo completo de 90 minutos pagado con tarjeta: ticket y pago guardan hasta_2h (7000)."""
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
        """Moto con 150 minutos paga mas_2h (9000) y, sin indicar método, se registra efectivo."""
        moto = Vehiculo.objects.create(usuario=self.laura, placa='XYZ45K', tipo='moto')
        ticket_id = self.entrar(moto).data['id']
        self.reloj.avanzar(150 * 60)

        self.assertEqual(self.liquidar(moto).data['valor'], 9000)
        resp = self.confirmar(ticket_id)
        self.assertEqual(resp.data['valor_cobrado'], 9000)
        self.assertEqual(resp.data['tarifa']['concepto'], 'mas_2h')
        self.assertEqual(resp.data['metodo_pago'], 'efectivo')  # método por defecto

    def test_la_liquidacion_no_cierra_el_ticket(self):
        """Liquidar varias veces no cierra el ticket ni crea pagos."""
        ticket_id = self.entrar(self.carro).data['id']
        self.reloj.avanzar(60 * 60)
        self.liquidar(self.carro)
        self.liquidar(self.carro)

        ticket = Ticket.objects.get(pk=ticket_id)
        self.assertIsNone(ticket.hora_salida)
        self.assertIsNone(ticket.valor_cobrado)
        self.assertFalse(Pago.objects.exists())

    def test_la_confirmacion_recalcula_con_la_hora_real(self):
        """Si entre liquidar (119 min) y confirmar se pasan los 120 minutos, se cobra mas_2h."""
        ticket_id = self.entrar(self.carro).data['id']
        self.reloj.avanzar(119 * 60)
        self.assertEqual(self.liquidar(self.carro).data['valor'], 7000)

        self.reloj.avanzar(2 * 60)  # el guarda tardó 2 minutos en cobrar
        resp = self.confirmar(ticket_id)
        self.assertEqual(resp.data['minutos'], 121)
        self.assertEqual(resp.data['valor_cobrado'], 12000)

    def test_no_se_confirma_dos_veces(self):
        """Confirmar un ticket ya cerrado responde 409 'ticket_cerrado' y no duplica el pago."""
        ticket_id = self.entrar(self.carro).data['id']
        self.reloj.avanzar(10 * 60)
        self.assertEqual(self.confirmar(ticket_id).status_code, status.HTTP_200_OK)

        resp = self.confirmar(ticket_id)
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(resp.data['codigo'], 'ticket_cerrado')
        self.assertEqual(Pago.objects.count(), 1)

    def test_salida_sin_vehiculo_adentro(self):
        """Liquidar la salida de un conductor sin ticket abierto responde 404 'sin_ticket_abierto'."""
        resp = self.liquidar(self.carro)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(resp.data['codigo'], 'sin_ticket_abierto')


class FlujoInvitadoTests(PorteriaTestCase):
    """TDR 3: el invitado entra con placa, recibe un código y paga tarifa completa."""

    def test_ingreso_de_invitado_y_cobro_completo(self):
        """Flujo completo de invitado: placa normalizada, código de 8 caracteres y 3 h a mas_2h."""
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
        """Un invitado que vuelve tras salir reutiliza el mismo vehículo sin usuario."""
        primero = self.client.post(URL_INVITADOS, {'tipo': 'moto', 'placa': 'KLM12N'}, format='json')
        self.reloj.avanzar(20 * 60)
        self.confirmar(primero.data['id'])

        segundo = self.client.post(URL_INVITADOS, {'tipo': 'moto', 'placa': 'KLM12N'}, format='json')
        self.assertEqual(segundo.status_code, status.HTTP_201_CREATED, segundo.data)
        self.assertEqual(Vehiculo.objects.filter(placa='KLM12N').count(), 1)

    def test_invitado_ya_adentro_es_rechazado(self):
        """Registrar otra vez una placa de invitado que sigue adentro responde 409 'vehiculo_adentro'."""
        self.client.post(URL_INVITADOS, {'tipo': 'moto', 'placa': 'KLM12N'}, format='json')
        resp = self.client.post(URL_INVITADOS, {'tipo': 'moto', 'placa': 'KLM12N'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(resp.data['codigo'], 'vehiculo_adentro')

    def test_placa_de_conductor_registrado_no_entra_como_invitado(self):
        """Una placa de un conductor registrado no puede entrar como invitado (409 'placa_registrada')."""
        resp = self.client.post(URL_INVITADOS, {'tipo': 'carro', 'placa': 'ABC123'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(resp.data['codigo'], 'placa_registrada')

    def test_placa_que_no_corresponde_al_tipo(self):
        """Una placa de carro registrada como moto responde 400 con error en 'placa'."""
        resp = self.client.post(URL_INVITADOS, {'tipo': 'moto', 'placa': 'ABC123'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('placa', resp.data)

    def test_codigo_de_salida_inexistente(self):
        """Un código de salida que no corresponde a ningún invitado adentro responde 404."""
        resp = self.client.post(URL_SALIDA, {'codigo_salida': 'ZZZZZZZZ'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class SegundoVehiculoTests(PorteriaTestCase):
    """TDR 4: un conductor no puede tener dos vehículos adentro a la vez."""

    def test_rechaza_el_segundo_vehiculo_simultaneo(self):
        """Con el carro adentro, la moto del mismo conductor se rechaza (409) indicando la placa."""
        moto = Vehiculo.objects.create(usuario=self.laura, placa='XYZ45K', tipo='moto')
        self.assertEqual(self.entrar(self.carro).status_code, status.HTTP_201_CREATED)

        resp = self.entrar(moto)
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(resp.data['codigo'], 'vehiculo_adentro')
        self.assertEqual(resp.data['placa_adentro'], 'ABC123')
        self.assertEqual(Ticket.objects.filter(usuario=self.laura).count(), 1)

    def test_el_mismo_vehiculo_no_entra_dos_veces(self):
        """El mismo vehículo no puede entrar de nuevo sin haber salido (409)."""
        self.entrar(self.carro)
        self.assertEqual(self.entrar(self.carro).status_code, status.HTTP_409_CONFLICT)

    def test_tras_salir_puede_entrar_con_otro_vehiculo(self):
        """Después de cerrar la salida, el conductor puede entrar con otro vehículo."""
        moto = Vehiculo.objects.create(usuario=self.laura, placa='XYZ45K', tipo='moto')
        ticket_id = self.entrar(self.carro).data['id']
        self.reloj.avanzar(15 * 60)
        self.confirmar(ticket_id)

        self.assertEqual(self.entrar(moto).status_code, status.HTTP_201_CREATED)

    def test_otro_conductor_si_puede_entrar(self):
        """La restricción es por conductor: otro conductor entra aunque Laura esté adentro."""
        pedro = crear_conductor('pedro@unimonserrate.edu.co')
        carro_pedro = Vehiculo.objects.create(usuario=pedro, placa='DEF456', tipo='carro')
        self.entrar(self.carro)
        self.assertEqual(self.entrar(carro_pedro).status_code, status.HTTP_201_CREATED)


class QREnPorteriaTests(PorteriaTestCase):
    """Errores del QR al pasar por la portería y validación del cuerpo de salida."""

    def test_qr_vencido_es_rechazado(self):
        """Un QR de hace 61 segundos se rechaza con 400 'qr_vencido' y no abre ticket."""
        token = generar_token(self.laura, self.carro)
        self.reloj.avanzar(61)
        resp = self.client.post(URL_ENTRADA, {'token': token}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['codigo'], 'qr_vencido')
        self.assertFalse(Ticket.objects.exists())

    def test_qr_alterado_es_rechazado(self):
        """Un QR con un byte cambiado se rechaza con 400 'qr_alterado'."""
        crudo = bytearray(b64_a_bytes(generar_token(self.laura, self.carro)))
        crudo[20] ^= 0x01
        resp = self.client.post(URL_ENTRADA, {'token': bytes_a_b64(bytes(crudo))}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['codigo'], 'qr_alterado')

    def test_salida_pide_token_o_codigo(self):
        """Pedir la salida sin token ni código de invitado responde 400."""
        self.assertEqual(
            self.client.post(URL_SALIDA, {}, format='json').status_code,
            status.HTTP_400_BAD_REQUEST,
        )


class PermisosPorteriaTests(PorteriaTestCase):
    """Solo el guarda autenticado puede usar los endpoints de portería."""

    def test_solo_el_guarda_usa_la_porteria(self):
        """Un conductor recibe 403 en entrada, salida, confirmación e invitados, sin abrir tickets."""
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
        """Sin autenticación, la entrada responde 401."""
        self.client.force_authenticate(None)
        resp = self.client.post(URL_ENTRADA, {'token': 'x'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class HistorialTests(PorteriaTestCase):
    """GET /api/accesos/historial: recibos cerrados del conductor autenticado."""

    def test_conductor_ve_solo_sus_recibos_cerrados(self):
        """El historial trae solo los tickets cerrados propios, del más reciente al más antiguo."""
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
        """El guarda no es conductor: el historial le responde 403."""
        self.assertEqual(self.client.get(URL_HISTORIAL).status_code, status.HTTP_403_FORBIDDEN)
