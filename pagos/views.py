"""
Vistas HTTP de la app pagos (rutas bajo /api/ en config/urls.py).

- MensualidadesVigentesView: el conductor consulta sus mensualidades activas, para la
  franja de estado de su pantalla principal.

El pago con la pasarela (Wompi sandbox) todavía no está implementado.
"""

from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import generics, serializers

from comun.permisos import EsConductor

from .models import Mensualidad


class MensualidadVigenteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Mensualidad
        fields = ['id', 'tipo_vehiculo', 'inicia_en', 'vence_en']
        read_only_fields = fields


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
                value=[
                    {
                        'id': '5d2a9c1e-7f3b-4a8e-b6d4-2c1e0f9a8b7c',
                        'tipo_vehiculo': 'carro',
                        'inicia_en': '2026-11-01T08:00:00-05:00',
                        'vence_en': '2026-12-01T08:00:00-05:00',
                    }
                ],
            ),
            OpenApiExample('Sin mensualidad', response_only=True, value=[]),
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
