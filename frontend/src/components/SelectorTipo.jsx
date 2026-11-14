import { NOMBRE_TIPO } from '../pages/conductor/vehiculos';

/** Control segmentado Carro / Moto. Lo usan "Mis vehículos" y el registro de invitados. */
export default function SelectorTipo({ valor, onCambiar, disabled }) {
  return (
    <fieldset className="segmentos" disabled={disabled}>
      <legend className="campo__etiqueta">Tipo de vehículo</legend>
      <div className="segmentos__opciones">
        {Object.entries(NOMBRE_TIPO).map(([tipo, texto]) => (
          <label key={tipo} className="segmentos__opcion">
            <input
              type="radio"
              name="tipo"
              value={tipo}
              checked={valor === tipo}
              onChange={() => onCambiar(tipo)}
            />
            <span>{texto}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
