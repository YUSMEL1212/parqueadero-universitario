import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { leerError } from '../api/errores';
import { useAuth } from '../auth/AuthContext';
import { zonaDe } from '../auth/roles';
import Aviso from '../components/Aviso';
import Campo from '../components/Campo';
import Marca from '../components/Marca';

const CORREO_VALIDO = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Mismos valores que usuarios.models.TipoConductor.
const TIPOS_CONDUCTOR = [
  { valor: '', texto: 'Selecciona una opción' },
  { valor: 'estudiante', texto: 'Estudiante' },
  { valor: 'docente', texto: 'Docente' },
  { valor: 'administrativo', texto: 'Administrativo' },
];

const VACIO = { nombre: '', email: '', tipo_conductor: '', telefono: '', password: '', confirmar: '' };

function validar(d) {
  const errores = {};
  if (!d.nombre.trim()) errores.nombre = 'Escribe tu nombre completo.';
  if (!d.email.trim()) errores.email = 'Escribe tu correo.';
  else if (!CORREO_VALIDO.test(d.email.trim())) errores.email = 'El correo no es válido.';
  if (!d.tipo_conductor) errores.tipo_conductor = 'Elige qué tipo de conductor eres.';
  if (d.telefono && !/^[0-9+\s-]{7,20}$/.test(d.telefono.trim())) {
    errores.telefono = 'Usa solo números (7 a 20 dígitos).';
  }
  if (!d.password) errores.password = 'Escribe una contraseña.';
  else if (d.password.length < 8) errores.password = 'Debe tener al menos 8 caracteres.';
  if (d.password && d.confirmar !== d.password) errores.confirmar = 'Las contraseñas no coinciden.';
  return errores;
}

export default function Registro() {
  const { registrar, iniciarSesion } = useAuth();
  const navigate = useNavigate();

  const [datos, setDatos] = useState(VACIO);
  const [errores, setErrores] = useState({});
  const [errorGeneral, setErrorGeneral] = useState(null);
  const [enviando, setEnviando] = useState(false);

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

    const email = datos.email.trim().toLowerCase();
    setEnviando(true);
    try {
      await registrar({
        nombre: datos.nombre.trim(),
        email,
        tipo_conductor: datos.tipo_conductor,
        telefono: datos.telefono.trim(),
        password: datos.password,
      });
    } catch (error) {
      const { general, campos } = leerError(error);
      setErrores(campos);
      setErrorGeneral(general);
      setEnviando(false);
      return;
    }

    // Cuenta creada: entra directo. Si el login falla, se envía al login con aviso.
    try {
      const perfil = await iniciarSesion(email, datos.password);
      navigate(zonaDe(perfil.rol) ?? '/', { replace: true });
    } catch {
      navigate('/login', {
        replace: true,
        state: { aviso: 'Tu cuenta fue creada. Inicia sesión para continuar.' },
      });
    }
  }

  return (
    <main className="auth">
      <div className="auth__caja">
        <Marca />
        <form className="tarjeta" onSubmit={enviar} noValidate>
          <h1 className="tarjeta__titulo">Crear cuenta</h1>
          <p className="texto-suave">Regístrate como conductor para usar el parqueadero.</p>

          <Aviso tipo="error">{errorGeneral}</Aviso>

          <Campo
            etiqueta="Nombre completo"
            name="nombre"
            autoComplete="name"
            value={datos.nombre}
            onChange={cambiar}
            error={errores.nombre}
            autoFocus
          />
          <Campo
            etiqueta="Correo"
            name="email"
            type="email"
            inputMode="email"
            autoComplete="email"
            value={datos.email}
            onChange={cambiar}
            error={errores.email}
          />
          <Campo
            etiqueta="Tipo de conductor"
            name="tipo_conductor"
            opciones={TIPOS_CONDUCTOR}
            value={datos.tipo_conductor}
            onChange={cambiar}
            error={errores.tipo_conductor}
          />
          <Campo
            etiqueta="Teléfono (opcional)"
            name="telefono"
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            value={datos.telefono}
            onChange={cambiar}
            error={errores.telefono}
          />
          <Campo
            etiqueta="Contraseña"
            name="password"
            type="password"
            autoComplete="new-password"
            value={datos.password}
            onChange={cambiar}
            error={errores.password}
            ayuda="Mínimo 8 caracteres; no solo números ni parecida a tu nombre o correo."
          />
          <Campo
            etiqueta="Confirmar contraseña"
            name="confirmar"
            type="password"
            autoComplete="new-password"
            value={datos.confirmar}
            onChange={cambiar}
            error={errores.confirmar}
          />

          <button type="submit" className="boton boton--primario boton--bloque" disabled={enviando}>
            {enviando ? 'Creando cuenta…' : 'Crear cuenta'}
          </button>
        </form>
        <p className="auth__pie">
          ¿Ya tienes cuenta? <Link to="/login">Inicia sesión</Link>
        </p>
      </div>
    </main>
  );
}
