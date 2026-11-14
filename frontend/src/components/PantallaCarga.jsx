export default function PantallaCarga() {
  return (
    <div className="pantalla-carga" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>Cargando…</span>
    </div>
  );
}
