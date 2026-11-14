import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import { leerError } from '../api/errores';
import { useAuth } from '../auth/AuthContext';
import { zonaDe } from '../auth/roles';
import Aviso from '../components/Aviso';
import Campo from '../components/Campo';
import Marca from '../components/Marca';

const CORREO_VALIDO = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function validar({ email, password }) {
  const errores = {};
  if (!email.trim()) errores.email = 'Escribe tu correo.';
  else if (!CORREO_VALIDO.test(email.trim())) errores.email = 'El correo no es válido.';
  if (!password) errores.password = 'Escribe tu contraseña.';
  return errores;
}

export default function Login() {
  const { iniciarSesion, sesionExpirada } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [datos, setDatos] = useState({ email: '', password: '' });
  const [errores, setErrores] = useState({});
  const [errorGeneral, setErrorGeneral] = useState(null);
  const [enviando, setEnviando] = useState(false);

  const aviso =
    location.state?.aviso ?? (sesionExpirada ? 'Tu sesión expiró. Vuelve a iniciar sesión.' : null);

  function cambiar(e) {
    const { name, value } = e.target;
    setDatos((d) => ({ ...d, [name]: value }));
    if (errores[name]) setErrores((er) => ({ ...er, [name]: undefined }));
  }

  async function enviar(e) {
    e.preventDefault();
    const encontrados = validar(datos);
    setErrores(encontrados);
    setErrorGeneral(null);
    if (Object.keys(encontrados).length) return;

    setEnviando(true);
    try {
      const perfil = await iniciarSesion(datos.email.trim(), datos.password);
      const zona = zonaDe(perfil.rol) ?? '/';
      // Si venía de una ruta de su propia zona, vuelve a ella.
      const desde = location.state?.desde;
      navigate(desde?.startsWith(zona) ? desde : zona, { replace: true });
    } catch (error) {
      const { general, campos } = leerError(error, {
        401: 'Correo o contraseña incorrectos, o la cuenta está desactivada.',
      });
      setErrores(campos);
      setErrorGeneral(general);
      setEnviando(false);
    }
  }

  return (
    <main className="auth">
      <div className="auth__caja">
        <Marca />
        <form className="tarjeta" onSubmit={enviar} noValidate>
          <h1 className="tarjeta__titulo">Iniciar sesión</h1>
          <p className="texto-suave">Ingresa con tu correo y contraseña.</p>

          <Aviso tipo="info">{!errorGeneral && aviso}</Aviso>
          <Aviso tipo="error">{errorGeneral}</Aviso>

          <Campo
            etiqueta="Correo"
            name="email"
            type="email"
            inputMode="email"
            autoComplete="username"
            value={datos.email}
            onChange={cambiar}
            error={errores.email}
            autoFocus
          />
          <Campo
            etiqueta="Contraseña"
            name="password"
            type="password"
            autoComplete="current-password"
            value={datos.password}
            onChange={cambiar}
            error={errores.password}
          />

          <button type="submit" className="boton boton--primario boton--bloque" disabled={enviando}>
            {enviando ? 'Ingresando…' : 'Ingresar'}
          </button>
        </form>
        <p className="auth__pie">
          ¿No tienes cuenta? <Link to="/registro">Regístrate</Link>
        </p>
      </div>
    </main>
  );
}
