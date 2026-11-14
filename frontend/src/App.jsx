import { Suspense, lazy } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';

import { ROLES } from './auth/roles';
import { RedireccionInicio, RutaProtegida, RutaPublica } from './auth/rutas';
import ZonaLayout from './components/ZonaLayout';
import Login from './pages/Login';
import Registro from './pages/Registro';
import LayoutAdmin from './pages/admin/LayoutAdmin';
import Reportes from './pages/admin/Reportes';
import Sensores from './pages/admin/Sensores';
import Tarifas from './pages/admin/Tarifas';
import Usuarios from './pages/admin/Usuarios';
import {
  RUTA_ADMIN,
  RUTA_REPORTES,
  RUTA_SENSORES,
  RUTA_TARIFAS,
  RUTA_USUARIOS,
} from './pages/admin/rutas';
import Historial from './pages/conductor/Historial';
import InicioConductor from './pages/conductor/InicioConductor';
import LayoutConductor from './pages/conductor/LayoutConductor';
import MisVehiculos from './pages/conductor/MisVehiculos';
import PagarMensualidad from './pages/conductor/PagarMensualidad';
import {
  RUTA_HISTORIAL,
  RUTA_INICIO_CONDUCTOR,
  RUTA_PAGAR_MENSUALIDAD,
  RUTA_VEHICULOS,
} from './pages/conductor/rutas';
import Cobros from './pages/porteria/Cobros';
import Invitados from './pages/porteria/Invitados';
import LayoutPorteria from './pages/porteria/LayoutPorteria';
import { RUTA_COBROS, RUTA_INVITADOS, RUTA_LECTOR } from './pages/porteria/rutas';

// El lector trae html5-qrcode (~400 kB): se descarga solo cuando un guarda lo abre.
const Lector = lazy(() => import('./pages/porteria/Lector'));

const cargandoLector = (
  <div className="vacio" role="status">
    <span className="spinner" aria-hidden="true" />
    <span className="texto-suave">Cargando el lector…</span>
  </div>
);

export default function App() {
  return (
    <Routes>
      <Route element={<RutaPublica />}>
        <Route path="/login" element={<Login />} />
        <Route path="/registro" element={<Registro />} />
      </Route>

      <Route element={<RutaProtegida roles={[ROLES.CONDUCTOR]} />}>
        <Route element={<ZonaLayout />}>
          <Route element={<LayoutConductor />}>
            <Route path={RUTA_INICIO_CONDUCTOR} element={<InicioConductor />} />
            <Route path={RUTA_VEHICULOS} element={<MisVehiculos />} />
            <Route path={RUTA_HISTORIAL} element={<Historial />} />
            <Route path={RUTA_PAGAR_MENSUALIDAD} element={<PagarMensualidad />} />
          </Route>
        </Route>
      </Route>

      <Route element={<RutaProtegida roles={[ROLES.GUARDA]} />}>
        <Route element={<ZonaLayout />}>
          {/* El guarda solo tiene estas tres pantallas; cualquier otra ruta lo trae aquí. */}
          <Route element={<LayoutPorteria />}>
            <Route
              path={RUTA_LECTOR}
              element={
                <Suspense fallback={cargandoLector}>
                  <Lector />
                </Suspense>
              }
            />
            <Route path={RUTA_INVITADOS} element={<Invitados />} />
            <Route path={RUTA_COBROS} element={<Cobros />} />
          </Route>
        </Route>
      </Route>

      <Route element={<RutaProtegida roles={[ROLES.ADMINISTRADOR]} />}>
        <Route element={<ZonaLayout />}>
          <Route element={<LayoutAdmin />}>
            <Route path={RUTA_ADMIN} element={<Navigate to={RUTA_USUARIOS} replace />} />
            <Route path={RUTA_USUARIOS} element={<Usuarios />} />
            <Route path={RUTA_TARIFAS} element={<Tarifas />} />
            <Route path={RUTA_SENSORES} element={<Sensores />} />
            <Route path={RUTA_REPORTES} element={<Reportes />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<RedireccionInicio />} />
    </Routes>
  );
}
