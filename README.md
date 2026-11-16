# Parqueadero Universitario

Sistema y/o aplicativo para la gestión y control de acceso vehicular al parqueadero universitario, creado por una API REST/WebSockets en Django y una Progressive Web App (PWA) en React.

## Despliegue en Producción (H25)

* **Frontend (PWA):**https://parqueadero-universitario.vercel.app*(Vercel)*
* **Backend (API REST y WebSockets):**https://parqueadero-api-1pz7.onrender.com *(Render + ASGI Daphne)*
* **Documentación Interactiva (Swagger):**https://parqueadero-api-1pz7.onrender.com/api/docs/
* **Base de Datos:** PostgreSQL en Supabase

### Credenciales de Prueba (Seeders)

| Rol | Correo | Contraseña | Vehículo Asociado |
| **Administrador** | `admin@parqueadero.test` | `Admin2026!` | 
| **Guarda (Portería 1)** | `guarda1@parqueadero.test`| `Guarda2026!` | 
| **Guarda (Portería 2)** | `guarda2@parqueadero.test`| `Guarda2026!` | 
| **Conductor (Estudiante)** | `estudiante@parqueadero.test`| `Conductor2026!` | `ABC123` (Carro) |
| **Conductor (Docente)** | `docente@parqueadero.test` | `Conductor2026!` | `XYZ12A` (Moto) |
| **Conductor (Administrativo)** | `administrativo@parqueadero.test`| `Conductor2026!` | `DEF456` (Carro) |

> **Nota:** El servicio gratuito en Render entra en suspensión tras 15 minutos sin tráfico. Ante un arranque en frío, la primera solicitud tarda ~50 segundos mientras el servidor vuelve a activarse.