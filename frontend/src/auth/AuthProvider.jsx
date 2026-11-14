import { useCallback, useEffect, useMemo, useState } from 'react';

import api, { SESION_EXPIRADA, tokens } from '../api/client';
import { AuthContext } from './AuthContext';

const CLAVE_USUARIO = 'parqueadero.usuario';

function leerUsuarioGuardado() {
  try {
    const texto = localStorage.getItem(CLAVE_USUARIO);
    return texto ? JSON.parse(texto) : null;
  } catch {
    return null;
  }
}

function persistirUsuario(usuario) {
  try {
    if (usuario) localStorage.setItem(CLAVE_USUARIO, JSON.stringify(usuario));
    else localStorage.removeItem(CLAVE_USUARIO);
  } catch {
    // Sin almacenamiento: el usuario queda solo en memoria.
  }
}

/**
 * Guarda el usuario y su rol. El perfil se conserva en localStorage para abrir la app
 * al instante (y sin conexión), y se vuelve a validar contra /api/auth/yo al cargar.
 */
export default function AuthProvider({ children }) {
  const [usuario, setUsuario] = useState(() => (tokens.refresh ? leerUsuarioGuardado() : null));
  // Hay tokens pero no perfil guardado: hay que esperar a /yo antes de decidir la ruta.
  const [cargando, setCargando] = useState(() => Boolean(tokens.refresh) && !leerUsuarioGuardado());
  const [sesionExpirada, setSesionExpirada] = useState(false);

  const guardarUsuario = useCallback((nuevo) => {
    persistirUsuario(nuevo);
    setUsuario(nuevo);
  }, []);

  const cerrarSesion = useCallback(() => {
    tokens.borrar();
    guardarUsuario(null);
  }, [guardarUsuario]);

  // El cliente de API avisa cuando el refresh ya no sirve.
  useEffect(() => {
    const alExpirar = () => {
      guardarUsuario(null);
      setSesionExpirada(true);
    };
    window.addEventListener(SESION_EXPIRADA, alExpirar);
    return () => window.removeEventListener(SESION_EXPIRADA, alExpirar);
  }, [guardarUsuario]);

  // Al abrir la app con una sesión guardada, refresca el perfil (el rol pudo cambiar).
  useEffect(() => {
    if (!tokens.refresh) return undefined;
    let vigente = true;
    api
      .get('/api/auth/yo')
      .then(({ data }) => vigente && guardarUsuario(data))
      .catch((error) => {
        if (vigente && error.response?.status === 401) cerrarSesion();
      })
      .finally(() => vigente && setCargando(false));
    return () => {
      vigente = false;
    };
  }, [guardarUsuario, cerrarSesion]);

  const iniciarSesion = useCallback(
    async (email, password) => {
      const { data } = await api.post('/api/auth/login', { email, password });
      tokens.guardar(data);
      try {
        const { data: perfil } = await api.get('/api/auth/yo');
        guardarUsuario(perfil);
        setSesionExpirada(false);
        return perfil;
      } catch (error) {
        tokens.borrar();
        throw error;
      }
    },
    [guardarUsuario],
  );

  /** Crea la cuenta (siempre rol conductor). No inicia sesión: eso lo decide la pantalla. */
  const registrar = useCallback(async (datos) => {
    const { data } = await api.post('/api/auth/registro', datos);
    return data;
  }, []);

  const valor = useMemo(
    () => ({ usuario, cargando, sesionExpirada, iniciarSesion, registrar, cerrarSesion }),
    [usuario, cargando, sesionExpirada, iniciarSesion, registrar, cerrarSesion],
  );

  return <AuthContext value={valor}>{children}</AuthContext>;
}
