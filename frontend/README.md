# Frontend — Parqueadero Universitario (PWA)

React + Vite, instalable como PWA. Habla con el backend Django en `VITE_API_URL`.

## Puesta en marcha

```bash
cp .env.example .env      # ajusta VITE_API_URL si el backend no está en 127.0.0.1:8000
npm install
npm run dev               # http://localhost:5173
```

El backend debe permitir el origen del frontend: en el `.env` de la raíz,
`CORS_ALLOWED_ORIGINS=http://localhost:5173`.

## Scripts

- `npm run dev` — servidor de desarrollo (sin service worker).
- `npm run build` — build de producción en `dist/`.
- `npm run preview` — sirve `dist/` en http://localhost:4173. Así se prueba la instalación
  de la PWA y el service worker.
- `npm run lint` — oxlint.

## Estructura

```
public/
  manifest.webmanifest   nombre, colores e íconos de la PWA
  sw.js                  service worker (app shell; la API nunca se cachea)
  icons/                 íconos PNG 192/512, maskable y apple-touch
src/
  api/client.js          axios: URL base, Bearer JWT y refresco automático ante 401
  api/errores.js         errores de DRF → mensajes para el usuario
  auth/                  contexto de sesión, roles y rutas protegidas por rol
  components/            piezas comunes (Campo, Aviso, ZonaLayout…)
  pages/                 login, registro y una carpeta por zona
```

## Rutas

| Ruta         | Acceso                      |
|--------------|-----------------------------|
| `/login`     | público                     |
| `/registro`  | público (crea un conductor) |
| `/conductor` | rol `conductor`             |
| `/conductor/vehiculos` | rol `conductor`   |
| `/conductor/historial` | rol `conductor`   |
| `/porteria`  | rol `guarda`                |
| `/admin`     | rol `administrador`         |

Con sesión iniciada, `/`, `/login` y `/registro` llevan a la zona del rol. Si un usuario
entra a una zona que no es la suya, vuelve a la de su rol.
