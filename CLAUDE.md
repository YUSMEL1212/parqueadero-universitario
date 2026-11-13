# Sistema de Parqueadero Universitario con IoT

Proyecto académico (Unimonserrate). Equipo: Yusmel (API + pantallas), Edicson (base de
datos, seeders, simuladores, despliegue), Evelyn (Product Owner, pruebas, documentación).
Entrega final: 23 de noviembre de 2026.

## Stack

- Backend: Python 3.12 + Django 5 + Django REST Framework
- Tiempo real: Django Channels (WebSocket)
- Base de datos: PostgreSQL en Supabase (conexión por `DATABASE_URL` en `.env`)
- Auth: SimpleJWT. Documentación: drf-spectacular en `/api/docs`
- Frontend: React + Vite como PWA (carpeta `frontend/`)

## Reglas que no se rompen

1. **La estructura de la base de datos solo cambia por `models.py` + migración.**
   Nunca crear ni alterar tablas desde el panel de Supabase ni con SQL suelto.
2. **Las tarifas nunca van en el código.** El motor de cobro las lee de la tabla
   `tarifas`, tomando la fila cuyo `vigente_hasta` es NULL. Un cambio de tarifa cierra
   la vigencia anterior y crea una fila nueva (historial).
3. **El contrato de mensajes IoT es fijo.** Los endpoints y los campos JSON están
   acordados con quien escribe los simuladores. Si hay que cambiar un campo, se avisa
   antes; no se cambia el endpoint por conveniencia.
4. **Los datos de prueba solo se cargan con `python manage.py seed`.**
5. **Nunca subir `.env`** ni llaves de Supabase o de la pasarela al repositorio.

## Reglas de negocio

- Placa de carro: `ABC123` (3 letras + 3 números). Placa de moto: `ABC12D`
  (3 letras + 2 números + 1 letra). Se guardan sin guion y en mayúsculas.
- Un usuario no puede tener dos vehículos dentro a la vez: restricción única sobre
  `tickets.usuario_id` con la condición `hora_salida IS NULL`.
- Motor de cobro, al salir:
  1. Si el usuario tiene mensualidad activa para ese tipo de vehículo
     (`vence_en > ahora`), el cobro es **0** y termina.
  2. Si no, minutos entre entrada y salida. **Hasta 120 minutos** → tarifa
     `hasta_2h`. **Desde 121 minutos** → tarifa `mas_2h`.
  3. Los invitados nunca tienen mensualidad: siempre pagan tarifa completa.
  4. El ticket guarda qué `tarifa_id` se aplicó.
- Valores iniciales (van en los seeders, no en el código):
  carro 7000 / 12000 / mensualidad 75000; moto 5000 / 9000 / mensualidad 56000.
- El token del QR se cifra con AES-256-GCM, contiene usuario, vehículo y vencimiento,
  y **vence a los 60 segundos**. El servidor rechaza tokens vencidos o alterados.
- Un sensor sin mensajes ni latidos durante 90 segundos pasa a `desconectado` y
  aparece en el reporte del administrador.
- Latencia objetivo de los sensores al dashboard: menos de 5 segundos.

## Contrato de mensajes IoT

`POST /api/iot/sensores/estado`
```json
{ "device_uid": "ESP32-C01", "ocupado": true, "distancia_cm": 42, "ts": "2026-11-13T09:10:00Z" }
```
Latido: el mismo endpoint con `{"device_uid": "...", "latido": true, "ts": "..."}`.
Respuesta: `200` con la bahía actualizada.

`POST /api/lpr/lecturas`
```json
{ "camara_id": "CAM-ENTRADA", "placa": "ABC123", "confianza": 0.94, "foto": "<base64 o url>" }
```
Respuesta: `{ "abrir": true, "motivo": "mensualidad_activa", "ticket_id": "..." }`.
Si no hay mensualidad o la lectura es mala: `abrir: false` y el ingreso pasa al lector QR.

Ambos endpoints se autentican con una llave de dispositivo en la cabecera `X-Device-Key`.

## Apps de Django

- `usuarios` — usuarios, roles, autenticación
- `vehiculos` — vehículos y validación de placas
- `tarifas` — tarifas con vigencia e historial
- `accesos` — tickets, entradas, salidas, invitados, QR, motor de cobro
- `pagos` — pagos y mensualidades (Wompi sandbox)
- `iot` — bahías, sensores, eventos, lecturas LPR, WebSocket de cupos

## Cómo trabajar en este repo

- Rama por tarea, se integra a `develop` con revisión de otro integrante.
- Cada endpoint nuevo queda documentado en drf-spectacular con ejemplo.
- Antes de dar una historia por terminada, se verifica contra su criterio de
  aceptación en el backlog (documento de Entregables de Arquitectura y Diseño).
