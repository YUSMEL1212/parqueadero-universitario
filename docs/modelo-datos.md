# Modelo de datos

Diccionario de las 11 tablas del DER. Es la referencia para `models.py` y las migraciones.
Toda la estructura se crea con migraciones de Django; nunca con SQL suelto ni desde el
panel de Supabase.

## Apps y modelos

| App | Modelos |
|---|---|
| `usuarios` | Rol, Usuario |
| `vehiculos` | Vehiculo |
| `tarifas` | Tarifa |
| `pagos` | Pago, Mensualidad |
| `accesos` | Ticket |
| `iot` | Bahia, Sensor, EventoSensor, LecturaLPR |

---

## roles

| Campo | Tipo | Llave o restricción |
|---|---|---|
| id | SERIAL | PK |
| nombre | VARCHAR(30) | UNIQUE, NOT NULL. Valores: administrador, guarda, conductor |

## usuarios

Extiende `AbstractBaseUser` + `PermissionsMixin`, con el correo como campo de login.

| Campo | Tipo | Llave o restricción |
|---|---|---|
| id | UUID | PK |
| rol_id | INTEGER | FK → roles.id, NOT NULL |
| nombre | VARCHAR(120) | NOT NULL |
| email | VARCHAR(160) | UNIQUE, NOT NULL. Es el USERNAME_FIELD |
| password | TEXT | NOT NULL (hash de Django) |
| tipo_conductor | VARCHAR(20) | estudiante, docente o administrativo; NULL para guarda y administrador |
| telefono | VARCHAR(20) | opcional |
| activo | BOOLEAN | DEFAULT true |
| creado_en | TIMESTAMPTZ | auto_now_add |

## vehiculos

| Campo | Tipo | Llave o restricción |
|---|---|---|
| id | UUID | PK |
| usuario_id | UUID | FK → usuarios.id, NULL si es de un invitado |
| placa | VARCHAR(6) | UNIQUE, NOT NULL. Sin guion y en mayúsculas |
| tipo | VARCHAR(5) | CHECK: carro o moto |
| activo | BOOLEAN | DEFAULT true |
| creado_en | TIMESTAMPTZ | auto_now_add |

Validación de placa según el tipo: carro `^[A-Z]{3}[0-9]{3}$`, moto `^[A-Z]{3}[0-9]{2}[A-Z]$`.

## tarifas

| Campo | Tipo | Llave o restricción |
|---|---|---|
| id | SERIAL | PK |
| tipo_vehiculo | VARCHAR(5) | CHECK: carro o moto |
| concepto | VARCHAR(20) | CHECK: hasta_2h, mas_2h o mensualidad |
| valor | INTEGER | Pesos colombianos, NOT NULL, mayor que 0 |
| vigente_desde | TIMESTAMPTZ | NOT NULL |
| vigente_hasta | TIMESTAMPTZ | NULL = tarifa vigente |
| creado_por | UUID | FK → usuarios.id |

## pagos

| Campo | Tipo | Llave o restricción |
|---|---|---|
| id | UUID | PK |
| usuario_id | UUID | FK → usuarios.id, NULL si paga un invitado |
| concepto | VARCHAR(15) | CHECK: mensualidad o fraccion |
| valor | INTEGER | Pesos colombianos |
| metodo | VARCHAR(10) | CHECK: pse, tarjeta o efectivo |
| referencia_pasarela | VARCHAR(60) | UNIQUE. Referencia que se envía a la pasarela y con la que vuelve su confirmación |
| transaccion_pasarela | VARCHAR(60) | Id de la transacción en Wompi, al confirmarse |
| tipo_vehiculo | VARCHAR(5) | CHECK: carro o moto. Solo mensualidades: el tipo que cubrirá al aprobarse |
| estado | VARCHAR(10) | CHECK: pendiente, aprobado o rechazado |
| pagado_en | TIMESTAMPTZ | |

## mensualidades

| Campo | Tipo | Llave o restricción |
|---|---|---|
| id | UUID | PK |
| usuario_id | UUID | FK → usuarios.id, NOT NULL |
| pago_id | UUID | FK → pagos.id, UNIQUE (OneToOne) |
| tipo_vehiculo | VARCHAR(5) | CHECK: carro o moto |
| inicia_en | TIMESTAMPTZ | NOT NULL |
| vence_en | TIMESTAMPTZ | inicia_en + 30 días |

## tickets

| Campo | Tipo | Llave o restricción |
|---|---|---|
| id | UUID | PK |
| vehiculo_id | UUID | FK → vehiculos.id, NOT NULL |
| usuario_id | UUID | FK → usuarios.id, NULL si es invitado |
| guarda_id | UUID | FK → usuarios.id, NULL si entró por LPR |
| tipo_ingreso | VARCHAR(10) | CHECK: registrado o invitado |
| metodo_ingreso | VARCHAR(6) | CHECK: lpr, qr o manual |
| hora_entrada | TIMESTAMPTZ | NOT NULL |
| hora_salida | TIMESTAMPTZ | NULL mientras el vehículo está adentro |
| minutos | INTEGER | Tiempo total de estadía |
| valor_cobrado | INTEGER | 0 si tiene mensualidad activa |
| tarifa_id | INTEGER | FK → tarifas.id (tarifa aplicada) |
| pago_id | UUID | FK → pagos.id |
| foto_ingreso_url | TEXT | Foto tomada por la cámara LPR |
| codigo_salida | VARCHAR(12) | Código del ticket de invitado |

## lecturas_lpr

| Campo | Tipo | Llave o restricción |
|---|---|---|
| id | BIGSERIAL | PK |
| ticket_id | UUID | FK → tickets.id, NULL si no abrió |
| placa_leida | VARCHAR(10) | |
| confianza | NUMERIC(4,2) | Nivel de confianza de la lectura |
| foto_url | TEXT | |
| resultado | VARCHAR(12) | CHECK: abierta, rechazada o no_leida |
| leido_en | TIMESTAMPTZ | auto_now_add |

## bahias

| Campo | Tipo | Llave o restricción |
|---|---|---|
| id | SERIAL | PK |
| codigo | VARCHAR(10) | UNIQUE (ej. C-01, M-01) |
| tipo_vehiculo | VARCHAR(5) | CHECK: carro o moto |
| estado | VARCHAR(15) | CHECK: libre, ocupada o fuera_servicio |
| actualizado_en | TIMESTAMPTZ | auto_now |

## sensores

| Campo | Tipo | Llave o restricción |
|---|---|---|
| id | SERIAL | PK |
| bahia_id | INTEGER | FK → bahias.id, UNIQUE (OneToOne) |
| device_uid | VARCHAR(40) | UNIQUE |
| estado | VARCHAR(15) | CHECK: ok, desconectado o falla |
| ultimo_pulso | TIMESTAMPTZ | Último mensaje o latido recibido |

## eventos_sensor

| Campo | Tipo | Llave o restricción |
|---|---|---|
| id | BIGSERIAL | PK |
| sensor_id | INTEGER | FK → sensores.id, NOT NULL |
| ocupado | BOOLEAN | NOT NULL |
| distancia_cm | INTEGER | Distancia medida |
| recibido_en | TIMESTAMPTZ | auto_now_add, indexado |

---

## Restricciones de integridad

Van en el `Meta` de cada modelo, como `constraints`:

1. **Un vehículo adentro por usuario**
   `UniqueConstraint(fields=['usuario_id'], condition=Q(hora_salida__isnull=True))`
   en `Ticket`.
2. **Una sola tarifa vigente por tipo y concepto**
   `UniqueConstraint(fields=['tipo_vehiculo','concepto'], condition=Q(vigente_hasta__isnull=True))`
   en `Tarifa`.
3. **Placa según el tipo de vehículo**: validador con las dos expresiones regulares,
   más un `CheckConstraint` en la base.
4. **Valor de tarifa mayor que 0**: `CheckConstraint(check=Q(valor__gt=0))`.

## Datos iniciales (comando `seed`)

- 1 administrador por defecto, 2 guardas, 3 conductores con vehículos de prueba.
- 12 bahías: 8 de carro (C-01 a C-08) y 4 de moto (M-01 a M-04), cada una con su sensor.
- 6 tarifas vigentes: carro 7000 / 12000 / 75000; moto 5000 / 9000 / 56000.
