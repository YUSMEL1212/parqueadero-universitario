from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accesos.models import Ticket
from usuarios.models import NombreRol, Rol, Usuario

from .models import Vehiculo

LISTA = '/api/vehiculos'
CLAVE = 'Parqueo.Seguro2026'


def detalle(vehiculo):
    return f'{LISTA}/{vehiculo.pk}'


def crear_conductor(email):
    return Usuario.objects.create_user(
        email, CLAVE, nombre=email.split('@')[0], tipo_conductor='estudiante'
    )


class CrearVehiculoTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.conductor = crear_conductor('laura@unimonserrate.edu.co')

    def setUp(self):
        self.client.force_authenticate(self.conductor)

    def test_placa_de_carro_valida(self):
        resp = self.client.post(LISTA, {'placa': 'ABC123', 'tipo': 'carro'}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['placa'], 'ABC123')
        vehiculo = Vehiculo.objects.get(placa='ABC123')
        self.assertEqual(vehiculo.tipo, 'carro')
        self.assertEqual(vehiculo.usuario, self.conductor)

    def test_placa_de_moto_valida(self):
        resp = self.client.post(LISTA, {'placa': 'XYZ45K', 'tipo': 'moto'}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(Vehiculo.objects.get(placa='XYZ45K').tipo, 'moto')

    def test_placa_con_formato_equivocado_para_el_tipo(self):
        # Placa de carro registrada como moto y placa de moto registrada como carro.
        resp = self.client.post(LISTA, {'placa': 'ABC123', 'tipo': 'moto'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            resp.data['placa'], ['Placa no válida para moto: debe tener el formato ABC12D.']
        )

        resp = self.client.post(LISTA, {'placa': 'XYZ45K', 'tipo': 'carro'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            resp.data['placa'], ['Placa no válida para carro: debe tener el formato ABC123.']
        )

        self.assertFalse(Vehiculo.objects.exists())

    def test_placa_duplicada(self):
        otro = crear_conductor('pedro@unimonserrate.edu.co')
        Vehiculo.objects.create(usuario=otro, placa='ABC123', tipo='carro')

        # Escrita distinto, pero normalizada es la misma placa.
        resp = self.client.post(LISTA, {'placa': 'abc-123', 'tipo': 'carro'}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['placa'], ['Ya existe un vehículo registrado con esta placa.'])
        self.assertEqual(Vehiculo.objects.count(), 1)

    def test_normaliza_minusculas_guion_y_espacios(self):
        resp = self.client.post(LISTA, {'placa': 'abc-123', 'tipo': 'carro'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['placa'], 'ABC123')

        resp = self.client.post(LISTA, {'placa': ' xyz 45-k ', 'tipo': 'moto'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['placa'], 'XYZ45K')

        self.assertEqual(
            set(Vehiculo.objects.values_list('placa', flat=True)), {'ABC123', 'XYZ45K'}
        )

    def test_el_usuario_lo_pone_el_servidor(self):
        otro = crear_conductor('pedro@unimonserrate.edu.co')

        resp = self.client.post(
            LISTA, {'placa': 'ABC123', 'tipo': 'carro', 'usuario': str(otro.pk)}, format='json'
        )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(Vehiculo.objects.get(placa='ABC123').usuario, self.conductor)

    def test_sin_token_es_401(self):
        self.client.force_authenticate(None)

        resp = self.client.post(LISTA, {'placa': 'ABC123', 'tipo': 'carro'}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class AislamientoEntreConductoresTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.laura = crear_conductor('laura@unimonserrate.edu.co')
        cls.pedro = crear_conductor('pedro@unimonserrate.edu.co')
        cls.carro_laura = Vehiculo.objects.create(usuario=cls.laura, placa='ABC123', tipo='carro')
        cls.moto_pedro = Vehiculo.objects.create(usuario=cls.pedro, placa='XYZ45K', tipo='moto')
        rol_admin, _ = Rol.objects.get_or_create(nombre=NombreRol.ADMINISTRADOR)
        cls.admin = Usuario.objects.create_user(
            'admin@unimonserrate.edu.co', CLAVE, nombre='Admin', rol=rol_admin
        )

    def test_conductor_no_puede_ver_el_vehiculo_de_otro(self):
        self.client.force_authenticate(self.laura)

        lista = self.client.get(LISTA)
        self.assertEqual(lista.status_code, status.HTTP_200_OK)
        self.assertEqual([v['placa'] for v in lista.data], ['ABC123'])

        self.assertEqual(
            self.client.get(detalle(self.moto_pedro)).status_code, status.HTTP_404_NOT_FOUND
        )

    def test_conductor_no_puede_modificar_ni_borrar_el_vehiculo_de_otro(self):
        self.client.force_authenticate(self.laura)

        resp = self.client.patch(detalle(self.moto_pedro), {'placa': 'QWE12R'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.delete(detalle(self.moto_pedro))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.moto_pedro.refresh_from_db()
        self.assertEqual(self.moto_pedro.placa, 'XYZ45K')

    def test_administrador_ve_todos(self):
        self.client.force_authenticate(self.admin)

        lista = self.client.get(LISTA)
        self.assertEqual({v['placa'] for v in lista.data}, {'ABC123', 'XYZ45K'})
        self.assertEqual(
            self.client.get(detalle(self.moto_pedro)).status_code, status.HTTP_200_OK
        )


class ModificarYEliminarTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.conductor = crear_conductor('laura@unimonserrate.edu.co')

    def setUp(self):
        self.client.force_authenticate(self.conductor)
        self.vehiculo = Vehiculo.objects.create(
            usuario=self.conductor, placa='ABC123', tipo='carro'
        )

    def abrir_ticket(self, **cambios):
        datos = dict(
            vehiculo=self.vehiculo,
            usuario=self.conductor,
            tipo_ingreso=Ticket.TipoIngreso.REGISTRADO,
            metodo_ingreso=Ticket.MetodoIngreso.QR,
            hora_entrada=timezone.now(),
        )
        datos.update(cambios)
        return Ticket.objects.create(**datos)

    def test_patch_valida_la_combinacion_final_de_placa_y_tipo(self):
        # Cambiar solo el tipo a moto deja ABC123, que no es placa de moto.
        resp = self.client.patch(detalle(self.vehiculo), {'tipo': 'moto'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        resp = self.client.patch(
            detalle(self.vehiculo), {'placa': 'abc-12d', 'tipo': 'moto'}, format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['placa'], 'ABC12D')

    def test_put_no_esta_permitido(self):
        resp = self.client.put(
            detalle(self.vehiculo), {'placa': 'ABC123', 'tipo': 'carro'}, format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_tiene_ticket_abierto(self):
        self.assertFalse(self.vehiculo.tiene_ticket_abierto())

        ticket = self.abrir_ticket()
        self.assertTrue(self.vehiculo.tiene_ticket_abierto())

        ticket.hora_salida = timezone.now()
        ticket.save()
        self.assertFalse(self.vehiculo.tiene_ticket_abierto())

    def test_no_se_cambia_placa_ni_tipo_con_el_vehiculo_adentro(self):
        self.abrir_ticket()

        resp = self.client.patch(detalle(self.vehiculo), {'placa': 'DEF456'}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.vehiculo.refresh_from_db()
        self.assertEqual(self.vehiculo.placa, 'ABC123')

    def test_eliminar_sin_historial_borra(self):
        resp = self.client.delete(detalle(self.vehiculo))

        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Vehiculo.objects.exists())

    def test_eliminar_con_historial_desactiva(self):
        self.abrir_ticket(hora_salida=timezone.now())

        resp = self.client.delete(detalle(self.vehiculo))

        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.vehiculo.refresh_from_db()
        self.assertFalse(self.vehiculo.activo)

    def test_eliminar_con_el_vehiculo_adentro_es_409(self):
        self.abrir_ticket()

        resp = self.client.delete(detalle(self.vehiculo))

        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(Vehiculo.objects.filter(pk=self.vehiculo.pk, activo=True).exists())
