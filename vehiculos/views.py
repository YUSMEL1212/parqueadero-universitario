from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response

from comun.permisos import EsAdministrador

from .models import Vehiculo
from .serializers import VehiculoSerializer

EJEMPLO_VEHICULO = {
    'id': '7b1e4c2a-9d3f-4e8b-a6c5-1f2d3e4a5b6c',
    'placa': 'ABC123',
    'tipo': 'carro',
    'activo': True,
    'usuario': '3f2c8a1e-5b7d-4c9a-9e1f-2a6b8c4d0e11',
    'creado_en': '2026-11-13T09:10:00-05:00',
}

EJEMPLOS_ERROR_400 = [
    OpenApiExample(
        'Placa con formato equivocado',
        response_only=True,
        status_codes=['400'],
        value={'placa': ['Placa no válida para moto: debe tener el formato ABC12D.']},
    ),
    OpenApiExample(
        'Placa duplicada',
        response_only=True,
        status_codes=['400'],
        value={'placa': ['Ya existe un vehículo registrado con esta placa.']},
    ),
]

NO_ENCONTRADO = OpenApiResponse(
    description='No existe o pertenece a otro conductor.'
)


@extend_schema_view(
    list=extend_schema(
        summary='Listar vehículos',
        description='El conductor ve solo sus vehículos; el administrador ve todos.',
        examples=[OpenApiExample('Lista', response_only=True, value=[EJEMPLO_VEHICULO])],
    ),
    create=extend_schema(
        summary='Registrar vehículo',
        description='Registra un vehículo para el usuario autenticado. La placa se '
        'normaliza (sin guion, sin espacios, en mayúsculas) y se valida según el tipo: '
        'carro `ABC123`, moto `ABC12D`.',
        responses={201: VehiculoSerializer, 400: OpenApiResponse(description='Datos inválidos')},
        examples=[
            OpenApiExample('Carro', request_only=True, value={'placa': 'abc-123', 'tipo': 'carro'}),
            OpenApiExample('Moto', request_only=True, value={'placa': 'XYZ 45K', 'tipo': 'moto'}),
            OpenApiExample('Creado', response_only=True, status_codes=['201'], value=EJEMPLO_VEHICULO),
            *EJEMPLOS_ERROR_400,
        ],
    ),
    retrieve=extend_schema(
        summary='Detalle de vehículo',
        responses={200: VehiculoSerializer, 404: NO_ENCONTRADO},
        examples=[OpenApiExample('Vehículo', response_only=True, value=EJEMPLO_VEHICULO)],
    ),
    partial_update=extend_schema(
        summary='Modificar vehículo',
        description='Cambia placa, tipo o estado. La combinación final de placa y tipo '
        'se valida de nuevo. No se puede cambiar la placa ni el tipo mientras el '
        'vehículo está adentro.',
        responses={200: VehiculoSerializer, 400: OpenApiResponse(description='Datos inválidos'),
                   404: NO_ENCONTRADO},
        examples=[
            OpenApiExample('Desactivar', request_only=True, value={'activo': False}),
            *EJEMPLOS_ERROR_400,
        ],
    ),
    destroy=extend_schema(
        summary='Eliminar vehículo',
        description='Si el vehículo nunca ha entrado se borra. Si tiene tickets en el '
        'historial se desactiva (`activo=false`) para conservar ese historial. Si está '
        'adentro responde 409.',
        responses={
            204: OpenApiResponse(description='Eliminado o desactivado'),
            404: NO_ENCONTRADO,
            409: OpenApiResponse(description='El vehículo está dentro del parqueadero'),
        },
    ),
)
@extend_schema(tags=['vehiculos'])
class VehiculoViewSet(viewsets.ModelViewSet):
    serializer_class = VehiculoSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def es_administrador(self):
        return EsAdministrador().has_permission(self.request, self)

    def get_queryset(self):
        vehiculos = Vehiculo.objects.order_by('-creado_en')
        if getattr(self, 'swagger_fake_view', False):
            # drf-spectacular genera el esquema sin usuario autenticado.
            return vehiculos.none()
        if self.es_administrador():
            return vehiculos
        # Un vehículo ajeno no aparece en el queryset: el detalle responde 404.
        return vehiculos.filter(usuario=self.request.user)

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)

    def destroy(self, request, *args, **kwargs):
        vehiculo = self.get_object()
        if vehiculo.tiene_ticket_abierto():
            return Response(
                {'detail': 'No se puede eliminar un vehículo que está dentro del parqueadero.'},
                status=status.HTTP_409_CONFLICT,
            )
        if vehiculo.tickets.exists():
            vehiculo.activo = False
            vehiculo.save(update_fields=['activo'])
        else:
            vehiculo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
