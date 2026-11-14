import { Route, Routes } from 'react-router-dom';

import { ROLES } from './auth/roles';
import { RedireccionInicio, RutaProtegida, RutaPublica } from './auth/rutas';
import ZonaLayout from './components/ZonaLayout';
import Login from './pages/Login';
import Registro from './pages/Registro';
import InicioAdmin from './pages/admin/InicioAdmin';
import InicioConductor from './pages/conductor/InicioConductor';
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
