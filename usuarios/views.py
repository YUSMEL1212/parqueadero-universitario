from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import generics, permissions
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import LoginSerializer, PerfilSerializer, RegistroSerializer

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
