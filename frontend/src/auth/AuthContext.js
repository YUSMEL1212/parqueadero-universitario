import { createContext, useContext } from 'react';

export const AuthContext = createContext(null);

/**
 * Sesión actual: { usuario, cargando, sesionExpirada, iniciarSesion, registrar, cerrarSesion }.
 * `usuario` es el perfil de /api/auth/yo (id, nombre, email, rol, tipo_conductor, …).
 */
export function useAuth() {
  const contexto = useContext(AuthContext);
  if (!contexto) throw new Error('useAuth debe usarse dentro de <AuthProvider>.');
  return contexto;
}
