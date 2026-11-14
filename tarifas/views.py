from django.db import IntegrityError
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from comun.permisos import EsAdministrador

from .models import Tarifa
from .serializers import (
    ActualizarTarifasSerializer,
    TarifaHistorialSerializer,
    TarifaSerializer,
)
from .servicios import actualizar_tarifas, tarifas_vigentes

EJEMPLO_VIGENTES = [
    {'id': 1, 'tipo_vehiculo': 'carro', 'concepto': 'hasta_2h', 'valor': 7000,
     'vigente_desde': '2026-11-01T08:00:00-05:00'},
    {'id': 7, 'tipo_vehiculo': 'carro', 'concepto': 'mas_2h', 'valor': 13000,
     'vigente_desde': '2026-11-13T09:10:00-05:00'},
    {'id': 3, 'tipo_vehiculo': 'carro', 'concepto': 'mensualidad', 'valor': 75000,
     'vigente_desde': '2026-11-01T08:00:00-05:00'},
    {'id': 4, 'tipo_vehiculo': 'moto', 'concepto': 'hasta_2h', 'valor': 5000,
     'vigente_desde': '2026-11-01T08:00:00-05:00'},
    {'id': 5, 'tipo_vehiculo': 'moto', 'concepto': 'mas_2h', 'valor': 9000,
     'vigente_desde': '2026-11-01T08:00:00-05:00'},
    {'id': 6, 'tipo_vehiculo': 'moto', 'concepto': 'mensualidad', 'valor': 56000,
     'vigente_desde': '2026-11-01T08:00:00-05:00'},
]

EJEMPLO_PUT = {
    'carro': {'hasta_2h': 7000, 'mas_2h': 13000, 'mensualidad': 75000},
    'moto': {'hasta_2h': 5000, 'mas_2h': 9000, 'mensualidad': 56000},
}


@extend_schema(tags=['tarifas'])
class TarifasView(APIView):
    """GET: cualquier usuario autenticado. PUT: solo administrador."""

    def get_permissions(self):
        if self.request.method == 'PUT':
            return [EsAdministrador()]
        return [permissions.IsAuthenticated()]

    @extend_schema(
        summary='Tarifas vigentes',
        description='Las seis tarifas vigentes (`vigente_hasta` nulo). Disponible para '
        'cualquier usuario autenticado: la app del conductor las muestra.',
        responses={200: TarifaSerializer(many=True)},
        examples=[OpenApiExample('Vigentes', response_only=True, value=EJEMPLO_VIGENTES)],
    )
    def get(self, request):
        return Response(TarifaSerializer(tarifas_vigentes(), many=True).data)

    @extend_schema(
        summary='Actualizar tarifas',
        description='Recibe los seis valores (carro y moto; `hasta_2h`, `mas_2h` y '
        '`mensualidad`). Por cada valor que cambie se cierra la tarifa vigente '
        '(`vigente_hasta` = ahora) y se crea una fila nueva con `vigente_desde` = ahora '
        'y `creado_por` = el administrador. Los valores que no cambian no crean fila. '
        'Todo ocurre en una transacción. Responde las filas creadas y las vigentes.',
        request=ActualizarTarifasSerializer,
        responses={
            200: OpenApiResponse(description='Cambios aplicados'),
            400: OpenApiResponse(description='Falta un valor o alguno es 0 o negativo'),
            403: OpenApiResponse(description='El usuario no es administrador'),
            409: OpenApiResponse(description='Otro administrador cambió las tarifas a la vez'),
        },
        examples=[
            OpenApiExample('Subir carro más de 2 h', request_only=True, value=EJEMPLO_PUT),
            OpenApiExample(
                'Aplicado',
                response_only=True,
                status_codes=['200'],
                value={'creadas': [EJEMPLO_VIGENTES[1]], 'vigentes': EJEMPLO_VIGENTES},
            ),
            OpenApiExample(
                'Valor negativo',
                response_only=True,
                status_codes=['400'],
                value={'moto': {'hasta_2h': ['El valor debe ser mayor que 0.']}},
            ),
        ],
    )
    def put(self, request):
        serializer = ActualizarTarifasSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            creadas = actualizar_tarifas(serializer.validated_data, request.user)
        except IntegrityError:
            return Response(
                {'detail': 'Otro administrador modificó las tarifas al mismo tiempo. '
                           'Consulta los valores vigentes e inténtalo de nuevo.'},
                status=status.HTTP_409_CONFLICT,
            )
        return Response({
            'creadas': TarifaSerializer(creadas, many=True).data,
            'vigentes': TarifaSerializer(tarifas_vigentes(), many=True).data,
        })


@extend_schema(
    tags=['tarifas'],
    summary='Historial de tarifas',
    description='Todas las tarifas, vigentes y cerradas, de la más reciente a la más '
    'antigua (por `vigente_desde`), con el nombre de quién las creó. Solo administrador.',
    examples=[
        OpenApiExample(
            'Historial',
            response_only=True,
            value=[
                {'id': 7, 'tipo_vehiculo': 'carro', 'concepto': 'mas_2h', 'valor': 13000,
                 'vigente_desde': '2026-11-13T09:10:00-05:00', 'vigente_hasta': None,
                 'creado_por': '3f2c8a1e-5b7d-4c9a-9e1f-2a6b8c4d0e11',
                 'creado_por_nombre': 'Administrador'},
                {'id': 2, 'tipo_vehiculo': 'carro', 'concepto': 'mas_2h', 'valor': 12000,
                 'vigente_desde': '2026-11-01T08:00:00-05:00',
                 'vigente_hasta': '2026-11-13T09:10:00-05:00',
                 'creado_por': '3f2c8a1e-5b7d-4c9a-9e1f-2a6b8c4d0e11',
                 'creado_por_nombre': 'Administrador'},
            ],
        )
    ],
)
class HistorialTarifasView(ListAPIView):
    serializer_class = TarifaHistorialSerializer
    permission_classes = [EsAdministrador]
    queryset = Tarifa.objects.select_related('creado_por').order_by('-vigente_desde', '-id')
