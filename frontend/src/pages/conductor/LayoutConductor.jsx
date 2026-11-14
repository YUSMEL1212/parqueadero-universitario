/**
 * Marco de la zona del conductor: la pantalla actual y, abajo, la navegación entre
 * Inicio, Vehículos, Pagos e Historial. Va dentro de ZonaLayout (encabezado común).
 */
import { NavLink, Outlet } from 'react-router-dom';

import {
  RUTA_HISTORIAL,
  RUTA_INICIO_CONDUCTOR,
  RUTA_PAGAR_MENSUALIDAD,
  RUTA_VEHICULOS,
} from './rutas';

const PROPS_ICONO = {
  width: 24,
  height: 24,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
};

const ICONOS = {
  inicio: (
    <svg {...PROPS_ICONO}>
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5 9.5V20h5v-6h4v6h5V9.5" />
    </svg>
  ),
  vehiculos: (
    <svg {...PROPS_ICONO}>
      <path d="M5 16V11l2-5h10l2 5v5" />
      <path d="M3 16h18v2H3z" />
      <path d="M5 11h14" />
      <circle cx="7.5" cy="18.5" r="1.5" />
      <circle cx="16.5" cy="18.5" r="1.5" />
    </svg>
  ),
  pagos: (
    <svg {...PROPS_ICONO}>
      <rect x="3" y="5.5" width="18" height="13" rx="2" />
      <path d="M3 10h18" />
      <path d="M7 15h3" />
    </svg>
  ),
  historial: (
    <svg {...PROPS_ICONO}>
      <path d="M6 3h12v18l-3-2-3 2-3-2-3 2z" />
      <path d="M9 8h6M9 12h6" />
    </svg>
  ),
};

const SECCIONES = [
  { clave: 'inicio', texto: 'Inicio', ruta: RUTA_INICIO_CONDUCTOR, exacta: true },
  { clave: 'vehiculos', texto: 'Vehículos', ruta: RUTA_VEHICULOS },
  { clave: 'pagos', texto: 'Pagos', ruta: RUTA_PAGAR_MENSUALIDAD },
  { clave: 'historial', texto: 'Historial', ruta: RUTA_HISTORIAL },
];

function NavConductor() {
  return (
    <nav className="nav-inferior" aria-label="Secciones">
      <ul className="nav-inferior__lista">
        {SECCIONES.map(({ clave, texto, ruta, exacta }) => (
          <li key={clave}>
            {ruta ? (
              <NavLink
                to={ruta}
                end={exacta}
                className={({ isActive }) =>
                  isActive ? 'nav-inferior__item nav-inferior__item--activo' : 'nav-inferior__item'
                }
              >
                {ICONOS[clave]}
                <span>{texto}</span>
              </NavLink>
            ) : (
              <span
                className="nav-inferior__item nav-inferior__item--deshabilitado"
                aria-disabled="true"
                title="Disponible pronto"
              >
                {ICONOS[clave]}
                <span>{texto}</span>
                <span className="sr-only"> (disponible pronto)</span>
              </span>
            )}
          </li>
        ))}
      </ul>
    </nav>
  );
}

export default function LayoutConductor() {
  return (
    <div className="zona-conductor">
      <Outlet />
      <NavConductor />
    </div>
  );
}
