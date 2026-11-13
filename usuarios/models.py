import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models import Q


class NombreRol(models.TextChoices):
    ADMINISTRADOR = 'administrador', 'Administrador'
    GUARDA = 'guarda', 'Guarda'
    CONDUCTOR = 'conductor', 'Conductor'


class Rol(models.Model):
    Nombre = NombreRol

    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=30, unique=True, choices=NombreRol.choices)

    class Meta:
        db_table = 'roles'
        verbose_name = 'rol'
        verbose_name_plural = 'roles'
        constraints = [
            models.CheckConstraint(
                condition=Q(nombre__in=NombreRol.values),
                name='roles_nombre_valido',
            ),
        ]

    def __str__(self):
        return self.get_nombre_display()


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('El email es obligatorio.')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, rol=None, **extra_fields):
        if rol is None:
            rol, _ = Rol.objects.get_or_create(nombre=Rol.Nombre.CONDUCTOR)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, rol=rol, **extra_fields)

    def create_superuser(self, email, password=None, rol=None, **extra_fields):
        if rol is None:
            rol, _ = Rol.objects.get_or_create(nombre=Rol.Nombre.ADMINISTRADOR)
        extra_fields.setdefault('is_superuser', True)
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Un superusuario debe tener is_superuser=True.')
        return self._create_user(email, password, rol=rol, **extra_fields)


class TipoConductor(models.TextChoices):
    ESTUDIANTE = 'estudiante', 'Estudiante'
    DOCENTE = 'docente', 'Docente'
    ADMINISTRATIVO = 'administrativo', 'Administrativo'


class Usuario(AbstractBaseUser, PermissionsMixin):
    TipoConductor = TipoConductor

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, related_name='usuarios')
    nombre = models.CharField(max_length=120)
    email = models.EmailField(max_length=160, unique=True)
    # password viene de AbstractBaseUser (hash de Django).
    tipo_conductor = models.CharField(
        max_length=20,
        choices=TipoConductor.choices,
        null=True,
        blank=True,
        help_text='Solo para conductores; NULL para guarda y administrador.',
    )
    telefono = models.CharField(max_length=20, blank=True, default='')
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    objects = UsuarioManager()

    USERNAME_FIELD = 'email'
    EMAIL_FIELD = 'email'
    REQUIRED_FIELDS = ['nombre']

    class Meta:
        db_table = 'usuarios'
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'
        constraints = [
            models.CheckConstraint(
                condition=Q(tipo_conductor__in=TipoConductor.values)
                | Q(tipo_conductor__isnull=True),
                name='usuarios_tipo_conductor_valido',
            ),
        ]

    def __str__(self):
        return f'{self.nombre} <{self.email}>'

    # Django (login, admin) espera is_active / is_staff; se derivan de los campos
    # del modelo de datos en lugar de agregar columnas nuevas.
    @property
    def is_active(self):
        return self.activo

    @property
    def is_staff(self):
        return self.is_superuser or self.rol.nombre == Rol.Nombre.ADMINISTRADOR
