/** Logo + nombre de la app. */
export default function Marca({ compacta = false }) {
  return (
    <div className={compacta ? 'marca marca--compacta' : 'marca'}>
      <img src="/favicon.svg" alt="" className="marca__logo" width="40" height="40" />
      <span className="marca__nombre">Parqueadero Universitario</span>
    </div>
  );
}
