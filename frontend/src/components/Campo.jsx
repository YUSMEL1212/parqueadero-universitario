/**
 * Etiqueta + control + mensaje de error/ayuda.
 * Con `opciones` ([{ valor, texto }]) dibuja un <select>; si no, un <input>.
 */
export default function Campo({ etiqueta, name, error, ayuda, opciones, ...props }) {
  const id = `campo-${name}`;
  const idNota = `${id}-nota`;
  const nota = error || ayuda;
  const comunes = {
    id,
    name,
    className: 'campo__control',
    'aria-invalid': error ? true : undefined,
    'aria-describedby': nota ? idNota : undefined,
    ...props,
  };

  return (
    <div className={error ? 'campo campo--error' : 'campo'}>
      <label htmlFor={id} className="campo__etiqueta">
        {etiqueta}
      </label>
      {opciones ? (
        <select {...comunes}>
          {opciones.map((o) => (
            <option key={o.valor} value={o.valor} disabled={o.valor === ''}>
              {o.texto}
            </option>
          ))}
        </select>
      ) : (
        <input {...comunes} />
      )}
      {nota && (
        <p id={idNota} className={error ? 'campo__error' : 'campo__ayuda'}>
          {nota}
        </p>
      )}
    </div>
  );
}
