from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from comun.permisos import EsAdministrador

from . import servicios
from .autenticacion import CABECERA, EsDispositivo, LlaveDispositivo
from .serializers import (
    BahiaSerializer,
    CuposSerializer,
    LecturaLPRSerializer,
    MensajeSensorSerializer,
    ReporteSensoresSerializer,
    RespuestaLPRSerializer,
)

ERROR_LLAVE = OpenApiResponse(description=f'Falta la cabecera {CABECERA} o la llave es inválida')

EJEMPLO_CUPOS = {
    'tipo': 'cupos',
    'libres': {'carro': 5, 'moto': 3},
    'actualizado_en': '2026-11-13T09:10:00.512000+00:00',
}


class _VistaDispositivo(APIView):
    authentication_classes = [LlaveDispositivo]
    permission_classes = [EsDispositivo]


class SensorEstadoView(_VistaDispositivo):
    @extend_schema(
        tags=['iot'],
        summary='Mensaje de un sensor de bahía',
        description=(
            'Contrato fijo con los simuladores (CLAUDE.md). Con `ocupado`, actualiza la '
            'bahía, guarda el evento y el último pulso, y si la bahía cambió emite el nuevo '
            'conteo por `ws/cupos`. Con `latido: true` solo actualiza el último pulso.\n\n'
            'Una bahía `fuera_servicio` no cambia por el sensor (el evento sí se guarda).'
        ),
        request=MensajeSensorSerializer,
        responses={
            200: BahiaSerializer,
            400: OpenApiResponse(description='Mensaje inválido'),
            401: ERROR_LLAVE,
            404: OpenApiResponse(description='No hay sensor con ese device_uid'),
        },
        examples=[
            OpenApiExample(
                'Ocupación',
                request_only=True,
                value={
                    'device_uid': 'ESP32-C01',
                    'ocupado': True,
                    'distancia_cm': 42,
                    'ts': '2026-11-13T09:10:00Z',
                },
            ),
            OpenApiExample(
                'Latido',
                request_only=True,
                value={'device_uid': 'ESP32-C01', 'latido': True, 'ts': '2026-11-13T09:10:30Z'},
            ),
            OpenApiExample(
                'Bahía actualizada',
                response_only=True,
                status_codes=['200'],
                value={
                    'codigo': 'C-01',
                    'tipo_vehiculo': 'carro',
                    'estado': 'ocupada',
                    'actualizado_en': '2026-11-13T09:10:00.498000Z',
                    'sensor': {
                        'device_uid': 'ESP32-C01',
                        'ultimo_pulso': '2026-11-13T09:10:00.495000Z',
                    },
                },
            ),
        ],
    )
    def post(self, request):
        serializer = MensajeSensorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            bahia = servicios.procesar_mensaje_sensor(serializer.validated_data)
        except servicios.SensorNoRegistrado as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(BahiaSerializer(bahia).data)


class LecturaLPRView(_VistaDispositivo):
    @extend_schema(
        tags=['iot'],
        summary='Lectura de placa de la cámara LPR',
        description=(
            'Contrato fijo con los simuladores (CLAUDE.md). Si la placa es de un conductor '
            'activo con mensualidad activa para ese tipo de vehículo y no tiene otro vehículo '
            'adentro, abre el ticket con `metodo_ingreso=lpr` y responde `abrir: true`. Si '
            'no, `abrir: false` y el ingreso pasa al lector QR. La lectura se registra '
            'siempre.\n\n'
            'Motivos: `mensualidad_activa`, `lectura_invalida`, `confianza_baja` (menor que '
            'LPR_CONFIANZA_MINIMA), `placa_no_registrada`, `vehiculo_inactivo`, '
            '`usuario_inactivo`, `sin_mensualidad`, `vehiculo_adentro`.'
        ),
        request=LecturaLPRSerializer,
        responses={
            200: RespuestaLPRSerializer,
            400: OpenApiResponse(description='Mensaje inválido'),
            401: ERROR_LLAVE,
        },
        examples=[
            OpenApiExample(
                'Lectura',
                request_only=True,
                value={
                    'camara_id': 'CAM-ENTRADA',
                    'placa': 'ABC123',
                    'confianza': 0.94,
                    'foto': 'https://almacen.ejemplo/lpr/20261113-091000.jpg',
                },
            ),
            OpenApiExample(
                'Abre',
                response_only=True,
                status_codes=['200'],
                value={
                    'abrir': True,
                    'motivo': 'mensualidad_activa',
                    'ticket_id': '0c9e7f1a-2b3d-4e5f-8a9b-1c2d3e4f5a6b',
                },
            ),
            OpenApiExample(
                'No abre',
                response_only=True,
                status_codes=['200'],
                value={'abrir': False, 'motivo': 'sin_mensualidad', 'ticket_id': None},
            ),
        ],
    )
    def post(self, request):
        serializer = LecturaLPRSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(servicios.procesar_lectura_lpr(serializer.validated_data))


class ReporteSensoresView(APIView):
    permission_classes = [EsAdministrador]

    @extend_schema(
        tags=['iot'],
        summary='Reporte de sensores',
        description=(
            'Cada bahía con su sensor, estado y último pulso. El estado del sensor se '
            'calcula al consultar: sin pulso en más de 90 segundos (o sin ningún pulso) es '
            '`desconectado`; un sensor marcado `falla` por el administrador sigue en `falla`.'
        ),
        responses={
            200: ReporteSensoresSerializer,
            401: OpenApiResponse(description='Sin token'),
            403: OpenApiResponse(description='El usuario no es administrador'),
        },
        examples=[
            OpenApiExample(
                'Reporte',
                response_only=True,
                value={
                    'generado_en': '2026-11-13T09:12:00Z',
                    'desconectados': 1,
                    'bahias': [
                        {
                            'bahia': 'C-01',
                            'tipo_vehiculo': 'carro',
                            'estado_bahia': 'ocupada',
                            'device_uid': 'ESP32-C01',
                            'estado_sensor': 'ok',
                            'ultimo_pulso': '2026-11-13T09:11:50Z',
                            'segundos_sin_pulso': 10,
                        },
                        {
                            'bahia': 'C-02',
                            'tipo_vehiculo': 'carro',
                            'estado_bahia': 'libre',
                            'device_uid': 'ESP32-C02',
                            'estado_sensor': 'desconectado',
                            'ultimo_pulso': '2026-11-13T09:05:00Z',
                            'segundos_sin_pulso': 420,
                        },
                    ],
                },
            ),
        ],
    )
    def get(self, request):
        return Response(ReporteSensoresSerializer(servicios.reporte_sensores()).data)


class CuposView(APIView):
    # Público, igual que ws/cupos: lo usa también la pantalla de portería.
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['iot'],
        summary='Cupos libres por tipo',
        description=(
            'Conteo actual de bahías libres de carro y de moto, para la carga inicial. Los '
            'cambios llegan después por el WebSocket `ws/cupos`, con el mismo formato.'
        ),
        auth=[],
        responses={200: CuposSerializer},
        examples=[OpenApiExample('Cupos', response_only=True, value=EJEMPLO_CUPOS)],
    )
    def get(self, request):
        return Response(servicios.contar_cupos())
