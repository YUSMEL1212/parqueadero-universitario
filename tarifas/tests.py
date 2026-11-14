"""Pruebas de los endpoints de tarifas: vigentes, historial y cambio con vigencias."""

from datetime import timedelta
from unittest import mock

from django.db import IntegrityError
from rest_framework import status
from rest_framework.test import APITestCase

from accesos.models import Ticket
from accesos.test_porteria import PorteriaTestCase
from accesos.tests import ENTRADA, cargar_tarifas_del_seed
from usuarios.management.commands.seed import TARIFAS
from usuarios.models import Rol, Usuario

from .models import Tarifa

URL_TARIFAS = '/api/tarifas'
URL_HISTORIAL = '/api/tarifas/historial'


def crear_usuario(email, rol, nombre):
    rol, _ = Rol.objects.get_or_create(nombre=rol)
    return Usuario.objects.create_user(email, 'Parqueo.Seguro2026', rol=rol, nombre=nombre)


def crear_administrador():
    return crear_usuario('admin@parqueadero.test', Rol.Nombre.ADMINISTRADOR, 'Ana Admin')


def valores_del_seed(**cambios):
    """Cuerpo del PUT con los valores del seed; `cambios` usa claves como carro__mas_2h."""
    cuerpo = {}
    for tipo, concepto, valor in TARIFAS:
        cuerpo.setdefault(str(tipo), {})[str(concepto)] = valor
    for clave, valor in cambios.items():
        tipo, concepto = clave.split('__')
        cuerpo[tipo][concepto] = valor
    return cuerpo


def vigente(tipo, concepto):
    return Tarifa.objects.get(tipo_vehiculo=tipo, concepto=concepto, vigente_hasta__isnull=True)


class TarifasAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cargar_tarifas_del_seed()
        cls.admin = crear_administrador()
        cls.guarda = crear_usuario('guarda@parqueadero.test', Rol.Nombre.GUARDA, 'Guarda')
        cls.conductor = crear_usuario(
            'laura@unimonserrate.edu.co', Rol.Nombre.CONDUCTOR, 'Laura'
        )

    def cambiar(self, momento, cuerpo, usuario=None):
        """PUT /api/tarifas con el reloj del servicio fijo en `momento`."""
        self.client.force_authenticate(usuario or self.admin)
        with mock.patch('tarifas.servicios.ahora', return_value=momento):
            return self.client.put(URL_TARIFAS, cuerpo, format='json')


class CambioDeTarifaTests(TarifasAPITestCase):
    def test_cambiar_una_tarifa_cierra_la_anterior_y_crea_una_nueva(self):
        anterior = vigente('carro', 'mas_2h')
        momento = ENTRADA + timedelta(days=1)

        resp = self.cambiar(momento, valores_del_seed(carro__mas_2h=13000))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        anterior.refresh_from_db()
        self.assertEqual(anterior.valor, 12000)  # la fila vieja no se edita
        self.assertEqual(anterior.vigente_hasta, momento)

        nueva = vigente('carro', 'mas_2h')
        self.assertNotEqual(nueva.pk, anterior.pk)
        self.assertEqual(nueva.valor, 13000)
        self.assertEqual(nueva.vigente_desde, momento)
        self.assertEqual(nueva.creado_por, self.admin)

        # Solo cambió un valor: una fila nueva, y siguen siendo seis vigentes.
        self.assertEqual(Tarifa.objects.count(), 7)
        self.assertEqual(Tarifa.objects.filter(vigente_hasta__isnull=True).count(), 6)
        self.assertEqual([t['id'] for t in resp.data['creadas']], [nueva.pk])
        self.assertEqual(len(resp.data['vigentes']), 6)

    def test_valores_sin_cambio_no_crean_filas(self):
        resp = self.cambiar(ENTRADA + timedelta(days=1), valores_del_seed())
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['creadas'], [])
        self.assertEqual(Tarifa.objects.count(), 6)
        self.assertFalse(Tarifa.objects.filter(vigente_hasta__isnull=False).exists())

    def test_varios_cambios_en_una_sola_peticion(self):
        resp = self.cambiar(
            ENTRADA + timedelta(days=1),
            valores_del_seed(carro__hasta_2h=8000, moto__mensualidad=60000),
        )
        self.assertEqual(len(resp.data['creadas']), 2)
        self.assertEqual(vigente('carro', 'hasta_2h').valor, 8000)
        self.assertEqual(vigente('moto', 'mensualidad').valor, 60000)
        self.assertEqual(Tarifa.objects.filter(vigente_hasta__isnull=False).count(), 2)

    def test_si_algo_falla_no_se_aplica_ningun_cambio(self):
        crear_real = Tarifa.objects.create
        llamadas = []

        def crear_y_fallar_la_segunda(**kwargs):
            llamadas.append(kwargs)
            if len(llamadas) == 2:
                raise IntegrityError('choque simulado')
            return crear_real(**kwargs)

        with mock.patch.object(Tarifa.objects, 'create', side_effect=crear_y_fallar_la_segunda):
            resp = self.cambiar(
                ENTRADA + timedelta(days=1),
                valores_del_seed(carro__hasta_2h=8000, moto__hasta_2h=6000),
            )

        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        # El primer cambio (carro) también se revirtió.
        self.assertEqual(Tarifa.objects.count(), 6)
        self.assertEqual(vigente('carro', 'hasta_2h').valor, 7000)
        self.assertEqual(vigente('moto', 'hasta_2h').valor, 5000)


class HistorialTests(TarifasAPITestCase):
    def test_el_historial_queda_completo_y_ordenado(self):
        t1 = ENTRADA + timedelta(days=1)
        t2 = ENTRADA + timedelta(days=2)
        self.cambiar(t1, valores_del_seed(carro__mas_2h=13000))
        self.cambiar(t2, valores_del_seed(carro__mas_2h=14000, moto__hasta_2h=5500))

        self.client.force_authenticate(self.admin)
        resp = self.client.get(URL_HISTORIAL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(len(resp.data), 9)  # 6 iniciales + 1 + 2

        fechas = [r['vigente_desde'] for r in resp.data]
        self.assertEqual(fechas, sorted(fechas, reverse=True))

        # La cadena de carro mas_2h: cada fila cierra justo cuando abre la siguiente.
        cadena = [
            r for r in resp.data if (r['tipo_vehiculo'], r['concepto']) == ('carro', 'mas_2h')
        ]
        self.assertEqual([r['valor'] for r in cadena], [14000, 13000, 12000])
        self.assertIsNone(cadena[0]['vigente_hasta'])
        self.assertEqual(cadena[1]['vigente_hasta'], cadena[0]['vigente_desde'])
        self.assertEqual(cadena[2]['vigente_hasta'], cadena[1]['vigente_desde'])

        self.assertEqual(str(cadena[0]['creado_por']), str(self.admin.pk))
        self.assertEqual(cadena[0]['creado_por_nombre'], 'Ana Admin')
        self.assertIsNone(cadena[2]['creado_por_nombre'])  # fila cargada sin autor

    def test_solo_el_administrador_ve_el_historial(self):
        for usuario in (self.guarda, self.conductor):
            with self.subTest(rol=usuario.rol.nombre):
                self.client.force_authenticate(usuario)
                self.assertEqual(
                    self.client.get(URL_HISTORIAL).status_code, status.HTTP_403_FORBIDDEN
                )


class ConsultaVigentesTests(TarifasAPITestCase):
    def test_cualquier_usuario_autenticado_ve_las_vigentes(self):
        self.cambiar(ENTRADA + timedelta(days=1), valores_del_seed(moto__mas_2h=9500))

        for usuario in (self.conductor, self.guarda, self.admin):
            with self.subTest(rol=usuario.rol.nombre):
                self.client.force_authenticate(usuario)
                resp = self.client.get(URL_TARIFAS)
                self.assertEqual(resp.status_code, status.HTTP_200_OK)
                self.assertEqual(len(resp.data), 6)
                valores = {(t['tipo_vehiculo'], t['concepto']): t['valor'] for t in resp.data}
                self.assertEqual(valores[('moto', 'mas_2h')], 9500)
                self.assertEqual(valores[('carro', 'hasta_2h')], 7000)

    def test_sin_autenticacion_responde_401(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(URL_TARIFAS).status_code, status.HTTP_401_UNAUTHORIZED)


class PermisosYValidacionTests(TarifasAPITestCase):
    def test_un_guarda_recibe_403_al_modificar(self):
        resp = self.cambiar(
            ENTRADA + timedelta(days=1), valores_del_seed(carro__hasta_2h=1000), self.guarda
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Tarifa.objects.count(), 6)
        self.assertEqual(vigente('carro', 'hasta_2h').valor, 7000)

    def test_un_conductor_tampoco_puede_modificar(self):
        resp = self.cambiar(
            ENTRADA + timedelta(days=1), valores_del_seed(carro__hasta_2h=1000), self.conductor
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_valor_negativo_da_400(self):
        resp = self.cambiar(ENTRADA + timedelta(days=1), valores_del_seed(moto__hasta_2h=-5000))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['moto']['hasta_2h'], ['El valor debe ser mayor que 0.'])
        self.assertEqual(Tarifa.objects.count(), 6)

    def test_valor_cero_da_400_aunque_los_demas_sean_validos(self):
        resp = self.cambiar(
            ENTRADA + timedelta(days=1),
            valores_del_seed(carro__hasta_2h=8000, carro__mensualidad=0),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('mensualidad', resp.data['carro'])
        self.assertEqual(vigente('carro', 'hasta_2h').valor, 7000)  # nada se aplicó

    def test_faltan_valores_da_400(self):
        cuerpo = valores_del_seed()
        del cuerpo['moto']['mensualidad']
        resp = self.cambiar(ENTRADA + timedelta(days=1), cuerpo)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('mensualidad', resp.data['moto'])

    def test_valor_no_entero_da_400(self):
        for malo in ('siete mil', 7000.5, None):
            with self.subTest(valor=malo):
                resp = self.cambiar(
                    ENTRADA + timedelta(days=1), valores_del_seed(carro__mas_2h=malo)
                )
                self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class CobroTrasCambioDeTarifaTests(PorteriaTestCase):
    """Un cobro cerrado antes del cambio conserva el valor viejo; uno posterior usa el nuevo."""

    def test_cobro_anterior_conserva_el_valor_y_el_posterior_usa_el_nuevo(self):
        # Cobro 1, con la tarifa original (carro hasta_2h = 7000).
        primero_id = self.entrar(self.carro).data['id']
        self.reloj.avanzar(90 * 60)
        self.assertEqual(self.confirmar(primero_id).data['valor_cobrado'], 7000)
        tarifa_vieja = vigente('carro', 'hasta_2h')

        # El administrador sube la tarifa.
        self.client.force_authenticate(crear_administrador())
        with mock.patch('tarifas.servicios.ahora', return_value=self.reloj.momento):
            resp = self.client.put(
                URL_TARIFAS, valores_del_seed(carro__hasta_2h=8000), format='json'
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.client.force_authenticate(self.guarda)

        # Cobro 2, después del cambio.
        self.reloj.avanzar(10 * 60)
        segundo_id = self.entrar(self.carro).data['id']
        self.reloj.avanzar(60 * 60)
        resp = self.confirmar(segundo_id)
        self.assertEqual(resp.data['valor_cobrado'], 8000)

        segundo = Ticket.objects.select_related('tarifa').get(pk=segundo_id)
        self.assertEqual(segundo.tarifa.valor, 8000)
        self.assertIsNone(segundo.tarifa.vigente_hasta)

        primero = Ticket.objects.select_related('tarifa').get(pk=primero_id)
        self.assertEqual(primero.valor_cobrado, 7000)
        self.assertEqual(primero.tarifa, tarifa_vieja)
        self.assertEqual(primero.tarifa.valor, 7000)
        self.assertIsNotNone(primero.tarifa.vigente_hasta)
