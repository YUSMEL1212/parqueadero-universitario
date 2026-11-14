"""Pruebas de la gestión de usuarios por el administrador: lista, rol y activación."""

import uuid

from rest_framework import status
from rest_framework.test import APITestCase

from .models import NombreRol, Rol, Usuario

URL_USUARIOS = '/api/usuarios'
CLAVE = 'Parqueo.Seguro2026'


def url_usuario(usuario):
    return f'{URL_USUARIOS}/{usuario.pk}'


def url_rol(usuario):
    return f'{URL_USUARIOS}/{usuario.pk}/rol'


def crear_usuario(email, rol, nombre, **extra):
    rol, _ = Rol.objects.get_or_create(nombre=rol)
    return Usuario.objects.create_user(email, CLAVE, rol=rol, nombre=nombre, **extra)


class GestionUsuariosTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = crear_usuario('ana@parqueadero.test', NombreRol.ADMINISTRADOR, 'Ana Admin')
        cls.guarda = crear_usuario('pedro@parqueadero.test', NombreRol.GUARDA, 'Pedro Guarda')
        cls.laura = crear_usuario(
            'laura.gomez@unimonserrate.edu.co',
            NombreRol.CONDUCTOR,
            'Laura Gómez',
            tipo_conductor='estudiante',
        )

    def setUp(self):
        self.client.force_authenticate(self.admin)


class ListaUsuariosTests(GestionUsuariosTestCase):
    def test_lista_todos_con_nombre_correo_rol_y_estado(self):
        resp = self.client.get(URL_USUARIOS)

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(
            [u['nombre'] for u in resp.data], ['Ana Admin', 'Laura Gómez', 'Pedro Guarda']
        )
        laura = resp.data[1]
        self.assertEqual(laura['email'], 'laura.gomez@unimonserrate.edu.co')
        self.assertEqual(laura['rol'], 'conductor')
        self.assertIs(laura['activo'], True)
        self.assertNotIn('password', laura)

    def test_busca_por_nombre_o_correo_sin_distinguir_mayusculas(self):
        por_nombre = self.client.get(URL_USUARIOS, {'buscar': 'GÓMEZ'})
        por_correo = self.client.get(URL_USUARIOS, {'buscar': 'parqueadero.test'})
        sin_resultados = self.client.get(URL_USUARIOS, {'buscar': 'nadie'})

        self.assertEqual([u['nombre'] for u in por_nombre.data], ['Laura Gómez'])
        self.assertEqual(
            [u['nombre'] for u in por_correo.data], ['Ana Admin', 'Pedro Guarda']
        )
        self.assertEqual(sin_resultados.data, [])

    def test_solo_el_administrador_ve_la_lista(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(URL_USUARIOS).status_code, status.HTTP_401_UNAUTHORIZED)
        for usuario in (self.guarda, self.laura):
            self.client.force_authenticate(usuario)
            self.assertEqual(self.client.get(URL_USUARIOS).status_code, status.HTTP_403_FORBIDDEN)


class CambioDeRolTests(GestionUsuariosTestCase):
    def test_cambia_el_rol_de_otro_usuario(self):
        resp = self.client.patch(url_rol(self.laura), {'rol': 'guarda'}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['rol'], 'guarda')
        self.laura.refresh_from_db()
        self.assertEqual(self.laura.rol.nombre, NombreRol.GUARDA)

    def test_el_nuevo_rol_rige_en_la_siguiente_peticion(self):
        self.client.patch(url_rol(self.guarda), {'rol': 'administrador'}, format='json')

        self.client.force_authenticate(Usuario.objects.get(pk=self.guarda.pk))
        self.assertEqual(self.client.get(URL_USUARIOS).status_code, status.HTTP_200_OK)

    def test_crea_el_rol_si_aun_no_existe_en_la_tabla(self):
        self.guarda.delete()
        Rol.objects.filter(nombre=NombreRol.GUARDA).delete()

        resp = self.client.patch(url_rol(self.laura), {'rol': 'guarda'}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertTrue(Rol.objects.filter(nombre=NombreRol.GUARDA).exists())

    def test_rechaza_un_rol_que_no_existe(self):
        resp = self.client.patch(url_rol(self.laura), {'rol': 'superusuario'}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('rol', resp.data)
        self.laura.refresh_from_db()
        self.assertEqual(self.laura.rol.nombre, NombreRol.CONDUCTOR)

    def test_un_administrador_no_puede_quitarse_su_propio_rol(self):
        for rol in ('guarda', 'conductor'):
            resp = self.client.patch(url_rol(self.admin), {'rol': rol}, format='json')

            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(resp.data['codigo'], 'propio_rol')
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.rol.nombre, NombreRol.ADMINISTRADOR)

    def test_reasignarse_administrador_a_si_mismo_no_es_error(self):
        resp = self.client.patch(url_rol(self.admin), {'rol': 'administrador'}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

    def test_puede_quitarle_el_rol_a_otro_administrador(self):
        otro = crear_usuario('beto@parqueadero.test', NombreRol.ADMINISTRADOR, 'Beto Admin')

        resp = self.client.patch(url_rol(otro), {'rol': 'conductor'}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['rol'], 'conductor')

    def test_usuario_inexistente_responde_404(self):
        resp = self.client.patch(
            f'{URL_USUARIOS}/{uuid.uuid4()}/rol', {'rol': 'guarda'}, format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_solo_el_administrador_cambia_roles(self):
        self.client.force_authenticate(self.guarda)
        resp = self.client.patch(url_rol(self.guarda), {'rol': 'administrador'}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.guarda.refresh_from_db()
        self.assertEqual(self.guarda.rol.nombre, NombreRol.GUARDA)


class ActivacionTests(GestionUsuariosTestCase):
    def test_desactiva_y_reactiva_un_usuario(self):
        resp = self.client.patch(url_usuario(self.laura), {'activo': False}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertIs(resp.data['activo'], False)
        self.laura.refresh_from_db()
        self.assertFalse(self.laura.activo)

        resp = self.client.patch(url_usuario(self.laura), {'activo': True}, format='json')
        self.assertIs(resp.data['activo'], True)

    def test_un_usuario_desactivado_no_puede_iniciar_sesion(self):
        self.client.patch(url_usuario(self.laura), {'activo': False}, format='json')
        self.client.force_authenticate(None)

        resp = self.client.post(
            '/api/auth/login',
            {'email': 'laura.gomez@unimonserrate.edu.co', 'password': CLAVE},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_exige_el_campo_activo(self):
        resp = self.client.patch(url_usuario(self.laura), {'rol': 'guarda'}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('activo', resp.data)
        self.laura.refresh_from_db()
        self.assertEqual(self.laura.rol.nombre, NombreRol.CONDUCTOR)

    def test_un_administrador_no_puede_desactivarse_a_si_mismo(self):
        resp = self.client.patch(url_usuario(self.admin), {'activo': False}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['codigo'], 'propia_cuenta')
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.activo)

    def test_solo_el_administrador_activa_o_desactiva(self):
        self.client.force_authenticate(self.laura)
        resp = self.client.patch(url_usuario(self.guarda), {'activo': False}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.guarda.refresh_from_db()
        self.assertTrue(self.guarda.activo)
