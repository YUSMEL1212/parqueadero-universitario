# Parqueadero Universitario

Sistema integral para la gestión y control de acceso vehicular universitario, compuesto por una API REST/WebSockets en Django y una Progressive Web App (PWA) en React[cite: 5, 17].

## Despliegue en Producción (H25)

* **Frontend (PWA):** [https://parqueadero-universitario.vercel.app](https://parqueadero-universitario.vercel.app) *(Vercel)*[cite: 1, 14]
* **Backend (API REST y WebSockets):** [https://parqueadero-api-1pz7.onrender.com](https://parqueadero-api-1pz7.onrender.com) *(Render + ASGI Daphne)*[cite: 5]
* **Documentación Interactiva (Swagger):** [https://parqueadero-api-1pz7.onrender.com/api/docs/](https://parqueadero-api-1pz7.onrender.com/api/docs/)[cite: 5]
* **Base de Datos:** PostgreSQL en Supabase

### Credenciales de Prueba (Seeders)

| Rol | Correo | Contraseña | Vehículo Asociado |
| :--- | :--- | :--- | :--- |
| **Administrador** | `admin@parqueadero.test`[cite: 5] | `Admin2026!` | — |
| **Guarda (Portería 1)** | `guarda1@parqueadero.test`[cite: 5] | `Guarda2026!` | — |
| **Guarda (Portería 2)** | `guarda2@parqueadero.test`[cite: 5] | `Guarda2026!` | — |
| **Conductor (Estudiante)** | `estudiante@parqueadero.test`[cite: 5] | `Conductor2026!` | `ABC123` (Carro)[cite: 5] |
| **Conductor (Docente)** | `docente@parqueadero.test`[cite: 5] | `Conductor2026!` | `XYZ12A` (Moto)[cite: 5] |
| **Conductor (Administrativo)** | `administrativo@parqueadero.test`[cite: 5] | `Conductor2026!` | `DEF456` (Carro)[cite: 5] |

> **Nota:** El servicio gratuito en Render entra en suspensión tras 15 minutos sin tráfico[cite: 3]. Ante un arranque en frío, la primera solicitud tarda ~50 segundos mientras el servidor vuelve a activarse.