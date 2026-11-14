/**
 * Marco de la zona del administrador: menú lateral con las cuatro secciones y, a la
 * derecha, la pantalla actual. En pantallas angostas el menú pasa arriba como una fila
 * desplazable. Va dentro de ZonaLayout (encabezado común).
 */
import { NavLink, Outlet } from 'react-router-dom';

import { RUTA_REPORTES, RUTA_SENSORES, RUTA_TARIFAS, RUTA_USUARIOS } from './rutas';

const PROPS_ICONO = {
  width: 20,
  height: 20,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
};

const ICONOS = {
  usuarios: (
    <svg {...PROPS_ICONO}>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20a6.5 6.5 0 0 1 13 0" />
      <path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.5a6.5 6.5 0 0 1 3.5 5.5" />
    </svg>
  ),
  tarifas: (
    <svg {...PROPS_ICONO}>
      <path d="M3 12V4.5A1.5 1.5 0 0 1 4.5 3H12l9 9-9 9-9-9Z" />
      <circle cx="8" cy="8" r="1.5" />
    </svg>
  ),
  sensores: (
    <svg {...PROPS_ICONO}>
      <circle cx="12" cy="12" r="2" />
      <path d="M8.5 15.5a5 5 0 0 1 0-7M15.5 8.5a5 5 0 0 1 0 7" />
      <path d="M5.6 18.4a9 9 0 0 1 0-12.8M18.4 5.6a9 9 0 0 1 0 12.8" />
    </svg>
  ),
  reportes: (
    <svg {...PROPS_ICONO}>
      <path d="M4 20V4M4 20h16" />
      <path d="M8 16v-4M12 16V8M16 16v-6" />
    </svg>
  ),
};

const SECCIONES = [
  { clave: 'usuarios', texto: 'Usuarios y roles', ruta: RUTA_USUARIOS },
  { clave: 'tarifas', texto: 'Tarifas', ruta: RUTA_TARIFAS },
  { clave: 'sensores', texto: 'Sensores y bahías', ruta: RUTA_SENSORES },
  { clave: 'reportes', texto: 'Reportes', ruta: RUTA_REPORTES },
];

export default function LayoutAdmin() {
  return (
    <div className="admin">
      <nav className="admin__menu" aria-label="Secciones de administración">
        <ul className="admin__lista">
          {SECCIONES.map(({ clave, texto, ruta }) => (
            <li key={clave}>
              <NavLink
                to={ruta}
                className={({ isActive }) =>
                  isActive ? 'admin__item admin__item--activo' : 'admin__item'
                }
              >
                {ICONOS[clave]}
                <span>{texto}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <div className="admin__contenido">
        <Outlet />
      </div>
    </div>
  );
}
