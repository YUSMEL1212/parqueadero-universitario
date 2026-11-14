/** Mensaje destacado en un formulario. tipo: 'error' | 'info' | 'exito'. */
export default function Aviso({ tipo = 'info', children }) {
  if (!children) return null;
  return (
    <div className={`aviso aviso--${tipo}`} role={tipo === 'error' ? 'alert' : 'status'}>
      {children}
    </div>
  );
}
