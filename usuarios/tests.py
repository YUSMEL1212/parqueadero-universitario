from django.test import override_settings
from django.urls import include, path
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APITestCase
from rest_framework.views import APIView

from comun.permisos import EsAdministrador

from .models import NombreRol, Rol, Usuario

REGISTRO = '/api/auth/registro'
LOGIN = '/api/auth/login'
REFRESH = '/api/auth/refresh'
YO = '/api/auth/yo'
SOLO_ADMIN = '/api/pruebas/solo-admin'

CLAVE = 'Parqueo.Seguro2026'


class SoloAdministradorView(APIView):
    """Endpoint de prueba restringido a administrador (solo existe en los tests)."""

    permission_classes = [EsAdministrador]

    def get(self, request):
        return Response({'ok': True})


# URLconf usada por los tests: las rutas reales más el endpoint de prueba.
urlpatterns = [
    path('api/auth/', include('usuarios.urls')),
    path('api/pruebas/solo-admin', SoloAdministradorView.as_view()),
]


def datos_registro(**cambios):
    datos = {
        'nombre': 'Laura Gómez',
        'email': 'laura.gomez@unimonserrate.edu.co',
        'password': CLAVE,
        'tipo_conductor': 'estudiante',
        'telefono': '3001234567',
    }
    datos.update(cambios)
    return datos


@override_settings(ROOT_URLCONF='usuarios.tests')
class RegistroTests(APITestCase):
    def test_registro_correcto_crea_conductor(self):
        # Aunque el cliente intente elegir rol o superusuario, se ignora.
        resp = self.client.post(
            REGISTRO,
            datos_registro(rol='administrador', is_superuser=True),
            format='json',
        )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['rol'], NombreRol.CONDUCTOR)
        self.assertNotIn('password', resp.data)
        usuario = Usuario.objects.get(email='laura.gomez@unimonserrate.edu.co')
        self.assertEqual(usuario.rol.nombre, NombreRol.CONDUCTOR)
        self.assertFalse(usuario.is_superuser)
        self.assertTrue(usuario.check_password(CLAVE))

    def test_registro_con_correo_repetido(self):
        self.client.post(REGISTRO, datos_registro(), format='json')

        resp = self.client.post(
            REGISTRO,
            datos_registro(email='Laura.Gomez@Unimonserrate.edu.co', nombre='Otra'),
            format='json',
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', resp.data)
        self.assertEqual(Usuario.objects.count(), 1)

    def test_registro_rechaza_correo_invalido_y_clave_debil(self):
        resp = self.client.post(
            REGISTRO, datos_registro(email='no-es-un-correo'), format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', resp.data)

        resp = self.client.post(REGISTRO, datos_registro(password='12345678'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', resp.data)
        self.assertFalse(Usuario.objects.exists())


@override_settings(ROOT_URLCONF='usuarios.tests')
class LoginTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = Usuario.objects.create_user(
            'laura.gomez@unimonserrate.edu.co',
            CLAVE,
            nombre='Laura Gómez',
            tipo_conductor='estudiante',
        )

    def test_login_correcto_devuelve_tokens(self):
        resp = self.client.post(
            LOGIN,
            {'email': 'laura.gomez@unimonserrate.edu.co', 'password': CLAVE},
            format='json',
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertIn('access', resp.data)
        self.assertIn('refresh', resp.data)

        # El access sirve para pedir el perfil y el refresh para obtener otro access.
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')
        perfil = self.client.get(YO)
        self.assertEqual(perfil.status_code, status.HTTP_200_OK)
        self.assertEqual(perfil.data['email'], 'laura.gomez@unimonserrate.edu.co')
        self.assertEqual(perfil.data['rol'], NombreRol.CONDUCTOR)

        self.client.credentials()
        refresco = self.client.post(REFRESH, {'refresh': resp.data['refresh']}, format='json')
        self.assertEqual(refresco.status_code, status.HTTP_200_OK)
        self.assertIn('access', refresco.data)

    def test_login_con_clave_mala(self):
        resp = self.client.post(
            LOGIN,
            {'email': 'laura.gomez@unimonserrate.edu.co', 'password': 'clave-incorrecta'},
            format='json',
        )

        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn('access', resp.data)

    def test_perfil_sin_token_es_401(self):
        self.assertEqual(self.client.get(YO).status_code, status.HTTP_401_UNAUTHORIZED)


@override_settings(ROOT_URLCONF='usuarios.tests')
class PermisosPorRolTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.conductor = Usuario.objects.create_user(
            'conductor@unimonserrate.edu.co', CLAVE, nombre='Conductor', tipo_conductor='docente'
        )
        rol_admin, _ = Rol.objects.get_or_create(nombre=NombreRol.ADMINISTRADOR)
        cls.admin = Usuario.objects.create_user(
            'admin@unimonserrate.edu.co', CLAVE, nombre='Admin', rol=rol_admin
        )

    def autenticar(self, email):
        resp = self.client.post(LOGIN, {'email': email, 'password': CLAVE}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {resp.data["access"]}')

    def test_conductor_recibe_403_en_endpoint_de_administrador(self):
        self.autenticar('conductor@unimonserrate.edu.co')

        resp = self.client.get(SOLO_ADMIN)

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_administrador_accede_a_endpoint_de_administrador(self):
        self.autenticar('admin@unimonserrate.edu.co')

        resp = self.client.get(SOLO_ADMIN)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)


@override_settings(CORS_ALLOWED_ORIGINS=['http://localhost:5173'])
class CorsTests(APITestCase):
    """El frontend (PWA) llama a la API desde otro origen."""

    def test_preflight_desde_origen_permitido(self):
        res = self.client.options(
            LOGIN,
            HTTP_ORIGIN='http://localhost:5173',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res['Access-Control-Allow-Origin'], 'http://localhost:5173')
        self.assertIn('authorization', res['Access-Control-Allow-Headers'])

    def test_origen_no_permitido_no_recibe_cabecera(self):
        res = self.client.post(
            LOGIN,
            {'email': 'x@x.co', 'password': 'x'},
            HTTP_ORIGIN='http://sitio-ajeno.example',
        )
        self.assertNotIn('Access-Control-Allow-Origin', res)
