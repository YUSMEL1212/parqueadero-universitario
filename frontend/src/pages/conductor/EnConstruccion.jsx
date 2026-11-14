import { Link } from 'react-router-dom';

import { RUTA_INICIO_CONDUCTOR } from './rutas';

/** Pantalla provisional para las rutas del conductor que aún no están implementadas. */
export default function EnConstruccion({ titulo, children }) {
  return (
    <section className="tarjeta conductor">
      <h1 className="tarjeta__titulo">{titulo}</h1>
      <p className="texto-suave">{children}</p>
      <Link to={RUTA_INICIO_CONDUCTOR} className="boton boton--secundario">
        Volver al inicio
      </Link>
    </section>
  );
}
