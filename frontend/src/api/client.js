/**
 * Cliente HTTP de la API.
 *
 * - URL base desde VITE_API_URL (frontend/.env).
 * - Agrega `Authorization: Bearer <access>` a cada petición.
 * - Si el backend responde 401, pide un access nuevo con el refresh y repite la
 *   petición una sola vez. Varias peticiones que fallen a la vez comparten el mismo
 *   refresco. Si el refresco falla, borra la sesión y emite SESION_EXPIRADA.
 */
import axios from 'axios';

const BASE_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');

const CLAVE_ACCESS = 'parqueadero.access';
const CLAVE_REFRESH = 'parqueadero.refresh';

export const SESION_EXPIRADA = 'parqueadero:sesion-expirada';

// Rutas de autenticación: un 401 aquí significa credenciales malas, no token vencido.
const RUTAS_SIN_REFRESCO = ['/api/auth/login', '/api/auth/registro', '/api/auth/refresh'];

function leer(clave) {
  try {
    return localStorage.getItem(clave);
  } catch {
    return null;
  }
}

function escribir(clave, valor) {
  try {
    if (valor) localStorage.setItem(clave, valor);
    else localStorage.removeItem(clave);
  } catch {
    // Almacenamiento bloqueado (modo privado): la sesión dura lo que dure la pestaña.
  }
}

export const tokens = {
  get access() {
    return leer(CLAVE_ACCESS);
  },
  get refresh() {
    return leer(CLAVE_REFRESH);
  },
  guardar({ access, refresh }) {
    if (access) escribir(CLAVE_ACCESS, access);
    if (refresh) escribir(CLAVE_REFRESH, refresh);
  },
  borrar() {
    escribir(CLAVE_ACCESS, null);
    escribir(CLAVE_REFRESH, null);
  },
};

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000,
});

api.interceptors.request.use((config) => {
  const access = tokens.access;
  if (access && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${access}`;
  }
  return config;
});

let refrescoEnCurso = null;

function refrescarAccess() {
  if (!refrescoEnCurso) {
    const refresh = tokens.refresh;
    refrescoEnCurso = (
      refresh
        ? // axios "pelado": este llamado no debe pasar por los interceptores de `api`.
          axios.post(`${BASE_URL}/api/auth/refresh`, { refresh }, { timeout: 15000 })
        : Promise.reject(new Error('Sin token de refresco'))
    )
      .then(({ data }) => {
        // Si el backend rota los refresh (ROTATE_REFRESH_TOKENS), también llega uno nuevo.
        tokens.guardar(data);
        return data.access;
      })
      .finally(() => {
        refrescoEnCurso = null;
      });
  }
  return refrescoEnCurso;
}

api.interceptors.response.use(
  (respuesta) => respuesta,
  async (error) => {
    const original = error.config;
    const ruta = original?.url ?? '';
    const esRutaAuth = RUTAS_SIN_REFRESCO.some((r) => ruta.endsWith(r));

    if (error.response?.status !== 401 || !original || original._reintento || esRutaAuth) {
      throw error;
    }

    original._reintento = true;
    let access;
    try {
      access = await refrescarAccess();
    } catch (errorRefresco) {
      // Solo se cierra la sesión si el servidor rechazó el refresh; un fallo de red
      // no debe sacar al usuario.
      if (errorRefresco.response || !tokens.refresh) {
        tokens.borrar();
        window.dispatchEvent(new Event(SESION_EXPIRADA));
        throw error;
      }
      throw errorRefresco;
    }
    original.headers.Authorization = `Bearer ${access}`;
    return api(original);
  },
);

export default api;
