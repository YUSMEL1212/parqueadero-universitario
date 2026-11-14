import { Route, Routes } from 'react-router-dom';

import { ROLES } from './auth/roles';
import { RedireccionInicio, RutaProtegida, RutaPublica } from './auth/rutas';
import ZonaLayout from './components/ZonaLayout';
import Login from './pages/Login';
import Registro from './pages/Registro';
import InicioAdmin from './pages/admin/InicioAdmin';
import EnConstruccion from './pages/conductor/EnConstruccion';
import InicioConductor from './pages/conductor/InicioConductor';
import { RUTA_PAGAR_MENSUALIDAD, RUTA_VEHICULOS } from './pages/conductor/rutas';
import InicioPorteria from './pages/porteria/InicioPorteria';

export default function App() {
  return (
    <Routes>
      <Route element={<RutaPublica />}>
        <Route path="/login" element={<Login />} />
        <Route path="/registro" element={<Registro />} />
      </Route>

      <Route element={<RutaProtegida roles={[ROLES.CONDUCTOR]} />}>
        <Route element={<ZonaLayout />}>
          <Route path="/conductor" element={<InicioConductor />} />
          {/* Rutas preparadas: las pantallas reales reemplazan a EnConstruccion. */}
          <Route
            path={RUTA_PAGAR_MENSUALIDAD}
            element={
              <EnConstruccion titulo="Pagar mensualidad">
                El pago en línea de la mensualidad estará disponible pronto.
              </EnConstruccion>
            }
          />
          <Route
            path={RUTA_VEHICULOS}
            element={
              <EnConstruccion titulo="Mis vehículos">
                El registro de vehículos desde la app estará disponible pronto.
              </EnConstruccion>
            }
          />
        </Route>
      </Route>

      <Route element={<RutaProtegida roles={[ROLES.GUARDA]} />}>
        <Route element={<ZonaLayout />}>
          <Route path="/porteria" element={<InicioPorteria />} />
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
