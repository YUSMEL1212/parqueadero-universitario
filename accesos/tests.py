"""
Pruebas unitarias del motor de cobro (accesos/services.py).

Llaman a `calcular_cobro` directamente, sin HTTP, con las tarifas del seed: tramos por
tiempo (frontera de 120 minutos), mensualidad activa, invitados, cambio de tarifa y
ausencia de tarifa vigente. Las funciones auxiliares de este módulo también las usa
accesos/test_porteria.py.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from pagos.models import Mensualidad, Pago
from tarifas.models import Tarifa
from usuarios.management.commands.seed import TARIFAS
from usuarios.models import Usuario

from .services import TarifaNoVigenteError, calcular_cobro

ENTRADA = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0)


def salida_a(minutos, segundos=0):
    """Hora de salida a cierta distancia de ENTRADA.

    Parámetros:
        minutos (int): minutos después de la entrada (negativo para antes).
        segundos (int): segundos adicionales.

    Devuelve:
        datetime: ENTRADA + minutos + segundos.
    """
    return ENTRADA + timedelta(minutes=minutos, seconds=segundos)


def cargar_tarifas_del_seed():
    """Crea las tarifas vigentes con los mismos valores que `python manage.py seed`."""
    for tipo, concepto, valor in TARIFAS:
        Tarifa.objects.create(
            tipo_vehiculo=tipo, concepto=concepto, valor=valor, vigente_desde=ENTRADA
        )


def crear_conductor(email):
    """Crea un conductor (estudiante) con contraseña fija de prueba.

    Parámetros:
        email (str): correo del conductor; la parte antes de la @ se usa como nombre.

    Devuelve:
        Usuario: el conductor creado.
    """
    return Usuario.objects.create_user(
        email, 'Parqueo.Seguro2026', nombre=email.split('@')[0], tipo_conductor='estudiante'
    )


def crear_mensualidad(usuario, tipo_vehiculo, vence_en):
    """Crea una mensualidad de 30 días, con su pago aprobado, que vence en `vence_en`.

    Parámetros:
        usuario (Usuario): dueño de la mensualidad.
        tipo_vehiculo (str): 'carro' o 'moto'.
        vence_en (datetime): fin de la mensualidad.

    Devuelve:
        Mensualidad: la mensualidad creada.
    """
    pago = Pago.objects.create(
        usuario=usuario,
        concepto=Pago.Concepto.MENSUALIDAD,
        valor=1,
        metodo=Pago.Metodo.TARJETA,
        estado=Pago.Estado.APROBADO,
    )
    return Mensualidad.objects.create(
        usuario=usuario,
        pago=pago,
        tipo_vehiculo=tipo_vehiculo,
        inicia_en=vence_en - timedelta(days=30),
        vence_en=vence_en,
    )


class CobroPorTiempoTests(TestCase):
    """Cobro sin mensualidad: tramo hasta_2h o mas_2h según los minutos de estadía."""

    @classmethod
    def setUpTestData(cls):
        """Carga las tarifas vigentes del seed una vez para toda la clase."""
        cargar_tarifas_del_seed()

    def test_carro_90_minutos(self):
        """Carro con 90 minutos paga hasta_2h (7000) y el resultado trae la tarifa aplicada."""
        r = calcular_cobro(ENTRADA, salida_a(90), 'carro')
        self.assertEqual(r['valor'], 7000)
        self.assertEqual(r['minutos'], 90)
        self.assertEqual(r['motivo'], 'hasta_2h')
        self.assertEqual(r['tarifa'].concepto, 'hasta_2h')

    def test_carro_exactamente_120_minutos(self):
        """Frontera: 120 minutos exactos todavía son hasta_2h (7000)."""
        r = calcular_cobro(ENTRADA, salida_a(120), 'carro')
        self.assertEqual(r['valor'], 7000)
        self.assertEqual(r['minutos'], 120)
        self.assertEqual(r['motivo'], 'hasta_2h')

    def test_carro_121_minutos(self):
        """Frontera: 121 minutos ya son mas_2h (12000)."""
        r = calcular_cobro(ENTRADA, salida_a(121), 'carro')
        self.assertEqual(r['valor'], 12000)
        self.assertEqual(r['minutos'], 121)
        self.assertEqual(r['motivo'], 'mas_2h')

    def test_minuto_empezado_cuenta_completo(self):
        """120 minutos y 1 segundo se redondean a 121 y se cobran como mas_2h."""
        # 120 min y 1 s ya superan las 2 horas.
        r = calcular_cobro(ENTRADA, salida_a(120, segundos=1), 'carro')
        self.assertEqual(r['minutos'], 121)
        self.assertEqual(r['valor'], 12000)

    def test_moto_120_minutos(self):
        """Moto con 120 minutos paga la tarifa hasta_2h de moto (5000)."""
        r = calcular_cobro(ENTRADA, salida_a(120), 'moto')
        self.assertEqual(r['valor'], 5000)
        self.assertEqual(r['motivo'], 'hasta_2h')

    def test_moto_121_minutos(self):
        """Moto con 121 minutos paga la tarifa mas_2h de moto (9000)."""
        r = calcular_cobro(ENTRADA, salida_a(121), 'moto')
        self.assertEqual(r['valor'], 9000)
        self.assertEqual(r['motivo'], 'mas_2h')

    def test_salida_anterior_a_la_entrada(self):
        """Una salida anterior a la entrada lanza ValueError."""
        with self.assertRaises(ValueError):
            calcular_cobro(ENTRADA, salida_a(-1), 'carro')


class CobroConMensualidadTests(TestCase):
    """Cobro de un conductor con mensualidad: cuándo aplica y cuándo no."""

    @classmethod
    def setUpTestData(cls):
        """Carga las tarifas del seed y crea un conductor sin mensualidad."""
        cargar_tarifas_del_seed()
        cls.conductor = crear_conductor('laura@unimonserrate.edu.co')

    def test_mensualidad_activa_cobra_cero_sin_importar_el_tiempo(self):
        """Con mensualidad activa el cobro es 0 para cualquier estadía, sin tarifa aplicada."""
        crear_mensualidad(self.conductor, 'carro', vence_en=ENTRADA + timedelta(days=10))

        for minutos in (5, 120, 121, 600):
            with self.subTest(minutos=minutos):
                r = calcular_cobro(ENTRADA, salida_a(minutos), 'carro', self.conductor)
                self.assertEqual(r['valor'], 0)
                self.assertEqual(r['motivo'], 'mensualidad_activa')
                self.assertIsNone(r['tarifa'])
                self.assertEqual(r['minutos'], minutos)

    def test_mensualidad_vencida_cobra_tarifa_normal(self):
        """Una mensualidad ya vencida no cuenta: se cobra la tarifa por tiempo."""
        crear_mensualidad(self.conductor, 'carro', vence_en=ENTRADA - timedelta(days=1))

        r = calcular_cobro(ENTRADA, salida_a(90), 'carro', self.conductor)
        self.assertEqual(r['valor'], 7000)
        self.assertEqual(r['motivo'], 'hasta_2h')

    def test_mensualidad_que_vence_antes_de_la_salida_no_aplica(self):
        """La mensualidad se evalúa a la hora de salida: si vence durante la estadía, se cobra."""
        # Activa al entrar, vencida al salir: manda vence_en > hora_salida.
        crear_mensualidad(self.conductor, 'carro', vence_en=salida_a(60))

        r = calcular_cobro(ENTRADA, salida_a(90), 'carro', self.conductor)
        self.assertEqual(r['valor'], 7000)

    def test_mensualidad_de_otro_tipo_de_vehiculo_no_aplica(self):
        """Una mensualidad de moto no cubre la estadía de un carro."""
        crear_mensualidad(self.conductor, 'moto', vence_en=ENTRADA + timedelta(days=10))

        r = calcular_cobro(ENTRADA, salida_a(90), 'carro', self.conductor)
        self.assertEqual(r['valor'], 7000)

    def test_invitado_cobra_completo_aunque_otro_usuario_tenga_mensualidad(self):
        """Un invitado (usuario=None) paga tarifa completa aunque exista otra mensualidad activa."""
        crear_mensualidad(self.conductor, 'carro', vence_en=ENTRADA + timedelta(days=10))

        r = calcular_cobro(ENTRADA, salida_a(121), 'carro', usuario=None)
        self.assertEqual(r['valor'], 12000)
        self.assertEqual(r['motivo'], 'mas_2h')


class CambioDeTarifaTests(TestCase):
    """El motor siempre usa la tarifa vigente, también después de un cambio de tarifa."""

    @classmethod
    def setUpTestData(cls):
        """Carga las tarifas vigentes del seed una vez para toda la clase."""
        cargar_tarifas_del_seed()

    def test_usa_la_tarifa_vigente_despues_de_un_cambio(self):
        """Tras cerrar la tarifa vigente y crear otra, se cobra la nueva y las demás no cambian."""
        # Cambio de tarifa como dice CLAUDE.md: se cierra la vigente y se crea otra fila.
        ahora = timezone.now()
        anterior = Tarifa.objects.get(
            tipo_vehiculo='carro', concepto='hasta_2h', vigente_hasta__isnull=True
        )
        anterior.vigente_hasta = ahora
        anterior.save()
        nueva = Tarifa.objects.create(
            tipo_vehiculo='carro', concepto='hasta_2h', valor=8000, vigente_desde=ahora
        )

        r = calcular_cobro(ENTRADA, salida_a(90), 'carro')
        self.assertEqual(r['valor'], 8000)
        self.assertEqual(r['tarifa'], nueva)
        # Las demás tarifas no cambian.
        self.assertEqual(calcular_cobro(ENTRADA, salida_a(121), 'carro')['valor'], 12000)


class SinTarifaVigenteTests(TestCase):
    """Comportamiento cuando falta la tarifa vigente para el caso."""

    def test_lanza_error_claro_si_no_hay_tarifa_vigente(self):
        """Si solo hay tarifa histórica, se lanza TarifaNoVigenteError con tipo, concepto y mensaje."""
        Tarifa.objects.create(
            tipo_vehiculo='moto',
            concepto='hasta_2h',
            valor=5000,
            vigente_desde=ENTRADA - timedelta(days=60),
            vigente_hasta=ENTRADA - timedelta(days=30),  # solo histórica
        )

        with self.assertRaises(TarifaNoVigenteError) as ctx:
            calcular_cobro(ENTRADA, salida_a(30), 'moto')
        self.assertEqual(ctx.exception.tipo_vehiculo, 'moto')
        self.assertEqual(ctx.exception.concepto, 'hasta_2h')
        self.assertIn('No hay tarifa vigente', str(ctx.exception))
