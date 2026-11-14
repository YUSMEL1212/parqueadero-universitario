"""Pruebas del pago de mensualidad: precio, inicio, webhook, simulador y modo Wompi."""

import hashlib
from datetime import timedelta
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accesos.services import tiene_mensualidad_activa
from accesos.tests import cargar_tarifas_del_seed, crear_conductor
from tarifas.models import Tarifa
from tarifas.tests import crear_administrador, valores_del_seed
from usuarios.models import Rol, Usuario

from . import wompi
from .models import DURACION_MENSUALIDAD, Mensualidad, Pago

URL_PRECIO = '/api/pagos/mensualidad/precio'
URL_PAGO = '/api/pagos/mensualidad'
URL_WEBHOOK = '/api/pagos/webhook'
URL_VIGENTES = '/api/mensualidades/vigentes'
FRONTEND = 'http://localhost:5173'
RETORNO = f'{FRONTEND}/conductor/pagos'

SIMULACION = override_settings(
    WOMPI_PUBLIC_KEY='', WOMPI_PRIVATE_KEY='', CORS_ALLOWED_ORIGINS=[FRONTEND]
)
WOMPI = override_settings(
    WOMPI_PUBLIC_KEY='pub_test_llave',
    WOMPI_PRIVATE_KEY='prv_test_llave',
    WOMPI_INTEGRITY_SECRET='test_integrity_secreto',
    WOMPI_SANDBOX=True,
    CORS_ALLOWED_ORIGINS=[FRONTEND],
)


class PagoMensualidadTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cargar_tarifas_del_seed()  # carro 75000, moto 56000
        cls.laura = crear_conductor('laura@unimonserrate.edu.co')

    def setUp(self):
        self.client.force_authenticate(self.laura)
        # Reloj fijo del servicio de pagos para comprobar los 30 días exactos.
        self.momento = timezone.now().replace(microsecond=0)
        parche = mock.patch('pagos.servicios.ahora', return_value=self.momento)
        parche.start()
        self.addCleanup(parche.stop)

    def iniciar(self, **cambios):
        cuerpo = {'tipo_vehiculo': 'carro', 'metodo': 'tarjeta', 'url_retorno': RETORNO}
        cuerpo.update(cambios)
        return self.client.post(URL_PAGO, cuerpo, format='json')

    def pago_iniciado(self, **cambios):
        resp = self.iniciar(**cambios)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        return Pago.objects.get(referencia_pasarela=resp.data['referencia'])

    def webhook(self, evento):
        self.client.force_authenticate(None)  # la pasarela llama sin usuario
        return self.client.post(URL_WEBHOOK, evento, format='json')

    def confirmar(self, pago, aprobado):
        return self.webhook(wompi.evento_simulado(pago.referencia_pasarela, pago.valor * 100, aprobado))


# --- Precio -------------------------------------------------------------------------


@SIMULACION
class PrecioTests(PagoMensualidadTestCase):
    def test_el_precio_sale_de_la_tarifa_vigente(self):
        carro = self.client.get(URL_PRECIO, {'tipo': 'carro'})
        moto = self.client.get(URL_PRECIO, {'tipo': 'moto'})

        self.assertEqual(carro.status_code, status.HTTP_200_OK, carro.data)
        self.assertEqual(carro.data['valor'], 75000)
        self.assertEqual(carro.data['duracion_dias'], 30)
        self.assertEqual(moto.data['valor'], 56000)

    def test_el_precio_cambia_cuando_el_administrador_modifica_la_tarifa(self):
        admin = crear_administrador()
        self.client.force_authenticate(admin)
        resp = self.client.put(
            '/api/tarifas', valores_del_seed(carro__mensualidad=80000), format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        self.client.force_authenticate(self.laura)
        precio = self.client.get(URL_PRECIO, {'tipo': 'carro'})
        self.assertEqual(precio.data['valor'], 80000)
        # El pago nuevo también se crea con el valor nuevo.
        self.assertEqual(self.pago_iniciado().valor, 80000)

    def test_tipo_invalido_o_ausente(self):
        self.assertEqual(self.client.get(URL_PRECIO).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            self.client.get(URL_PRECIO, {'tipo': 'bus'}).status_code, status.HTTP_400_BAD_REQUEST
        )

    def test_sin_tarifa_vigente_responde_409(self):
        Tarifa.objects.filter(tipo_vehiculo='moto', concepto='mensualidad').update(
            vigente_hasta=self.momento
        )
        resp = self.client.get(URL_PRECIO, {'tipo': 'moto'})

        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(resp.data['codigo'], 'sin_tarifa_vigente')
        self.assertEqual(self.iniciar(tipo_vehiculo='moto').status_code, status.HTTP_409_CONFLICT)


# --- Inicio del pago ----------------------------------------------------------------


@SIMULACION
class InicioPagoTests(PagoMensualidadTestCase):
    def test_crea_un_pago_pendiente_con_referencia_unica_y_sin_mensualidad(self):
        resp = self.iniciar(metodo='pse', banco='1007', correo='laura.personal@correo.test')

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['estado'], 'pendiente')
        self.assertEqual(resp.data['valor'], 75000)
        self.assertEqual(resp.data['modo'], 'simulacion')
        pago = Pago.objects.get(referencia_pasarela=resp.data['referencia'])
        self.assertEqual(pago.usuario, self.laura)
        self.assertEqual(pago.concepto, Pago.Concepto.MENSUALIDAD)
        self.assertEqual(pago.metodo, Pago.Metodo.PSE)
        self.assertEqual(pago.tipo_vehiculo, 'carro')
        self.assertFalse(Mensualidad.objects.exists())

        otro = self.pago_iniciado()
        self.assertNotEqual(otro.referencia_pasarela, pago.referencia_pasarela)

    def test_en_simulacion_la_url_lleva_al_checkout_interno(self):
        resp = self.iniciar(metodo='pse', banco='1007')

        url = urlsplit(resp.data['url_pago'])
        self.assertEqual(url.path, f"/api/pagos/simulacion/{resp.data['referencia']}")
        parametros = parse_qs(url.query)
        self.assertEqual(parametros['banco'], ['1007'])
        self.assertEqual(parametros['correo'], [self.laura.email])  # por defecto, el de la cuenta
        self.assertEqual(parametros['volver'], [f"{RETORNO}?referencia={resp.data['referencia']}"])

    def test_pse_exige_banco(self):
        resp = self.iniciar(metodo='pse')

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('banco', resp.data)
        self.assertFalse(Pago.objects.exists())

    def test_rechaza_efectivo_y_tipos_invalidos(self):
        self.assertEqual(self.iniciar(metodo='efectivo').status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.iniciar(tipo_vehiculo='bus').status_code, status.HTTP_400_BAD_REQUEST)

    def test_rechaza_una_url_de_retorno_ajena(self):
        resp = self.iniciar(url_retorno='https://sitio-ajeno.test/robar')

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('url_retorno', resp.data)

    def test_solo_un_conductor_inicia_pagos(self):
        rol, _ = Rol.objects.get_or_create(nombre=Rol.Nombre.GUARDA)
        guarda = Usuario.objects.create_user('g@parqueadero.test', 'x', rol=rol, nombre='G')
        self.client.force_authenticate(guarda)

        self.assertEqual(self.iniciar().status_code, status.HTTP_403_FORBIDDEN)


# --- Webhook ------------------------------------------------------------------------


@SIMULACION
class WebhookTests(PagoMensualidadTestCase):
    def test_pago_aprobado_crea_mensualidad_de_30_dias_activa(self):
        pago = self.pago_iniciado()

        resp = self.confirmar(pago, aprobado=True)

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data, {'procesado': True, 'referencia': pago.referencia_pasarela,
                                     'estado': 'aprobado'})
        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.APROBADO)
        self.assertEqual(pago.pagado_en, self.momento)
        self.assertTrue(pago.transaccion_pasarela.startswith('SIM-'))

        mensualidad = Mensualidad.objects.get(pago=pago)
        self.assertEqual(mensualidad.usuario, self.laura)
        self.assertEqual(mensualidad.tipo_vehiculo, 'carro')
        self.assertEqual(mensualidad.inicia_en, self.momento)
        self.assertEqual(mensualidad.vence_en, self.momento + timedelta(days=30))
        self.assertEqual(DURACION_MENSUALIDAD, timedelta(days=30))
        # Activa de inmediato para el motor de cobro y para la app del conductor.
        self.assertTrue(tiene_mensualidad_activa(self.laura, 'carro', timezone.now()))
        self.assertFalse(tiene_mensualidad_activa(self.laura, 'moto', timezone.now()))
        self.client.force_authenticate(self.laura)
        vigentes = self.client.get(URL_VIGENTES)
        self.assertEqual([m['id'] for m in vigentes.data], [str(mensualidad.id)])

    def test_pago_rechazado_no_crea_nada(self):
        pago = self.pago_iniciado()

        resp = self.confirmar(pago, aprobado=False)

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['estado'], 'rechazado')
        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.RECHAZADO)
        self.assertIsNone(pago.pagado_en)
        self.assertFalse(Mensualidad.objects.exists())
        self.assertFalse(tiene_mensualidad_activa(self.laura, 'carro', timezone.now()))

    def test_webhook_repetido_no_duplica_la_mensualidad(self):
        pago = self.pago_iniciado()
        evento = wompi.evento_simulado(pago.referencia_pasarela, pago.valor * 100, True)

        primera = self.webhook(evento)
        segunda = self.webhook(evento)
        tercera = self.confirmar(pago, aprobado=True)  # otro evento de la misma transacción

        self.assertTrue(primera.data['procesado'])
        for resp in (segunda, tercera):
            self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
            self.assertFalse(resp.data['procesado'])
            self.assertEqual(resp.data['estado'], 'aprobado')
        self.assertEqual(Mensualidad.objects.filter(pago=pago).count(), 1)
        self.assertEqual(Mensualidad.objects.count(), 1)

    def test_un_pago_resuelto_no_cambia_con_una_confirmacion_tardia(self):
        pago = self.pago_iniciado()
        self.confirmar(pago, aprobado=True)

        self.confirmar(pago, aprobado=False)

        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.APROBADO)
        self.assertEqual(Mensualidad.objects.count(), 1)

    def test_firma_invalida_no_cambia_nada(self):
        pago = self.pago_iniciado()
        evento = wompi.evento_simulado(pago.referencia_pasarela, pago.valor * 100, False)
        evento['data']['transaction']['status'] = 'APPROVED'  # alterado sin volver a firmar

        resp = self.webhook(evento)

        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.PENDIENTE)
        self.assertFalse(Mensualidad.objects.exists())

    def test_monto_distinto_no_aprueba(self):
        pago = self.pago_iniciado()

        resp = self.webhook(wompi.evento_simulado(pago.referencia_pasarela, 100, True))

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['codigo'], 'monto_no_coincide')
        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.PENDIENTE)
        self.assertFalse(Mensualidad.objects.exists())

    def test_referencia_desconocida_responde_200_sin_procesar(self):
        resp = self.webhook(wompi.evento_simulado('MEN-NO-EXISTE', 7500000, True))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data['procesado'])

    def test_ignora_otros_eventos(self):
        resp = self.webhook({'event': 'nequi_token.updated', 'data': {}})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data['procesado'])


# --- Estado del pago y checkout simulado --------------------------------------------


@SIMULACION
class SimuladorTests(PagoMensualidadTestCase):
    def test_aprobar_en_el_simulador_dispara_el_webhook_y_vuelve_a_la_pwa(self):
        resp = self.iniciar(metodo='pse', banco='1007')
        url = resp.data['url_pago']
        referencia = resp.data['referencia']

        pagina = self.client.get(url)
        self.assertEqual(pagina.status_code, status.HTTP_200_OK)
        self.assertContains(pagina, 'Bancolombia')
        self.assertContains(pagina, '75.000')

        volver = parse_qs(urlsplit(url).query)['volver'][0]
        resp = self.client.post(urlsplit(url).path, {'accion': 'aprobar', 'volver': volver})

        self.assertEqual(resp.status_code, status.HTTP_303_SEE_OTHER)
        self.assertEqual(resp['Location'], f'{RETORNO}?referencia={referencia}')
        estado = self.client.get(f'{URL_PAGO}/{referencia}')
        self.assertEqual(estado.data['estado'], 'aprobado')
        self.assertEqual(
            estado.data['mensualidad']['vence_en'],
            timezone.localtime(self.momento + timedelta(days=30)).isoformat(),
        )

    def test_rechazar_en_el_simulador_no_crea_mensualidad(self):
        pago = self.pago_iniciado()

        self.client.post(f'/api/pagos/simulacion/{pago.referencia_pasarela}', {'accion': 'rechazar'})

        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.RECHAZADO)
        self.assertFalse(Mensualidad.objects.exists())

    def test_el_simulador_no_redirige_a_sitios_ajenos(self):
        pago = self.pago_iniciado()

        resp = self.client.post(
            f'/api/pagos/simulacion/{pago.referencia_pasarela}',
            {'accion': 'aprobar', 'volver': 'https://sitio-ajeno.test/'},
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertContains(resp, 'Pago aprobado')

    def test_el_estado_solo_lo_ve_el_dueno_del_pago(self):
        pago = self.pago_iniciado()
        self.client.force_authenticate(crear_conductor('mario@unimonserrate.edu.co'))

        resp = self.client.get(f'{URL_PAGO}/{pago.referencia_pasarela}')

        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# --- Modo Wompi ---------------------------------------------------------------------


@WOMPI
class ModoWompiTests(PagoMensualidadTestCase):
    def transaccion(self, pago, estado, **cambios):
        datos = {
            'id': '1234-1763132712-49201',
            'reference': pago.referencia_pasarela,
            'amount_in_cents': pago.valor * 100,
            'currency': 'COP',
            'status': estado,
        }
        datos.update(cambios)
        return datos

    def test_la_url_es_el_checkout_de_wompi_con_firma_de_integridad(self):
        resp = self.iniciar()

        self.assertEqual(resp.data['modo'], 'wompi')
        url = urlsplit(resp.data['url_pago'])
        self.assertEqual(f'{url.scheme}://{url.netloc}{url.path}', wompi.URL_CHECKOUT)
        p = {k: v[0] for k, v in parse_qs(url.query).items()}
        referencia = resp.data['referencia']
        self.assertEqual(p['public-key'], 'pub_test_llave')
        self.assertEqual(p['amount-in-cents'], '7500000')
        self.assertEqual(p['currency'], 'COP')
        self.assertEqual(p['reference'], referencia)
        esperado = hashlib.sha256(f'{referencia}7500000COPtest_integrity_secreto'.encode()).hexdigest()
        self.assertEqual(p['signature:integrity'], esperado)
        self.assertEqual(p['redirect-url'], f'{RETORNO}?referencia={referencia}')

    @override_settings(WOMPI_INTEGRITY_SECRET='')
    def test_sin_secreto_de_integridad_responde_503(self):
        resp = self.iniciar()

        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(resp.data['codigo'], 'pasarela_mal_configurada')

    def test_el_webhook_confia_en_la_api_de_wompi_y_no_en_el_cuerpo(self):
        pago = self.pago_iniciado()
        cuerpo = {'event': 'transaction.updated',
                  'data': {'transaction': self.transaccion(pago, 'APPROVED')}}

        with mock.patch.object(
            wompi, 'consultar_transaccion', return_value=self.transaccion(pago, 'DECLINED')
        ) as consulta:
            resp = self.webhook(cuerpo)

        consulta.assert_called_once_with('1234-1763132712-49201')
        self.assertEqual(resp.data['estado'], 'rechazado')
        self.assertFalse(Mensualidad.objects.exists())

    def test_el_webhook_aprobado_por_la_api_crea_la_mensualidad(self):
        pago = self.pago_iniciado()
        cuerpo = {'event': 'transaction.updated',
                  'data': {'transaction': {'id': '1234-1763132712-49201'}}}

        with mock.patch.object(
            wompi, 'consultar_transaccion', return_value=self.transaccion(pago, 'APPROVED')
        ):
            self.webhook(cuerpo)
            self.webhook(cuerpo)

        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.APROBADO)
        self.assertEqual(pago.transaccion_pasarela, '1234-1763132712-49201')
        self.assertEqual(Mensualidad.objects.count(), 1)

    def test_wompi_caido_responde_502_para_que_reintente(self):
        pago = self.pago_iniciado()
        cuerpo = {'event': 'transaction.updated', 'data': {'transaction': {'id': 'x'}}}

        with mock.patch.object(
            wompi, 'consultar_transaccion', side_effect=wompi.PasarelaNoDisponible('caída')
        ):
            resp = self.webhook(cuerpo)

        self.assertEqual(resp.status_code, status.HTTP_502_BAD_GATEWAY)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.PENDIENTE)

    def test_al_volver_del_checkout_el_estado_se_sincroniza_sin_webhook(self):
        pago = self.pago_iniciado()

        with mock.patch.object(
            wompi, 'consultar_transaccion', return_value=self.transaccion(pago, 'APPROVED')
        ):
            resp = self.client.get(
                f'{URL_PAGO}/{pago.referencia_pasarela}', {'transaccion': '1234-1763132712-49201'}
            )

        self.assertEqual(resp.data['estado'], 'aprobado')
        self.assertIsNotNone(resp.data['mensualidad'])

    def test_el_simulador_no_existe_con_llaves_de_wompi(self):
        pago = self.pago_iniciado()

        resp = self.client.post(f'/api/pagos/simulacion/{pago.referencia_pasarela}', {'accion': 'aprobar'})

        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.PENDIENTE)
