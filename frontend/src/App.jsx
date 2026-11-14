import { Suspense, lazy } from 'react';
import { Route, Routes } from 'react-router-dom';

import { ROLES } from './auth/roles';
import { RedireccionInicio, RutaProtegida, RutaPublica } from './auth/rutas';
import ZonaLayout from './components/ZonaLayout';
import Login from './pages/Login';
import Registro from './pages/Registro';
import InicioAdmin from './pages/admin/InicioAdmin';
import EnConstruccion from './pages/conductor/EnConstruccion';
import Historial from './pages/conductor/Historial';
import InicioConductor from './pages/conductor/InicioConductor';
import LayoutConductor from './pages/conductor/LayoutConductor';
import MisVehiculos from './pages/conductor/MisVehiculos';
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
            {/* Ruta preparada: la pantalla real reemplaza a EnConstruccion. */}
            <Route
              path={RUTA_PAGAR_MENSUALIDAD}
              element={
                <EnConstruccion titulo="Pagar mensualidad">
                  El pago en línea de la mensualidad estará disponible pronto.
                </EnConstruccion>
              }
            />
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
          <Route path="/admin" element={<InicioAdmin />} />
        </Route>
      </Route>

      <Route path="*" element={<RedireccionInicio />} />
    </Routes>
  );
}
