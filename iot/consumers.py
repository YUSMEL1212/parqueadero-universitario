"""WebSocket de cupos libres (ws/cupos).

No exige autenticación: lo usan la app del conductor y la pantalla de portería, y solo
publica el conteo de bahías libres. Al conectarse recibe el estado actual; después,
un mensaje cada vez que una bahía cambia de estado. Lo que envíe el cliente se ignora.

Mensaje:
    {"tipo": "cupos", "libres": {"carro": 5, "moto": 3}, "actualizado_en": "..."}
"""

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .servicios import GRUPO_CUPOS, contar_cupos


class CuposConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        # Primero se suscribe y luego lee el conteo: así no se pierde un cambio que
        # ocurra entre la lectura y la suscripción.
        await self.channel_layer.group_add(GRUPO_CUPOS, self.channel_name)
        await self.accept()
        await self.send_json(await database_sync_to_async(contar_cupos)())

    async def disconnect(self, code):
        await self.channel_layer.group_discard(GRUPO_CUPOS, self.channel_name)

    async def receive_json(self, content, **kwargs):
        pass  # canal de solo lectura

    async def cupos_actualizados(self, evento):
        """Handler de group_send con type='cupos.actualizados' (servicios.emitir_cupos)."""
        await self.send_json(evento['cupos'])
