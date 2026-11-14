"""
Vistas HTTP de la app pagos (rutas bajo /api/ en config/urls.py).

- MensualidadesVigentesView: mensualidades activas del conductor (franja del inicio).
- PrecioMensualidadView: valor vigente de la mensualidad, leído de la tabla tarifas.
- PagoMensualidadView: inicia el pago (Pago pendiente + URL de la pasarela).
- EstadoPagoView: estado de un pago del conductor, para la pantalla de regreso.
- BancosPSEView: bancos para el selector de PSE.
- WebhookView: confirmación de la pasarela (Wompi o el simulador).
- simulador_pasarela: página del checkout simulado (solo sin llaves de Wompi).

Las reglas viven en pagos/servicios.py y la pasarela en pagos/wompi.py.
"""

import logging

from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from comun.permisos import EsConductor
from vehiculos.models import TipoVehiculo

from . import servicios, wompi
from .models import DURACION_MENSUALIDAD, Mensualidad, Pago
from .serializers import (
    BancoSerializer,
    IniciarPagoSerializer,
    MensualidadVigenteSerializer,
    PagoIniciadoSerializer,
    PagoMensualidadSerializer,
    PrecioMensualidadSerializer,
)

logger = logging.getLogger(__name__)

EJEMPLO_REFERENCIA = 'MEN-3F2C8A1E5B7D4C9A9E1F2A6B8C4D0E11'

EJEMPLO_PAGO = {
    'referencia': EJEMPLO_REFERENCIA,
    'estado': 'pendiente',
    'valor': 75000,
    'tipo_vehiculo': 'carro',
    'metodo': 'pse',
    'pagado_en': None,
    'mensualidad': None,
}

EJEMPLO_APROBADO = {
    **EJEMPLO_PAGO,
    'estado': 'aprobado',
    'pagado_en': '2026-11-14T10:05:12-05:00',
    'mensualidad': {
        'id': '5d2a9c1e-7f3b-4a8e-b6d4-2c1e0f9a8b7c',
        'tipo_vehiculo': 'carro',
        'inicia_en': '2026-11-14T10:05:12-05:00',
        'vence_en': '2026-12-14T10:05:12-05:00',
    },
}

ERROR_PASARELA = OpenApiResponse(description='La pasarela no respondió; reintentar')


def _error(mensaje, codigo, estado):
    return Response({'detail': mensaje, 'codigo': codigo}, status=estado)


def _sin_tarifa(exc):
    return _error(str(exc), 'sin_tarifa_vigente', status.HTTP_409_CONFLICT)


def _pasarela_caida(exc):
    return _error(str(exc), 'pasarela_no_disponible', status.HTTP_502_BAD_GATEWAY)


class MensualidadesVigentesView(generics.ListAPIView):
    """GET /api/mensualidades/vigentes: mensualidades activas del conductor autenticado."""

    serializer_class = MensualidadVigenteSerializer
    permission_classes = [EsConductor]
    pagination_class = None

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Mensualidad.objects.none()
        # Misma regla que el motor de cobro (accesos.services.tiene_mensualidad_activa):
        # activa = vence_en > ahora. Cada mensualidad cubre solo su tipo de vehículo.
        return Mensualidad.objects.filter(
            usuario=self.request.user, vence_en__gt=timezone.now()
        ).order_by('-vence_en')

    @extend_schema(
        tags=['pagos'],
        summary='Mensualidades vigentes',
        description=(
            'Mensualidades del conductor autenticado con `vence_en` en el futuro, de la que '
            'vence más tarde a la que vence antes. Lista vacía si no tiene ninguna. Una '
            'mensualidad de moto no cubre un carro: la PWA la compara con el tipo del '
            'vehículo elegido.'
        ),
        responses={
            200: MensualidadVigenteSerializer(many=True),
            403: OpenApiResponse(description='El usuario no es conductor'),
        },
        examples=[
            OpenApiExample(
                'Con mensualidad de carro',
                response_only=True,
                value=[EJEMPLO_APROBADO['mensualidad']],
            ),
            OpenApiExample('Sin mensualidad', response_only=True, value=[]),
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class PrecioMensualidadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['pagos'],
        summary='Precio de la mensualidad',
        description='Valor vigente de la mensualidad para el tipo de vehículo, leído de la '
        'tabla `tarifas` (fila con `vigente_hasta` nulo). Cambia en cuanto el administrador '
        'modifica la tarifa.',
        parameters=[
            OpenApiParameter('tipo', OpenApiTypes.STR, enum=TipoVehiculo.values, required=True)
        ],
        responses={
            200: PrecioMensualidadSerializer,
            400: OpenApiResponse(description='Falta `tipo` o no es carro ni moto'),
            409: OpenApiResponse(description='No hay tarifa de mensualidad vigente'),
        },
        examples=[
            OpenApiExample(
                'Carro',
                response_only=True,
                value={
                    'tipo_vehiculo': 'carro',
                    'valor': 75000,
                    'tarifa_id': 3,
                    'vigente_desde': '2026-11-01T08:00:00-05:00',
                    'duracion_dias': 30,
                },
            )
        ],
    )
    def get(self, request):
        tipo = request.query_params.get('tipo', '')
        if tipo not in TipoVehiculo.values:
            return Response(
                {'tipo': ['Indica el tipo de vehículo: carro o moto.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            tarifa = servicios.tarifa_mensualidad(tipo)
        except servicios.SinTarifaVigente as exc:
            return _sin_tarifa(exc)
        return Response(
            PrecioMensualidadSerializer(
                {
                    'tipo_vehiculo': tipo,
                    'valor': tarifa.valor,
                    'tarifa_id': tarifa.pk,
                    'vigente_desde': tarifa.vigente_desde,
                    'duracion_dias': DURACION_MENSUALIDAD.days,
                }
            ).data
        )


class PagoMensualidadView(APIView):
    permission_classes = [EsConductor]

    @extend_schema(
        tags=['pagos'],
        summary='Iniciar el pago de una mensualidad',
        description=(
            'Crea un pago `pendiente` por el valor vigente de la mensualidad, con una '
            'referencia única, y devuelve `url_pago` para redirigir al conductor.\n\n'
            '- `modo: wompi` → `url_pago` es el Web Checkout de Wompi.\n'
            '- `modo: simulacion` (sin llaves de Wompi en el .env) → `url_pago` es una '
            'página interna que aprueba o rechaza el pago y dispara el mismo webhook.\n\n'
            'Al terminar, la pasarela devuelve al conductor a `url_retorno?referencia=…` '
            '(Wompi agrega `&id=` con su transacción). La mensualidad se crea solo cuando '
            'llega la confirmación aprobada.'
        ),
        request=IniciarPagoSerializer,
        responses={
            201: PagoIniciadoSerializer,
            400: OpenApiResponse(description='Datos inválidos (p. ej. PSE sin banco)'),
            403: OpenApiResponse(description='El usuario no es conductor'),
            409: OpenApiResponse(description='No hay tarifa de mensualidad vigente'),
            503: OpenApiResponse(description='Wompi mal configurado en el servidor'),
        },
        examples=[
            OpenApiExample(
                'PSE',
                request_only=True,
                value={
                    'tipo_vehiculo': 'carro',
                    'metodo': 'pse',
                    'banco': '1007',
                    'correo': 'laura.gomez@unimonserrate.edu.co',
                    'url_retorno': 'http://localhost:5173/conductor/pagos',
                },
            ),
            OpenApiExample(
                'Simulación',
                response_only=True,
                status_codes=['201'],
                value={
                    **EJEMPLO_PAGO,
                    'modo': 'simulacion',
                    'url_pago': f'http://127.0.0.1:8000/api/pagos/simulacion/{EJEMPLO_REFERENCIA}'
                    '?banco=1007&correo=laura.gomez%40unimonserrate.edu.co&volver=…',
                },
            ),
        ],
    )
    def post(self, request):
        datos = IniciarPagoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        d = datos.validated_data
        try:
            pago, url = servicios.iniciar_pago_mensualidad(
                usuario=request.user,
                tipo_vehiculo=d['tipo_vehiculo'],
                metodo=d['metodo'],
                construir_url=request.build_absolute_uri,
                correo=d.get('correo') or request.user.email,
                url_retorno=d.get('url_retorno', ''),
                banco=d.get('banco', '') if d['metodo'] == Pago.Metodo.PSE else '',
            )
        except servicios.SinTarifaVigente as exc:
            return _sin_tarifa(exc)
        except wompi.PasarelaMalConfigurada as exc:
            logger.error('Wompi mal configurado: %s', exc)
            return _error(
                'El pago en línea no está disponible en este momento.',
                'pasarela_mal_configurada',
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        pago.modo = wompi.modo()
        pago.url_pago = url
        return Response(PagoIniciadoSerializer(pago).data, status=status.HTTP_201_CREATED)


class EstadoPagoView(APIView):
    permission_classes = [EsConductor]

    @extend_schema(
        tags=['pagos'],
        summary='Estado de un pago de mensualidad',
        description='Estado de un pago del conductor autenticado y, si se aprobó, la '
        'mensualidad creada. La PWA lo consulta al volver de la pasarela hasta que deje de '
        'estar `pendiente`. Con `?transaccion=` (el `id` que agrega Wompi al volver) y el '
        'pago aún pendiente, el servidor consulta la transacción en Wompi: así el flujo '
        'termina aunque el webhook no llegue (p. ej. con el backend en localhost).',
        parameters=[OpenApiParameter('transaccion', OpenApiTypes.STR, required=False)],
        responses={
            200: PagoMensualidadSerializer,
            404: OpenApiResponse(description='No existe o es de otro usuario'),
            502: ERROR_PASARELA,
        },
        examples=[OpenApiExample('Aprobado', response_only=True, value=EJEMPLO_APROBADO)],
    )
    def get(self, request, referencia):
        pago = get_object_or_404(
            Pago,
            referencia_pasarela=referencia,
            usuario=request.user,
            concepto=Pago.Concepto.MENSUALIDAD,
        )
        try:
            pago = servicios.sincronizar_con_wompi(pago, request.query_params.get('transaccion'))
        except wompi.PasarelaNoDisponible:
            pass  # Se responde el estado guardado; la PWA vuelve a consultar.
        except servicios.MontoNoCoincide:
            pass  # Queda pendiente y registrado en el log para revisión.
        return Response(PagoMensualidadSerializer(pago).data)


class BancosPSEView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['pagos'],
        summary='Bancos para PSE',
        description='Lista de bancos para el selector de PSE. En modo Wompi viene de su API; '
        'en modo simulación es una lista fija de demostración.',
        responses={200: BancoSerializer(many=True), 502: ERROR_PASARELA},
        examples=[
            OpenApiExample(
                'Bancos',
                response_only=True,
                value=[{'codigo': '1007', 'nombre': 'Bancolombia'}],
            )
        ],
    )
    def get(self, request):
        try:
            bancos = wompi.bancos_pse()
        except wompi.PasarelaNoDisponible as exc:
            return _pasarela_caida(exc)
        return Response(BancoSerializer(bancos, many=True).data)


RespuestaWebhook = inline_serializer(
    name='RespuestaWebhook',
    fields={
        'procesado': serializers.BooleanField(),
        'referencia': serializers.CharField(allow_null=True),
        'estado': serializers.CharField(allow_null=True),
    },
)


class WebhookView(APIView):
    # Lo llama la pasarela, sin usuario: la autenticidad se verifica en servicios.
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['pagos'],
        summary='Webhook de la pasarela',
        description=(
            'Recibe el evento `transaction.updated` de Wompi. En modo Wompi no se confía en '
            'el cuerpo: se consulta la transacción en la API de Wompi con la llave privada. '
            'En modo simulación se verifica la firma del evento.\n\n'
            '`APPROVED` → el pago queda `aprobado` y se crea la mensualidad de 30 días desde '
            'ese momento. `DECLINED`, `VOIDED` o `ERROR` → `rechazado`, sin mensualidad.\n\n'
            '**Idempotente:** un pago ya aprobado o rechazado no cambia, así que una '
            'confirmación repetida no duplica la mensualidad. Una referencia desconocida '
            'responde 200 con `procesado: false` para que Wompi no reintente.'
        ),
        auth=[],
        request=OpenApiTypes.OBJECT,
        responses={
            200: RespuestaWebhook,
            400: OpenApiResponse(description='Monto o moneda distintos a los del pago'),
            401: OpenApiResponse(description='Firma inválida (modo simulación)'),
            502: ERROR_PASARELA,
        },
        examples=[
            OpenApiExample(
                'Evento de Wompi',
                request_only=True,
                value={
                    'event': 'transaction.updated',
                    'data': {
                        'transaction': {
                            'id': '1234-1610641025-49201',
                            'reference': EJEMPLO_REFERENCIA,
                            'amount_in_cents': 7500000,
                            'currency': 'COP',
                            'status': 'APPROVED',
                        }
                    },
                    'environment': 'test',
                    'signature': {
                        'properties': wompi.PROPIEDADES_FIRMA,
                        'checksum': '3476DDA50F64CD7CBD160689640506FEBEA93239BC524FC0469B2C68A3CC8BD0',
                    },
                    'timestamp': 1763132712,
                },
            ),
            OpenApiExample(
                'Procesado',
                response_only=True,
                status_codes=['200'],
                value={'procesado': True, 'referencia': EJEMPLO_REFERENCIA, 'estado': 'aprobado'},
            ),
        ],
    )
    def post(self, request):
        try:
            pago, cambio = servicios.recibir_evento(request.data)
        except wompi.FirmaInvalida as exc:
            return _error(str(exc), 'firma_invalida', status.HTTP_401_UNAUTHORIZED)
        except wompi.PasarelaNoDisponible as exc:
            return _pasarela_caida(exc)
        except servicios.MontoNoCoincide:
            return _error(
                'El monto no coincide con el del pago.', 'monto_no_coincide',
                status.HTTP_400_BAD_REQUEST,
            )
        except servicios.ReferenciaDesconocida as exc:
            logger.warning('Webhook con referencia desconocida %s', exc)
            return Response({'procesado': False, 'referencia': str(exc), 'estado': None})
        return Response(
            {
                'procesado': cambio,
                'referencia': pago.referencia_pasarela if pago else None,
                'estado': pago.estado if pago else None,
            }
        )


# --- Checkout simulado --------------------------------------------------------------


@csrf_exempt  # La referencia (aleatoria) es la credencial, como en un checkout real.
@require_http_methods(['GET', 'POST'])
def simulador_pasarela(request, referencia):
    """Página de la pasarela simulada. Solo existe sin llaves de Wompi.

    GET muestra el pago con los botones Aprobar y Rechazar. POST arma un evento con el
    formato de Wompi y lo procesa igual que el webhook; luego devuelve al conductor a la
    PWA (`volver`) o, si no hay a dónde volver, muestra el resultado.
    """
    if not wompi.en_simulacion():
        raise Http404
    pago = get_object_or_404(
        Pago.objects.select_related('usuario'),
        referencia_pasarela=referencia,
        concepto=Pago.Concepto.MENSUALIDAD,
    )
    fuente = request.POST if request.method == 'POST' else request.GET
    volver = fuente.get('volver', '')
    if not servicios.url_retorno_valida(volver):
        volver = ''
    correo = fuente.get('correo', '')
    banco = next(
        (b['nombre'] for b in wompi.BANCOS_SIMULACION if b['codigo'] == fuente.get('banco')),
        '',
    )

    if request.method == 'POST' and pago.estado == Pago.Estado.PENDIENTE:
        aprobado = request.POST.get('accion') == 'aprobar'
        evento = wompi.evento_simulado(
            pago.referencia_pasarela, pago.valor * 100, aprobado, correo
        )
        # El mismo procesamiento que POST /api/pagos/webhook, firma incluida.
        pago, _ = servicios.recibir_evento(evento)
        if volver:
            return HttpResponseRedirect(volver, status=303)

    return render(
        request,
        'pagos/simulador.html',
        {
            'pago': pago,
            'valor': f'{pago.valor:,}'.replace(',', '.'),
            'banco': banco,
            'correo': correo,
            'volver': volver,
            'codigo_banco': fuente.get('banco', ''),
            'pendiente': pago.estado == Pago.Estado.PENDIENTE,
        },
    )
