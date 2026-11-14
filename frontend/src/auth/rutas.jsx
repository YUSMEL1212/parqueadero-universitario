import { Navigate, Outlet, useLocation } from 'react-router-dom';

import PantallaCarga from '../components/PantallaCarga';
import SinZona from '../components/SinZona';
import { useAuth } from './AuthContext';
import { zonaDe } from './roles';

/**
 * Exige sesión y, si se indica `roles`, uno de esos roles.
 * Sin sesión → /login (recordando a dónde iba). Rol equivocado → la zona de su rol.
 */
export function RutaProtegida({ roles }) {
  const { usuario, cargando } = useAuth();
  const location = useLocation();

  if (cargando) return <PantallaCarga />;
  if (!usuario) return <Navigate to="/login" replace state={{ desde: location.pathname }} />;
  if (roles && !roles.includes(usuario.rol)) {
    const zona = zonaDe(usuario.rol);
    return zona ? <Navigate to={zona} replace /> : <SinZona />;
  }
  return <Outlet />;
}

/** Login y registro: si ya hay sesión, lleva a la zona del rol. */
export function RutaPublica() {
  const { usuario, cargando } = useAuth();

  if (cargando) return <PantallaCarga />;
  const zona = usuario && zonaDe(usuario.rol);
  if (zona) return <Navigate to={zona} replace />;
  return <Outlet />;
}

/** "/" y rutas desconocidas. */
export function RedireccionInicio() {
  const { usuario, cargando } = useAuth();

  if (cargando) return <PantallaCarga />;
  if (!usuario) return <Navigate to="/login" replace />;
  const zona = zonaDe(usuario.rol);
  return zona ? <Navigate to={zona} replace /> : <SinZona />;
}
