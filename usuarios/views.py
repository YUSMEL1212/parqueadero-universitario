from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from comun.permisos import EsAdministrador

from . import gestion
from .models import Usuario
from .serializers import (
    CambiarEstadoSerializer,
    CambiarRolSerializer,
    LoginSerializer,
    PerfilSerializer,
    RegistroSerializer,
    UsuarioAdminSerializer,
)

EJEMPLO_PERFIL = {
    'id': '3f2c8a1e-5b7d-4c9a-9e1f-2a6b8c4d0e11',
    'nombre': 'Laura Gómez',
    'email': 'laura.gomez@unimonserrate.edu.co',
    'rol': 'conductor',
    'tipo_conductor': 'estudiante',
    'telefono': '3001234567',
    'creado_en': '2026-11-13T09:10:00-05:00',
}

EJEMPLO_TOKENS = {
    'access': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...',
    'refresh': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...',
}


@extend_schema(
    tags=['auth'],
    summary='Registro de conductor',
    description='Crea una cuenta con rol **conductor**. No es posible registrarse '
    'como guarda o administrador: cualquier campo de rol enviado se ignora.',
    responses={201: PerfilSerializer, 400: OpenApiResponse(description='Datos inválidos')},
    examples=[
        OpenApiExample(
            'Registro',
            request_only=True,
            value={
                'nombre': 'Laura Gómez',
                'email': 'laura.gomez@unimonserrate.edu.co',
                'password': 'Parqueo.Seguro2026',
                'tipo_conductor': 'estudiante',
                'telefono': '3001234567',
            },
        ),
        OpenApiExample('Creado', response_only=True, status_codes=['201'], value=EJEMPLO_PERFIL),
        OpenApiExample(
            'Correo repetido',
            response_only=True,
            status_codes=['400'],
            value={'email': ['Ya existe un usuario con este correo.']},
        ),
    ],
)
class RegistroView(generics.CreateAPIView):
    serializer_class = RegistroSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []


@extend_schema(
    tags=['auth'],
    summary='Login',
    description='Recibe correo y contraseña y devuelve el par de tokens JWT.',
    examples=[
        OpenApiExample(
            'Login',
            request_only=True,
            value={'email': 'laura.gomez@unimonserrate.edu.co', 'password': 'Parqueo.Seguro2026'},
        ),
        OpenApiExample('Tokens', response_only=True, status_codes=['200'], value=EJEMPLO_TOKENS),
    ],
)
class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer


@extend_schema(
    tags=['auth'],
    summary='Refrescar token',
    description='Recibe el token `refresh` y devuelve un `access` nuevo.',
    examples=[
        OpenApiExample('Refresh', request_only=True, value={'refresh': EJEMPLO_TOKENS['refresh']}),
        OpenApiExample(
            'Access nuevo',
            response_only=True,
            status_codes=['200'],
            value={'access': EJEMPLO_TOKENS['access']},
        ),
    ],
)
class RefreshView(TokenRefreshView):
    pass


@extend_schema(
    tags=['auth'],
    summary='Perfil del usuario autenticado',
    examples=[OpenApiExample('Perfil', response_only=True, value=EJEMPLO_PERFIL)],
)
class YoView(generics.RetrieveAPIView):
    serializer_class = PerfilSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


# --- Gestión de usuarios (administrador) --------------------------------------------

EJEMPLO_USUARIO_ADMIN = {
    'id': '3f2c8a1e-5b7d-4c9a-9e1f-2a6b8c4d0e11',
    'nombre': 'Laura Gómez',
    'email': 'laura.gomez@unimonserrate.edu.co',
    'rol': 'conductor',
    'tipo_conductor': 'estudiante',
    'activo': True,
    'creado_en': '2026-11-13T09:10:00-05:00',
}

RESPUESTAS_ADMIN = {
    401: OpenApiResponse(description='Sin token'),
    403: OpenApiResponse(description='El usuario no es administrador'),
    404: OpenApiResponse(description='No existe el usuario'),
}


def _no_permitido(exc):
    return Response(
        {'detail': str(exc), 'codigo': exc.codigo}, status=status.HTTP_400_BAD_REQUEST
    )


class UsuariosView(generics.ListAPIView):
    """GET /api/usuarios: lista de usuarios para el administrador."""

    serializer_class = UsuarioAdminSerializer
    permission_classes = [EsAdministrador]
    pagination_class = None

    def get_queryset(self):
        return gestion.buscar_usuarios(self.request.query_params.get('buscar', ''))

    @extend_schema(
        tags=['usuarios'],
        summary='Lista de usuarios',
        description='Todos los usuarios con su rol y estado, ordenados por nombre. Con '
        '`?buscar=` filtra por nombre o correo (contiene, sin distinguir mayúsculas). '
        'Solo administrador.',
        parameters=[
            OpenApiParameter(
                'buscar',
                OpenApiTypes.STR,
                required=False,
                description='Texto a buscar en el nombre o el correo.',
            )
        ],
        responses={
            200: UsuarioAdminSerializer(many=True),
            401: RESPUESTAS_ADMIN[401],
            403: RESPUESTAS_ADMIN[403],
        },
        examples=[
            OpenApiExample('Usuarios', response_only=True, value=[EJEMPLO_USUARIO_ADMIN])
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class RolUsuarioView(APIView):
    """PATCH /api/usuarios/{id}/rol: cambia el rol de un usuario."""

    permission_classes = [EsAdministrador]

    @extend_schema(
        tags=['usuarios'],
        summary='Cambiar el rol de un usuario',
        description='Asigna `conductor`, `guarda` o `administrador`. El cambio rige desde la '
        'siguiente petición del usuario. Un administrador no puede quitarse a sí mismo el '
        'rol de administrador (400 con `codigo: propio_rol`). Solo administrador.',
        request=CambiarRolSerializer,
        responses={
            200: UsuarioAdminSerializer,
            400: OpenApiResponse(
                description='Rol inválido, o el administrador se quita su propio rol'
            ),
            **RESPUESTAS_ADMIN,
        },
        examples=[
            OpenApiExample('A guarda', request_only=True, value={'rol': 'guarda'}),
            OpenApiExample(
                'Actualizado',
                response_only=True,
                status_codes=['200'],
                value={**EJEMPLO_USUARIO_ADMIN, 'rol': 'guarda'},
            ),
            OpenApiExample(
                'Quitarse el rol',
                response_only=True,
                status_codes=['400'],
                value={
                    'detail': 'No puedes quitarte a ti mismo el rol de administrador. '
                    'Pídeselo a otro administrador.',
                    'codigo': 'propio_rol',
                },
            ),
        ],
    )
    def patch(self, request, pk):
        usuario = get_object_or_404(Usuario.objects.select_related('rol'), pk=pk)
        serializer = CambiarRolSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            gestion.cambiar_rol(usuario, serializer.validated_data['rol'], request.user)
        except gestion.CambioNoPermitido as exc:
            return _no_permitido(exc)
        return Response(UsuarioAdminSerializer(usuario).data)


class UsuarioView(APIView):
    """PATCH /api/usuarios/{id}: activa o desactiva un usuario."""

    permission_classes = [EsAdministrador]

    @extend_schema(
        tags=['usuarios'],
        summary='Activar o desactivar un usuario',
        description='Con `activo: false` el usuario no puede iniciar sesión, sus tokens '
        'dejan de funcionar y la placa de sus vehículos no abre la talanquera por LPR. Un '
        'administrador no puede desactivarse a sí mismo (400 con `codigo: propia_cuenta`). '
        'Solo administrador.',
        request=CambiarEstadoSerializer,
        responses={
            200: UsuarioAdminSerializer,
            400: OpenApiResponse(
                description='Falta `activo`, o el administrador se desactiva a sí mismo'
            ),
            **RESPUESTAS_ADMIN,
        },
        examples=[
            OpenApiExample('Desactivar', request_only=True, value={'activo': False}),
            OpenApiExample(
                'Desactivado',
                response_only=True,
                status_codes=['200'],
                value={**EJEMPLO_USUARIO_ADMIN, 'activo': False},
            ),
        ],
    )
    def patch(self, request, pk):
        usuario = get_object_or_404(Usuario.objects.select_related('rol'), pk=pk)
        serializer = CambiarEstadoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            gestion.cambiar_estado(usuario, serializer.validated_data['activo'], request.user)
        except gestion.CambioNoPermitido as exc:
            return _no_permitido(exc)
        return Response(UsuarioAdminSerializer(usuario).data)
