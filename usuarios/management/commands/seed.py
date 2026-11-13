"""
Carga los datos iniciales del sistema (docs/modelo-datos.md, sección "Datos iniciales").

Es idempotente: cada registro se busca por su llave natural (nombre del rol, email,
placa, código de bahía, bahía del sensor, tipo + concepto de la tarifa vigente) y solo
se crea si no existe. Correrlo varias veces no duplica nada ni modifica lo existente.

Las contraseñas de prueba se leen de las variables de entorno SEED_*_PASSWORD
(ver .env.example); nunca van en el código.
"""

from decouple import UndefinedValueError, config
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from iot.models import Bahia, Sensor
from tarifas.models import ConceptoTarifa, Tarifa
from usuarios.models import Rol, TipoConductor, Usuario
from vehiculos.models import TipoVehiculo, Vehiculo

ROLES = [Rol.Nombre.ADMINISTRADOR, Rol.Nombre.GUARDA, Rol.Nombre.CONDUCTOR]

# (email, nombre, rol, tipo_conductor, variable de entorno con la contraseña)
USUARIOS = [
    ('admin@parqueadero.test', 'Administrador', Rol.Nombre.ADMINISTRADOR, None,
     'SEED_ADMIN_PASSWORD'),
    ('guarda1@parqueadero.test', 'Guarda Uno', Rol.Nombre.GUARDA, None,
     'SEED_GUARDA_PASSWORD'),
    ('guarda2@parqueadero.test', 'Guarda Dos', Rol.Nombre.GUARDA, None,
     'SEED_GUARDA_PASSWORD'),
    ('estudiante@parqueadero.test', 'Conductor Estudiante', Rol.Nombre.CONDUCTOR,
     TipoConductor.ESTUDIANTE, 'SEED_CONDUCTOR_PASSWORD'),
    ('docente@parqueadero.test', 'Conductor Docente', Rol.Nombre.CONDUCTOR,
     TipoConductor.DOCENTE, 'SEED_CONDUCTOR_PASSWORD'),
    ('administrativo@parqueadero.test', 'Conductor Administrativo', Rol.Nombre.CONDUCTOR,
     TipoConductor.ADMINISTRATIVO, 'SEED_CONDUCTOR_PASSWORD'),
]

# (placa, tipo, email del dueño)
VEHICULOS = [
    ('ABC123', TipoVehiculo.CARRO, 'estudiante@parqueadero.test'),
    ('XYZ12A', TipoVehiculo.MOTO, 'docente@parqueadero.test'),
    ('DEF456', TipoVehiculo.CARRO, 'administrativo@parqueadero.test'),
]

# 8 bahías de carro (C-01..C-08) y 4 de moto (M-01..M-04).
BAHIAS = (
    [(f'C-{i:02d}', TipoVehiculo.CARRO) for i in range(1, 9)]
    + [(f'M-{i:02d}', TipoVehiculo.MOTO) for i in range(1, 5)]
)

# Valores iniciales en pesos colombianos. Después de esto, el motor de cobro
# solo lee la tabla `tarifas`.
TARIFAS = [
    (TipoVehiculo.CARRO, ConceptoTarifa.HASTA_2H, 7000),
    (TipoVehiculo.CARRO, ConceptoTarifa.MAS_2H, 12000),
    (TipoVehiculo.CARRO, ConceptoTarifa.MENSUALIDAD, 75000),
    (TipoVehiculo.MOTO, ConceptoTarifa.HASTA_2H, 5000),
    (TipoVehiculo.MOTO, ConceptoTarifa.MAS_2H, 9000),
    (TipoVehiculo.MOTO, ConceptoTarifa.MENSUALIDAD, 56000),
]


def device_uid_para(codigo_bahia):
    """C-01 -> ESP32-C01 (formato del contrato IoT)."""
    return f"ESP32-{codigo_bahia.replace('-', '')}"


class Command(BaseCommand):
    help = 'Carga los datos iniciales (roles, usuarios, vehículos, bahías, sensores, tarifas).'

    def handle(self, *args, **options):
        passwords = self._leer_passwords()
        self.resumen = []  # (entidad, creados, existentes)
        self.avisos = []

        with transaction.atomic():
            roles = self._seed_roles()
            usuarios = self._seed_usuarios(roles, passwords)
            self._seed_vehiculos(usuarios)
            self._seed_bahias_y_sensores()
            self._seed_tarifas(usuarios['admin@parqueadero.test'])

        self._imprimir_resumen()

    # --- lectura de configuración -------------------------------------------------

    def _leer_passwords(self):
        nombres = sorted({var for *_, var in USUARIOS})
        passwords, faltantes = {}, []
        for nombre in nombres:
            try:
                valor = config(nombre)
            except UndefinedValueError:
                valor = ''
            if not valor:
                faltantes.append(nombre)
            passwords[nombre] = valor
        if faltantes:
            raise CommandError(
                'Faltan variables de entorno para las contraseñas de prueba: '
                f"{', '.join(faltantes)}. Cópialas de .env.example a tu .env."
            )
        return passwords

    # --- seeders --------------------------------------------------------------------

    def _seed_roles(self):
        roles, creados = {}, 0
        for nombre in ROLES:
            rol, creado = Rol.objects.get_or_create(nombre=nombre)
            roles[nombre] = rol
            creados += creado
        self._registrar('Roles', creados, len(ROLES))
        return roles

    def _seed_usuarios(self, roles, passwords):
        usuarios = {}
        creados_por_rol = {rol: 0 for rol in ROLES}
        total_por_rol = {rol: 0 for rol in ROLES}
        for email, nombre, rol, tipo_conductor, var_password in USUARIOS:
            total_por_rol[rol] += 1
            usuario = Usuario.objects.filter(email=email).first()
            if usuario is None:
                crear = (
                    Usuario.objects.create_superuser
                    if rol == Rol.Nombre.ADMINISTRADOR
                    else Usuario.objects.create_user
                )
                usuario = crear(
                    email=email,
                    password=passwords[var_password],
                    rol=roles[rol],
                    nombre=nombre,
                    tipo_conductor=tipo_conductor,
                )
                creados_por_rol[rol] += 1
            usuarios[email] = usuario
        etiquetas = {
            Rol.Nombre.ADMINISTRADOR: 'Administradores',
            Rol.Nombre.GUARDA: 'Guardas',
            Rol.Nombre.CONDUCTOR: 'Conductores',
        }
        for rol in ROLES:
            self._registrar(etiquetas[rol], creados_por_rol[rol], total_por_rol[rol])
        return usuarios

    def _seed_vehiculos(self, usuarios):
        creados = 0
        for placa, tipo, email in VEHICULOS:
            if Vehiculo.objects.filter(placa=placa).exists():
                continue
            vehiculo = Vehiculo(placa=placa, tipo=tipo, usuario=usuarios[email])
            vehiculo.full_clean()  # valida el formato de placa según el tipo
            vehiculo.save()
            creados += 1
        self._registrar('Vehículos', creados, len(VEHICULOS))

    def _seed_bahias_y_sensores(self):
        bahias_creadas = sensores_creados = 0
        for codigo, tipo in BAHIAS:
            bahia, creada = Bahia.objects.get_or_create(
                codigo=codigo, defaults={'tipo_vehiculo': tipo}
            )
            bahias_creadas += creada
            _, creado = Sensor.objects.get_or_create(
                bahia=bahia, defaults={'device_uid': device_uid_para(codigo)}
            )
            sensores_creados += creado
        self._registrar('Bahías', bahias_creadas, len(BAHIAS))
        self._registrar('Sensores', sensores_creados, len(BAHIAS))

    def _seed_tarifas(self, admin):
        creadas = 0
        ahora = timezone.now()
        for tipo, concepto, valor in TARIFAS:
            vigente = Tarifa.objects.filter(
                tipo_vehiculo=tipo, concepto=concepto, vigente_hasta__isnull=True
            ).first()
            if vigente is None:
                Tarifa.objects.create(
                    tipo_vehiculo=tipo,
                    concepto=concepto,
                    valor=valor,
                    vigente_desde=ahora,
                    creado_por=admin,
                )
                creadas += 1
            elif vigente.valor != valor:
                # No se pisa una tarifa vigente: los cambios de tarifa se hacen
                # cerrando la vigencia y creando una fila nueva (historial).
                self.avisos.append(
                    f'Tarifa vigente {tipo}/{concepto} = {vigente.valor} '
                    f'(el seed trae {valor}); se deja como está.'
                )
        self._registrar('Tarifas vigentes', creadas, len(TARIFAS))

    # --- salida ---------------------------------------------------------------------

    def _registrar(self, entidad, creados, total):
        self.resumen.append((entidad, creados, total - creados))

    def _imprimir_resumen(self):
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Resumen del seed'))
        self.stdout.write(f"  {'Entidad':<18}{'Creados':>9}{'Ya existían':>14}")
        for entidad, creados, existentes in self.resumen:
            self.stdout.write(f'  {entidad:<18}{creados:>9}{existentes:>14}')
        total = sum(c for _, c, _ in self.resumen)
        self.stdout.write('')
        if total:
            self.stdout.write(self.style.SUCCESS(f'Se crearon {total} registros.'))
        else:
            self.stdout.write(self.style.SUCCESS('Nada que crear: los datos ya estaban cargados.'))
        for aviso in self.avisos:
            self.stdout.write(self.style.WARNING(f'Aviso: {aviso}'))

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Usuarios de prueba'))
        for email, _, rol, tipo_conductor, var_password in USUARIOS:
            detalle = f'{rol}' + (f' ({tipo_conductor})' if tipo_conductor else '')
            self.stdout.write(f'  {email:<34}{detalle:<28}clave: ${var_password}')
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Vehículos'))
        for placa, tipo, email in VEHICULOS:
            self.stdout.write(f'  {placa}  {tipo:<6} {email}')
