"""Pruebas del token del QR dinámico (accesos/qr.py) y de GET /api/accesos/qr."""

import base64
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from usuarios.models import Usuario
from vehiculos.models import Vehiculo

from .qr import (
    TokenQRAlterado,
    TokenQRError,
    TokenQRIlegible,
    TokenQRVencido,
    generar_token,
    validar_token,
)

# Llaves fijas solo para pruebas (32 bytes en base64url); no dependen del .env.
LLAVE_PRUEBA = base64.urlsafe_b64encode(bytes(range(32))).decode()
OTRA_LLAVE = base64.urlsafe_b64encode(bytes(range(32, 64))).decode()
URL_QR = '/api/accesos/qr'


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


def b64_a_bytes(token):
    """Decodifica un token base64url sin relleno para poder manipular sus bytes.

    Parámetros:
        token (str): token generado por `generar_token`.

    Devuelve:
        bytes: nonce, texto cifrado y etiqueta GCM concatenados.
    """
    return base64.urlsafe_b64decode(token + '=' * (-len(token) % 4))


def bytes_a_b64(datos):
    """Vuelve a codificar bytes (posiblemente alterados) como token base64url sin relleno.

    Parámetros:
        datos (bytes): bytes del token.

    Devuelve:
        str: texto con el mismo formato que produce `generar_token`.
    """
    return base64.urlsafe_b64encode(datos).rstrip(b'=').decode()


class Reloj:
    """Reemplaza accesos.qr.ahora para simular el paso del tiempo."""

    def __init__(self, inicio):
        """Fija la hora inicial del reloj.

        Parámetros:
            inicio (datetime): hora desde la que arranca la simulación.
        """
        self.momento = inicio

    def __call__(self):
        """Devuelve la hora simulada actual, igual que lo haría `ahora()`.

        Devuelve:
            datetime: el momento actual del reloj.
        """
        return self.momento

    def avanzar(self, segundos):
        """Adelanta el reloj.

        Parámetros:
            segundos (int): segundos que se suman a la hora simulada.
        """
        self.momento += timedelta(seconds=segundos)


@override_settings(QR_SECRET_KEY=LLAVE_PRUEBA)
class TokenQRTests(TestCase):
    """Generación y validación del token: contenido, vigencia de 60 s y rechazo de alterados."""

    @classmethod
    def setUpTestData(cls):
        """Crea un conductor con un carro activo para toda la clase."""
        cls.conductor = crear_conductor('laura@unimonserrate.edu.co')
        cls.carro = Vehiculo.objects.create(usuario=cls.conductor, placa='ABC123', tipo='carro')

    def setUp(self):
        """Reemplaza el reloj de accesos.qr por un Reloj controlado por la prueba."""
        # Arranca en un segundo exacto para que el vencimiento caiga justo a los 60 s.
        self.reloj = Reloj(timezone.now().replace(microsecond=0))
        parche = mock.patch('accesos.qr.ahora', self.reloj)
        parche.start()
        self.addCleanup(parche.stop)

    def test_token_valido_se_descifra(self):
        """Un token recién generado se descifra con usuario, vehículo, placa y 60 s de vigencia."""
        token = generar_token(self.conductor, self.carro)
        datos = validar_token(token)

        self.assertEqual(datos['usuario_id'], str(self.conductor.pk))
        self.assertEqual(datos['vehiculo_id'], str(self.carro.pk))
        self.assertEqual(datos['placa'], 'ABC123')
        self.assertEqual(datos['vence_en'] - datos['emitido_en'], timedelta(seconds=60))
        self.assertEqual(datos['vence_en'], self.reloj.momento + timedelta(seconds=60))

    def test_el_token_no_lleva_datos_en_claro(self):
        """El token cifrado no deja ver ni la placa ni el id del usuario."""
        crudo = b64_a_bytes(generar_token(self.conductor, self.carro))
        self.assertNotIn(b'ABC123', crudo)
        self.assertNotIn(str(self.conductor.pk).encode(), crudo)

    def test_dos_tokens_seguidos_son_distintos(self):
        """Dos tokens del mismo vehículo en el mismo segundo son distintos (nonce aleatorio)."""
        # Nonce aleatorio: el mismo contenido no produce el mismo token.
        self.assertNotEqual(
            generar_token(self.conductor, self.carro), generar_token(self.conductor, self.carro)
        )

    def test_sigue_valido_a_los_59_segundos(self):
        """El token todavía es válido 59 segundos después de emitido."""
        token = generar_token(self.conductor, self.carro)
        self.reloj.avanzar(59)
        self.assertEqual(validar_token(token)['placa'], 'ABC123')

    def test_token_vencido_es_rechazado(self):
        """A los 60 segundos (y después) el token se rechaza con TokenQRVencido."""
        token = generar_token(self.conductor, self.carro)
        self.reloj.avanzar(60)
        with self.assertRaises(TokenQRVencido):
            validar_token(token)

        self.reloj.avanzar(3600)
        with self.assertRaises(TokenQRVencido) as ctx:
            validar_token(token)
        self.assertIn('venció', str(ctx.exception))

    def test_token_con_un_byte_cambiado_es_rechazado(self):
        """Cambiar cualquier byte del token (nonce, cifrado o etiqueta) da TokenQRAlterado."""
        crudo = b64_a_bytes(generar_token(self.conductor, self.carro))
        # Cambiar cualquier byte (nonce, texto cifrado o etiqueta) invalida el token.
        for posicion in range(len(crudo)):
            alterado = bytearray(crudo)
            alterado[posicion] ^= 0x01
            with self.subTest(posicion=posicion):
                with self.assertRaises(TokenQRAlterado):
                    validar_token(bytes_a_b64(bytes(alterado)))

    def test_token_de_otra_llave_es_rechazado(self):
        """Un token cifrado con otra llave se rechaza como alterado."""
        with override_settings(QR_SECRET_KEY=OTRA_LLAVE):
            token = generar_token(self.conductor, self.carro)
        with self.assertRaises(TokenQRAlterado):
            validar_token(token)

    def test_alterado_y_vencido_se_reporta_como_alterado(self):
        """Si el token está alterado y además vencido, gana alterado: no se lee sin autenticar."""
        # El vencimiento va cifrado: no se lee hasta pasar la autenticación GCM.
        crudo = bytearray(b64_a_bytes(generar_token(self.conductor, self.carro)))
        crudo[-1] ^= 0xFF
        self.reloj.avanzar(120)
        with self.assertRaises(TokenQRAlterado):
            validar_token(bytes_a_b64(bytes(crudo)))

    def test_texto_que_no_es_token_no_se_puede_descifrar(self):
        """Vacío, espacios, texto no base64, base64 demasiado corto o None dan TokenQRIlegible."""
        for basura in ['', '   ', 'esto no es base64!', 'QUJD', None]:
            with self.subTest(basura=basura):
                with self.assertRaises(TokenQRIlegible):
                    validar_token(basura)

    def test_las_tres_excepciones_son_distintas_y_comparten_base(self):
        """Vencido, alterado e ilegible heredan de TokenQRError y no se heredan entre sí."""
        for exc in (TokenQRVencido, TokenQRAlterado, TokenQRIlegible):
            self.assertTrue(issubclass(exc, TokenQRError))
        self.assertFalse(issubclass(TokenQRVencido, TokenQRAlterado))
        self.assertFalse(issubclass(TokenQRAlterado, TokenQRIlegible))
        self.assertFalse(issubclass(TokenQRIlegible, TokenQRVencido))

    def test_no_genera_token_para_vehiculo_ajeno(self):
        """No se genera token si el vehículo es de otro conductor (ValueError)."""
        otro = crear_conductor('pedro@unimonserrate.edu.co')
        with self.assertRaises(ValueError):
            generar_token(otro, self.carro)


@override_settings(QR_SECRET_KEY=LLAVE_PRUEBA)
class EndpointQRTests(APITestCase):
    """GET /api/accesos/qr: elección del vehículo, aislamiento entre conductores y errores."""

    @classmethod
    def setUpTestData(cls):
        """Crea dos conductores, cada uno con un vehículo activo."""
        cls.laura = crear_conductor('laura@unimonserrate.edu.co')
        cls.pedro = crear_conductor('pedro@unimonserrate.edu.co')
        cls.carro_laura = Vehiculo.objects.create(usuario=cls.laura, placa='ABC123', tipo='carro')
        cls.moto_pedro = Vehiculo.objects.create(usuario=cls.pedro, placa='XYZ45K', tipo='moto')

    def test_devuelve_token_del_vehiculo_activo(self):
        """Con un solo vehículo activo devuelve 200 con un token válido de ese vehículo."""
        self.client.force_authenticate(self.laura)
        resp = self.client.get(URL_QR)

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertIn(resp.data['segundos_restantes'], (59, 60))
        self.assertEqual(resp.data['vehiculo']['placa'], 'ABC123')
        datos = validar_token(resp.data['token'])
        self.assertEqual(datos['usuario_id'], str(self.laura.pk))
        self.assertEqual(datos['vehiculo_id'], str(self.carro_laura.pk))
        self.assertEqual(datos['vence_en'], resp.data['vence_en'])

    def test_conductor_no_puede_pedir_el_qr_de_otro(self):
        """Pedir el QR del vehículo de otro conductor responde 404 sin token."""
        self.client.force_authenticate(self.laura)
        resp = self.client.get(URL_QR, {'vehiculo': str(self.moto_pedro.pk)})

        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertNotIn('token', resp.data)

    def test_cada_conductor_recibe_solo_su_vehiculo(self):
        """El token devuelto corresponde siempre al conductor autenticado y a su vehículo."""
        self.client.force_authenticate(self.pedro)
        resp = self.client.get(URL_QR)

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        datos = validar_token(resp.data['token'])
        self.assertEqual(datos['usuario_id'], str(self.pedro.pk))
        self.assertEqual(datos['placa'], 'XYZ45K')

    def test_con_varios_activos_debe_indicar_cual(self):
        """Con varios vehículos activos sin ?vehiculo responde 400; indicándolo, 200."""
        moto = Vehiculo.objects.create(usuario=self.laura, placa='LMN12P', tipo='moto')
        self.client.force_authenticate(self.laura)

        self.assertEqual(self.client.get(URL_QR).status_code, status.HTTP_400_BAD_REQUEST)

        resp = self.client.get(URL_QR, {'vehiculo': str(moto.pk)})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(validar_token(resp.data['token'])['placa'], 'LMN12P')

    def test_vehiculo_inactivo_no_genera_qr(self):
        """Un vehículo inactivo no genera QR, ni por defecto ni pidiéndolo por id (404)."""
        self.carro_laura.activo = False
        self.carro_laura.save(update_fields=['activo'])
        self.client.force_authenticate(self.laura)

        self.assertEqual(self.client.get(URL_QR).status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.get(URL_QR, {'vehiculo': str(self.carro_laura.pk)})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_id_de_vehiculo_invalido(self):
        """Un ?vehiculo que no es UUID responde 400."""
        self.client.force_authenticate(self.laura)
        resp = self.client.get(URL_QR, {'vehiculo': 'no-es-un-uuid'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sin_autenticar_responde_401(self):
        """Sin autenticación el endpoint responde 401."""
        self.assertEqual(self.client.get(URL_QR).status_code, status.HTTP_401_UNAUTHORIZED)
