"""
Vistas HTTP de la app accesos (rutas bajo /api/accesos/).

- QRView: el conductor pide el token de su QR dinámico.
- EntradaView, SalidaView, ConfirmarSalidaView, InvitadoView: portería, solo guardas.
- HistorialView: recibos del conductor autenticado.

Las vistas solo validan la entrada, llaman a accesos/porteria.py o accesos/qr.py y
serializan la respuesta; las reglas de negocio no viven aquí. Cada vista queda
documentada en drf-spectacular (/api/docs) con ejemplos.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from comun.permisos import EsConductor, EsGuarda
from vehiculos.models import Vehiculo

from . import porteria
from .models import Ticket
from .qr import generar_token, segundos_restantes, validar_token
from .serializers import (
    ConfirmarSalidaSerializer,
    EntradaSerializer,
    InvitadoSerializer,
    LiquidacionSerializer,
    ReciboSerializer,
    SalidaSerializer,
    TicketSerializer,
)

RespuestaQR = inline_serializer(
    name='RespuestaQR',
    fields={
        'token': serializers.CharField(),
        'vence_en': serializers.DateTimeField(),
        'segundos_restantes': serializers.IntegerField(),
        'vehiculo': inline_serializer(
            name='VehiculoQR',
            fields={
                'id': serializers.UUIDField(),
                'placa': serializers.CharField(),
                'tipo': serializers.CharField(),
            },
        ),
    },
)


class QRView(APIView):
    """GET /api/accesos/qr: token del QR dinámico del conductor autenticado."""

    permission_classes = [EsConductor]

    @extend_schema(
        tags=['accesos'],
        summary='Token del QR dinámico',
        description=(
            'Genera el token cifrado (AES-256-GCM) que la PWA muestra como QR. Vence a los '
            '60 segundos; la PWA debe pedir uno nuevo cuando `segundos_restantes` llegue a 0.\n\n'
            'Si el conductor tiene un solo vehículo activo se usa ese. Si tiene varios, debe '
            'indicar cuál con `?vehiculo=<id>`. Un vehículo de otro conductor responde 404.'
        ),
        parameters=[
            OpenApiParameter(
                'vehiculo',
                OpenApiTypes.UUID,
                required=False,
                description='Id del vehículo. Obligatorio si el conductor tiene varios activos.',
            ),
        ],
        responses={
            200: RespuestaQR,
            400: OpenApiResponse(description='Varios vehículos activos sin indicar cuál, o id inválido'),
            403: OpenApiResponse(description='El usuario no es conductor'),
            404: OpenApiResponse(description='Sin vehículo activo, o el vehículo es de otro conductor'),
        },
        examples=[
            OpenApiExample(
                'QR generado',
                response_only=True,
                status_codes=['200'],
                value={
                    'token': 'q1Zr3x0b9yJ8kLmN...Xc2Q',
                    'vence_en': '2026-11-13T14:11:00Z',
                    'segundos_restantes': 60,
                    'vehiculo': {
                        'id': '7b1e4c2a-9d3f-4e8b-a6c5-1f2d3e4a5b6c',
                        'placa': 'ABC123',
                        'tipo': 'carro',
                    },
                },
            ),
        ],
    )
    def get(self, request):
        """Genera un token QR para un vehículo activo del conductor.

        Parámetros:
            request (Request): petición autenticada; acepta ``?vehiculo=<id>`` opcional.

        Devuelve:
            Response: 200 con token, vencimiento, segundos restantes y vehículo; 400 si
            hay varios vehículos activos sin indicar cuál o el id no es válido; 404 si no
            tiene un vehículo activo con ese id.
        """
        activos = Vehiculo.objects.filter(usuario=request.user, activo=True)
        vehiculo_id = request.query_params.get('vehiculo')

        if vehiculo_id:
            try:
                vehiculo = activos.filter(pk=vehiculo_id).first()
            except DjangoValidationError:
                return Response(
                    {'detail': 'El id de vehículo no es válido.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if vehiculo is None:
                # Mismo 404 si no existe, está inactivo o es de otro conductor.
                return Response(
                    {'detail': 'No tienes un vehículo activo con ese id.'},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            candidatos = list(activos[:2])
            if not candidatos:
                return Response(
                    {'detail': 'No tienes un vehículo activo registrado.'},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if len(candidatos) > 1:
                return Response(
                    {'detail': 'Tienes varios vehículos activos; indica cuál con ?vehiculo=<id>.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            vehiculo = candidatos[0]

        token = generar_token(request.user, vehiculo)
        vence_en = validar_token(token)['vence_en']
        return Response(
            {
                'token': token,
                'vence_en': vence_en,
                'segundos_restantes': segundos_restantes(vence_en),
                'vehiculo': {'id': vehiculo.pk, 'placa': vehiculo.placa, 'tipo': vehiculo.tipo},
            }
        )


# --- Portería (guarda) --------------------------------------------------------------

EJEMPLO_TICKET = {
    'id': '0c9e7f1a-2b3d-4e5f-8a9b-1c2d3e4f5a6b',
    'placa': 'ABC123',
    'tipo_vehiculo': 'carro',
    'conductor': 'Laura Gómez',
    'tipo_ingreso': 'registrado',
    'metodo_ingreso': 'qr',
    'hora_entrada': '2026-11-13T08:00:00-05:00',
    'codigo_salida': None,
}

EJEMPLO_RECIBO = {
    'id': '0c9e7f1a-2b3d-4e5f-8a9b-1c2d3e4f5a6b',
    'placa': 'ABC123',
    'tipo_vehiculo': 'carro',
    'tipo_ingreso': 'registrado',
    'hora_entrada': '2026-11-13T08:00:00-05:00',
    'hora_salida': '2026-11-13T09:30:00-05:00',
    'minutos': 90,
    'valor_cobrado': 7000,
    'tarifa': {'id': 1, 'concepto': 'hasta_2h', 'valor': 7000},
    'pago': '5d4c3b2a-1f0e-4d9c-8b7a-6f5e4d3c2b1a',
    'metodo_pago': 'efectivo',
}

ERROR_QR = OpenApiResponse(
    description='QR vencido, alterado o ilegible. `codigo`: qr_vencido, qr_alterado o qr_ilegible.'
)
ERROR_ROL = OpenApiResponse(description='El usuario no es guarda')
ERROR_TARIFA = OpenApiResponse(
    description='No hay tarifa vigente para el caso (`codigo`: sin_tarifa_vigente)'
)


class _VistaPorteria(APIView):
    """Convierte los errores de accesos/porteria.py en respuestas con `detail` y `codigo`."""

    permission_classes = [EsGuarda]

    def handle_exception(self, exc):
        """Responde los ErrorPorteria con su status; el resto lo maneja DRF.

        Parámetros:
            exc (Exception): excepción lanzada durante la vista.

        Devuelve:
            Response: ``{'detail', 'codigo', ...}`` con el status del error, o la
            respuesta estándar de DRF para cualquier otra excepción.
        """
        if isinstance(exc, porteria.ErrorPorteria):
            return Response(exc.como_respuesta(), status=exc.status)
        return super().handle_exception(exc)

    def _datos(self, serializer_class):
        """Valida el cuerpo de la petición con el serializer indicado.

        Parámetros:
            serializer_class (type): clase de serializer de entrada.

        Devuelve:
            dict: los datos validados.

        Lanza:
            ValidationError: de DRF si los datos no son válidos (responde 400).
        """
        serializer = serializer_class(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class EntradaView(_VistaPorteria):
    """POST /api/accesos/entrada: el guarda registra el ingreso de un conductor con su QR."""

    @extend_schema(
        tags=['accesos'],
        summary='Registrar entrada con QR',
        description=(
            'El guarda escanea el QR del conductor. Se valida el token (60 s de vigencia, '
            'AES-256-GCM), se verifica que el conductor no tenga otro vehículo adentro y se '
            'abre el ticket con `metodo_ingreso=qr`.'
        ),
        request=EntradaSerializer,
        responses={
            201: TicketSerializer,
            400: ERROR_QR,
            403: ERROR_ROL,
            404: OpenApiResponse(description='El vehículo del QR ya no existe'),
            409: OpenApiResponse(
                description='El conductor ya tiene un vehículo adentro (`vehiculo_adentro`), '
                'o el vehículo o la cuenta están desactivados'
            ),
        },
        examples=[
            OpenApiExample('QR leído', request_only=True, value={'token': 'q1Zr3x0b9yJ8kLmN...Xc2Q'}),
            OpenApiExample(
                'Ticket abierto', response_only=True, status_codes=['201'], value=EJEMPLO_TICKET
            ),
            OpenApiExample(
                'Segundo vehículo',
                response_only=True,
                status_codes=['409'],
                value={
                    'detail': 'El conductor ya tiene un vehículo adentro (ABC123). '
                    'Debe salir antes de ingresar otro.',
                    'codigo': 'vehiculo_adentro',
                    'placa_adentro': 'ABC123',
                },
            ),
        ],
    )
    def post(self, request):
        """Abre el ticket del conductor cuyo QR se leyó.

        Parámetros:
            request (Request): petición del guarda con ``{'token': ...}``.

        Devuelve:
            Response: 201 con el ticket abierto. Los errores de portería (400, 404, 409)
            los responde ``handle_exception``.
        """
        datos = self._datos(EntradaSerializer)
        ticket = porteria.registrar_entrada(datos['token'], guarda=request.user)
        return Response(TicketSerializer(ticket).data, status=status.HTTP_201_CREATED)


class SalidaView(_VistaPorteria):
    """POST /api/accesos/salida: liquida (sin cerrar) el ticket abierto que va a salir."""

    @extend_schema(
        tags=['accesos'],
        summary='Liquidar salida',
        description=(
            'Busca el ticket abierto y calcula el cobro si el vehículo saliera ahora. '
            '**No cierra el ticket**: el guarda muestra el valor, cobra y luego llama a '
            '`/api/accesos/salida/confirmar` con el `ticket_id`.\n\n'
            'El conductor registrado se identifica con `token` (su QR); el invitado, con el '
            '`codigo_salida` impreso en su ticket. Se envía uno de los dos.'
        ),
        request=SalidaSerializer,
        responses={
            200: LiquidacionSerializer,
            400: ERROR_QR,
            403: ERROR_ROL,
            404: OpenApiResponse(description='No hay ticket abierto (`sin_ticket_abierto`)'),
            503: ERROR_TARIFA,
        },
        examples=[
            OpenApiExample('Conductor', request_only=True, value={'token': 'q1Zr3x0b9yJ8kLmN...Xc2Q'}),
            OpenApiExample('Invitado', request_only=True, value={'codigo_salida': 'K7MP2QXA'}),
            OpenApiExample(
                'Fracción',
                response_only=True,
                status_codes=['200'],
                value={
                    'ticket_id': '0c9e7f1a-2b3d-4e5f-8a9b-1c2d3e4f5a6b',
                    'placa': 'ABC123',
                    'tipo_vehiculo': 'carro',
                    'tipo_ingreso': 'registrado',
                    'hora_entrada': '2026-11-13T08:00:00-05:00',
                    'hora_salida': '2026-11-13T09:30:00-05:00',
                    'minutos': 90,
                    'valor': 7000,
                    'motivo': 'hasta_2h',
                    'tarifa': {'id': 1, 'concepto': 'hasta_2h', 'valor': 7000},
                },
            ),
            OpenApiExample(
                'Mensualidad',
                response_only=True,
                status_codes=['200'],
                value={
                    'ticket_id': '0c9e7f1a-2b3d-4e5f-8a9b-1c2d3e4f5a6b',
                    'placa': 'ABC123',
                    'tipo_vehiculo': 'carro',
                    'tipo_ingreso': 'registrado',
                    'hora_entrada': '2026-11-13T08:00:00-05:00',
                    'hora_salida': '2026-11-13T17:00:00-05:00',
                    'minutos': 540,
                    'valor': 0,
                    'motivo': 'mensualidad_activa',
                    'tarifa': None,
                },
            ),
        ],
    )
    def post(self, request):
        """Busca el ticket por QR o por código de invitado y calcula el cobro actual.

        Parámetros:
            request (Request): petición del guarda con ``token`` o ``codigo_salida``.

        Devuelve:
            Response: 200 con la liquidación. Los errores de portería (400, 404, 503)
            los responde ``handle_exception``.
        """
        datos = self._datos(SalidaSerializer)
        if datos.get('token'):
            ticket = porteria.buscar_ticket_por_qr(datos['token'])
        else:
            ticket = porteria.buscar_ticket_por_codigo(datos['codigo_salida'])
        return Response(porteria.liquidar_salida(ticket))


class ConfirmarSalidaView(_VistaPorteria):
    """POST /api/accesos/salida/confirmar: cierra el ticket y registra el pago."""

    @extend_schema(
        tags=['accesos'],
        summary='Confirmar salida',
        description=(
            'Cierra el ticket: guarda hora de salida, minutos, valor cobrado y tarifa '
            'aplicada. Si hubo cobro, crea el pago (`fraccion`, aprobado) con el método '
            'indicado. El cobro se recalcula en este momento.'
        ),
        request=ConfirmarSalidaSerializer,
        responses={
            200: ReciboSerializer,
            400: OpenApiResponse(description='Datos inválidos'),
            403: ERROR_ROL,
            404: OpenApiResponse(description='El ticket no existe'),
            409: OpenApiResponse(description='El ticket ya estaba cerrado (`ticket_cerrado`)'),
            503: ERROR_TARIFA,
        },
        examples=[
            OpenApiExample(
                'Confirmar',
                request_only=True,
                value={
                    'ticket_id': '0c9e7f1a-2b3d-4e5f-8a9b-1c2d3e4f5a6b',
                    'metodo_pago': 'efectivo',
                },
            ),
            OpenApiExample('Recibo', response_only=True, status_codes=['200'], value=EJEMPLO_RECIBO),
        ],
    )
    def post(self, request):
        """Cierra el ticket indicado con el cobro recalculado en este momento.

        Parámetros:
            request (Request): petición del guarda con ``ticket_id`` y ``metodo_pago``.

        Devuelve:
            Response: 200 con el recibo. Los errores de portería (404, 409, 503) los
            responde ``handle_exception``.
        """
        datos = self._datos(ConfirmarSalidaSerializer)
        ticket = porteria.confirmar_salida(datos['ticket_id'], datos['metodo_pago'])
        return Response(ReciboSerializer(ticket).data)


class InvitadoView(_VistaPorteria):
    """POST /api/accesos/invitados: el guarda registra el ingreso de un vehículo sin cuenta."""

    @extend_schema(
        tags=['accesos'],
        summary='Registrar invitado',
        description=(
            'Registra el ingreso de un vehículo sin cuenta. Crea el vehículo sin usuario (o '
            'reutiliza el de una visita anterior) y abre un ticket `invitado` con un '
            '`codigo_salida` de 8 caracteres que el invitado presenta al salir. Los '
            'invitados siempre pagan tarifa completa.'
        ),
        request=InvitadoSerializer,
        responses={
            201: TicketSerializer,
            400: OpenApiResponse(description='Tipo o placa inválidos'),
            403: ERROR_ROL,
            409: OpenApiResponse(
                description='La placa es de un conductor registrado (`placa_registrada`) o '
                'ya está adentro (`vehiculo_adentro`)'
            ),
        },
        examples=[
            OpenApiExample('Invitado', request_only=True, value={'tipo': 'moto', 'placa': 'xyz-45k'}),
            OpenApiExample(
                'Ticket de invitado',
                response_only=True,
                status_codes=['201'],
                value={
                    **EJEMPLO_TICKET,
                    'placa': 'XYZ45K',
                    'tipo_vehiculo': 'moto',
                    'conductor': None,
                    'tipo_ingreso': 'invitado',
                    'metodo_ingreso': 'manual',
                    'codigo_salida': 'K7MP2QXA',
                },
            ),
        ],
    )
    def post(self, request):
        """Abre un ticket de invitado con su código de salida.

        Parámetros:
            request (Request): petición del guarda con ``tipo`` y ``placa``.

        Devuelve:
            Response: 201 con el ticket de invitado. Los errores de portería (409) los
            responde ``handle_exception``; una placa inválida responde 400.
        """
        datos = self._datos(InvitadoSerializer)
        ticket = porteria.registrar_invitado(datos['placa'], datos['tipo'], guarda=request.user)
        return Response(TicketSerializer(ticket).data, status=status.HTTP_201_CREATED)


class HistorialView(APIView):
    """GET /api/accesos/historial: recibos (tickets cerrados) del conductor autenticado."""

    permission_classes = [EsConductor]

    @extend_schema(
        tags=['accesos'],
        summary='Historial de recibos del conductor',
        description=(
            'Tickets cerrados del conductor autenticado, del más reciente al más antiguo. '
            'Los tickets abiertos (vehículo adentro) no aparecen.'
        ),
        responses={
            200: ReciboSerializer(many=True),
            403: OpenApiResponse(description='El usuario no es conductor'),
        },
        examples=[OpenApiExample('Historial', response_only=True, value=[EJEMPLO_RECIBO])],
    )
    def get(self, request):
        """Lista los tickets cerrados del conductor, del más reciente al más antiguo.

        Parámetros:
            request (Request): petición autenticada del conductor.

        Devuelve:
            Response: 200 con la lista de recibos; los tickets abiertos no aparecen.
        """
        recibos = (
            Ticket.objects.filter(usuario=request.user, hora_salida__isnull=False)
            .select_related('vehiculo', 'tarifa', 'pago')
            .order_by('-hora_salida')
        )
        return Response(ReciboSerializer(recibos, many=True).data)
