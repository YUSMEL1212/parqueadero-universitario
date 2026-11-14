import { useAuth } from '../auth/AuthContext';
import Marca from './Marca';

/** El usuario tiene sesión pero su rol no tiene una zona en la app. */
export default function SinZona() {
  const { cerrarSesion } = useAuth();
  return (
    <main className="auth">
      <div className="auth__caja">
        <Marca />
        <section className="tarjeta">
          <h1 className="tarjeta__titulo">Sin acceso</h1>
          <p className="texto-suave">
            Tu cuenta no tiene una zona asignada en la aplicación. Contacta al administrador del
            parqueadero.
          </p>
          <button type="button" className="boton boton--secundario" onClick={cerrarSesion}>
            Cerrar sesión
          </button>
        </section>
      </div>
    </main>
  );
}
