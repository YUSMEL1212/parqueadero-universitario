import { Outlet } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext';
import { NOMBRE_ROL } from '../auth/roles';
import Marca from './Marca';

/** Encabezado común de /conductor, /porteria y /admin. */
export default function ZonaLayout() {
  const { usuario, cerrarSesion } = useAuth();

  return (
    <div className="zona">
      <header className="zona__barra">
        <Marca compacta />
        <div className="zona__usuario">
          <span className="zona__nombre">{usuario.nombre}</span>
          <span className="chip">{NOMBRE_ROL[usuario.rol] ?? usuario.rol}</span>
          <button type="button" className="boton boton--texto" onClick={cerrarSesion}>
            Salir
          </button>
        </div>
      </header>
      <main className="zona__contenido">
        <Outlet />
      </main>
    </div>
  );
}
