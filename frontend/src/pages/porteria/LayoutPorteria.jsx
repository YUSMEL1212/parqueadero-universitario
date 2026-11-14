/**
 * Marco de la zona del guarda: la pantalla actual y, abajo, la navegación entre
 * Lector, Invitados y Cobros. Va dentro de ZonaLayout (encabezado común).
 *
 * Guarda el estado que comparten las pantallas (por `useOutletContext`):
 *   modo        → 'entrada' | 'salida' del lector; se conserva al cambiar de pestaña.
 *   liquidacion → la salida que se está cobrando (respuesta de POST /api/accesos/salida).
 *                 Se guarda en sessionStorage para no perderla si se recarga la página;
 *                 el ticket sigue abierto hasta confirmar, así que no hay nada que deshacer.
 */
import { useCallback, useMemo, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';

import { MODOS } from './porteria';
import { RUTA_COBROS, RUTA_INVITADOS, RUTA_LECTOR } from './rutas';

const CLAVE_LIQUIDACION = 'parqueadero.porteria.liquidacion';

function leerLiquidacion() {
  try {
    const guardada = sessionStorage.getItem(CLAVE_LIQUIDACION);
    return guardada ? JSON.parse(guardada) : null;
  } catch {
    return null;
  }
}

function guardarLiquidacion(liquidacion) {
  try {
    if (liquidacion) sessionStorage.setItem(CLAVE_LIQUIDACION, JSON.stringify(liquidacion));
    else sessionStorage.removeItem(CLAVE_LIQUIDACION);
  } catch {
    // Almacenamiento bloqueado: la liquidación vive solo en memoria.
  }
}

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
  lector: (
    <svg {...PROPS_ICONO}>
      <path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3" />
      <path d="M8 8h3v3H8zM13 13h3v3h-3zM13 8h3M8 13v3h3" />
    </svg>
  ),
  invitados: (
    <svg {...PROPS_ICONO}>
      <circle cx="10" cy="8" r="3.5" />
      <path d="M3.5 20a6.5 6.5 0 0 1 13 0" />
      <path d="M19 8v6M16 11h6" />
    </svg>
  ),
  cobros: (
    <svg {...PROPS_ICONO}>
      <rect x="2.5" y="6" width="19" height="12" rx="2" />
      <circle cx="12" cy="12" r="2.5" />
      <path d="M6 9.5v5M18 9.5v5" />
    </svg>
  ),
};

const SECCIONES = [
  { clave: 'lector', texto: 'Lector', ruta: RUTA_LECTOR, exacta: true },
  { clave: 'invitados', texto: 'Invitados', ruta: RUTA_INVITADOS },
  { clave: 'cobros', texto: 'Cobros', ruta: RUTA_COBROS },
];

function NavPorteria({ cobroPendiente }) {
  return (
    <nav className="nav-inferior" aria-label="Secciones">
      <ul className="nav-inferior__lista nav-inferior__lista--3">
        {SECCIONES.map(({ clave, texto, ruta, exacta }) => {
          const pendiente = clave === 'cobros' && cobroPendiente;
          return (
            <li key={clave}>
              <NavLink
                to={ruta}
                end={exacta}
                className={({ isActive }) =>
                  isActive ? 'nav-inferior__item nav-inferior__item--activo' : 'nav-inferior__item'
                }
              >
                <span className="nav-inferior__icono">
                  {ICONOS[clave]}
                  {pendiente && <span className="nav-inferior__marca" aria-hidden="true" />}
                </span>
                <span>{texto}</span>
                {pendiente && <span className="sr-only"> (hay un cobro pendiente)</span>}
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export default function LayoutPorteria() {
  const [modo, setModo] = useState(MODOS.ENTRADA);
  const [liquidacion, setLiquidacionEstado] = useState(leerLiquidacion);

  const setLiquidacion = useCallback((nueva) => {
    guardarLiquidacion(nueva);
    setLiquidacionEstado(nueva);
  }, []);

  const contexto = useMemo(
    () => ({ modo, setModo, liquidacion, setLiquidacion }),
    [modo, liquidacion, setLiquidacion],
  );

  return (
    <div className="zona-porteria">
      <Outlet context={contexto} />
      <NavPorteria cobroPendiente={Boolean(liquidacion)} />
    </div>
  );
}
