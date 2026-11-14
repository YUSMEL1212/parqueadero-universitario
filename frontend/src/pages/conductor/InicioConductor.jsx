import { useAuth } from '../../auth/AuthContext';

export default function InicioConductor() {
  const { usuario } = useAuth();
  return (
    <section className="tarjeta">
      <h1 className="tarjeta__titulo">Hola, {usuario.nombre.split(' ')[0]}</h1>
      <p className="texto-suave">
        Aquí verás tus vehículos, tu código QR de ingreso y tus pagos. Esta sección está en
        construcción.
      </p>
    </section>
  );
}
