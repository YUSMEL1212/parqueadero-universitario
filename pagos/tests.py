"""Pruebas de GET /api/mensualidades/vigentes."""

from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from usuarios.models import NombreRol, Rol, Usuario

from .models import Mensualidad, Pago

URL = '/api/mensualidades/vigentes'


def crear_conductor(email):
    return Usuario.objects.create_user(
        email, 'Parqueo.Seguro2026', nombre=email.split('@')[0], tipo_conductor='estudiante'
    )


def crear_mensualidad(usuario, tipo, inicia_en):
    pago = Pago.objects.create(
        usuario=usuario,
        concepto=Pago.Concepto.MENSUALIDAD,
        valor=75000,
        metodo=Pago.Metodo.TARJETA,
        estado=Pago.Estado.APROBADO,
        pagado_en=inicia_en,
    )
    return Mensualidad.objects.create(
        usuario=usuario, pago=pago, tipo_vehiculo=tipo, inicia_en=inicia_en
    )


class MensualidadesVigentesTests(APITestCase):
    def setUp(self):
        self.conductor = crear_conductor('laura@unimonserrate.edu.co')
        self.client.force_authenticate(self.conductor)

    def test_sin_mensualidad_devuelve_lista_vacia(self):
        respuesta = self.client.get(URL)
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data, [])

    def test_solo_las_vigentes_y_propias(self):
        ahora = timezone.now()
        vigente = crear_mensualidad(self.conductor, 'carro', ahora - timedelta(days=5))
        crear_mensualidad(self.conductor, 'moto', ahora - timedelta(days=40))  # vencida
        crear_mensualidad(crear_conductor('otro@unimonserrate.edu.co'), 'moto', ahora)

        respuesta = self.client.get(URL)

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual([m['id'] for m in respuesta.data], [str(vigente.id)])
        self.assertEqual(respuesta.data[0]['tipo_vehiculo'], 'carro')

    def test_sin_sesion_responde_401(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_un_guarda_no_puede_consultar(self):
        guarda = crear_conductor('guarda@unimonserrate.edu.co')
        guarda.rol = Rol.objects.get_or_create(nombre=NombreRol.GUARDA)[0]
        guarda.save()
        self.client.force_authenticate(guarda)
        self.assertEqual(self.client.get(URL).status_code, status.HTTP_403_FORBIDDEN)
