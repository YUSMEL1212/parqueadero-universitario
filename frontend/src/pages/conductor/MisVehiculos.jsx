/**
 * Mis vehículos (/conductor/vehiculos):
 *   1. Lista de los vehículos activos del conductor, con su estado (adentro o afuera).
 *   2. Eliminar con confirmación; no se permite si el vehículo está adentro.
 *   3. Formulario para agregar un carro o una moto.
 *
 * Al eliminar un vehículo con historial, el backend lo desactiva (activo=false) para
 * conservar los recibos; por eso la lista muestra solo los activos.
 */
import { useRef, useState } from 'react';

import api from '../../api/client';
import { leerError } from '../../api/errores';
import Aviso from '../../components/Aviso';
import Campo from '../../components/Campo';
import useConsulta from '../../hooks/useConsulta';
import { NOMBRE_TIPO, ejemploPlaca, errorDePlaca, formatearPlaca, normalizarPlaca } from './vehiculos';

// ---- Lista -------------------------------------------------------------------------

function TarjetaVehiculo({ vehiculo, onEliminado, onSigueAdentro }) {
  const [confirmando, setConfirmando] = useState(false);
  const [eliminando, setEliminando] = useState(false);
  const [error, setError] = useState(null);
  const placa = formatearPlaca(vehiculo.placa);
  const idNota = `nota-${vehiculo.id}`;

  async function eliminar() {
    setEliminando(true);
    setError(null);
    try {
      await api.delete(`/api/vehiculos/${vehiculo.id}`);
      onEliminado(vehiculo.id);
    } catch (e) {
      const status = e.response?.status;
      if (status === 404) {
        // Ya no existe (se eliminó desde otro dispositivo): se quita de la lista.
        onEliminado(vehiculo.id);
        return;
      }
      if (status === 409) onSigueAdentro(vehiculo.id);
      setError(leerError(e).general);
      setEliminando(false);
      setConfirmando(false);
    }
  }

  return (
    <li className="vehiculo">
      <div className="vehiculo__fila">
        <div className="vehiculo__datos">
          <span className="placa">{placa}</span>
          <div className="vehiculo__detalle">
            <span className="vehiculo__tipo">{NOMBRE_TIPO[vehiculo.tipo] ?? vehiculo.tipo}</span>
            <span className={vehiculo.adentro ? 'estado estado--adentro' : 'estado'}>
              <span className="estado-punto" aria-hidden="true" />
              {vehiculo.adentro ? 'Dentro del parqueadero' : 'Fuera del parqueadero'}
            </span>
          </div>
        </div>
        {!confirmando && (
          <button
            type="button"
            className="boton boton--peligro-texto"
            onClick={() => setConfirmando(true)}
            disabled={vehiculo.adentro}
            aria-describedby={vehiculo.adentro ? idNota : undefined}
            aria-label={`Eliminar ${placa}`}
          >
            Eliminar
          </button>
        )}
      </div>

      {vehiculo.adentro && (
        <p id={idNota} className="vehiculo__nota texto-suave">
          Podrás eliminarlo cuando salga del parqueadero.
        </p>
      )}

      {confirmando && (
        <div className="vehiculo__confirmar" role="group" aria-label={`Confirmar eliminación de ${placa}`}>
          <p>
            ¿Eliminar <strong>{placa}</strong> de tu cuenta? Ya no podrás generar códigos de
            ingreso con este vehículo. Tus recibos anteriores se conservan.
          </p>
          <div className="vehiculo__acciones">
            <button
              type="button"
              className="boton boton--secundario"
              onClick={() => setConfirmando(false)}
              disabled={eliminando}
              autoFocus
            >
              Cancelar
            </button>
            <button type="button" className="boton boton--peligro" onClick={eliminar} disabled={eliminando}>
              {eliminando ? 'Eliminando…' : 'Sí, eliminar'}
            </button>
          </div>
        </div>
      )}

      <Aviso tipo="error">{error}</Aviso>
    </li>
  );
}

function ListaVehiculos({ consulta, vehiculos }) {
  const { error, cargando, recargar, setDatos } = consulta;

  if (cargando && !vehiculos) {
    return (
      <div className="vacio" role="status">
        <span className="spinner" aria-hidden="true" />
        <span className="texto-suave">Cargando tus vehículos…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="vacio">
        <p className="vacio__titulo">No se pudieron cargar tus vehículos</p>
        <p className="texto-suave">{leerError(error).general}</p>
        <button type="button" className="boton boton--primario" onClick={recargar}>
          Reintentar
        </button>
      </div>
    );
  }

  if (!vehiculos.length) {
    return (
      <div className="vacio">
        <p className="vacio__titulo">Aún no tienes vehículos registrados</p>
        <p className="texto-suave">
          Agrega tu carro o tu moto con el formulario de abajo para generar tu código de
          ingreso.
        </p>
      </div>
    );
  }

  const quitar = (id) => setDatos((lista) => lista?.filter((v) => v.id !== id) ?? lista);
  const marcarAdentro = (id) =>
    setDatos((lista) => lista?.map((v) => (v.id === id ? { ...v, adentro: true } : v)) ?? lista);

  return (
    <ul className="lista-tarjetas" aria-label="Tus vehículos">
      {vehiculos.map((v) => (
        <TarjetaVehiculo key={v.id} vehiculo={v} onEliminado={quitar} onSigueAdentro={marcarAdentro} />
      ))}
    </ul>
  );
}

// ---- Formulario --------------------------------------------------------------------

function SelectorTipo({ valor, onCambiar, disabled }) {
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

function FormularioVehiculo({ onAgregado }) {
  const [tipo, setTipo] = useState('carro');
  const [placa, setPlaca] = useState('');
  const [errorPlaca, setErrorPlaca] = useState(null);
  const [errorGeneral, setErrorGeneral] = useState(null);
  const [exito, setExito] = useState(null);
  const [enviando, setEnviando] = useState(false);
  const campoPlaca = useRef(null);

  // Una vez marcado el error, se revisa mientras escribe para quitarlo apenas se corrija.
  function cambiarPlaca(valor) {
    const texto = valor.toUpperCase();
    setPlaca(texto);
    setExito(null);
    if (errorPlaca) setErrorPlaca(errorDePlaca(texto, tipo));
  }

  function cambiarTipo(nuevo) {
    setTipo(nuevo);
    setExito(null);
    if (errorPlaca) setErrorPlaca(errorDePlaca(placa, nuevo));
  }

  async function enviar(evento) {
    evento.preventDefault();
    setErrorGeneral(null);
    setExito(null);

    const error = errorDePlaca(placa, tipo);
    if (error) {
      setErrorPlaca(error);
      campoPlaca.current?.focus();
      return;
    }

    setEnviando(true);
    try {
      const { data } = await api.post('/api/vehiculos', { placa: normalizarPlaca(placa), tipo });
      onAgregado(data);
      setPlaca('');
      setErrorPlaca(null);
      setExito(`Agregaste ${NOMBRE_TIPO[data.tipo]?.toLowerCase() ?? 'vehículo'} ${formatearPlaca(data.placa)}.`);
    } catch (e) {
      // Placa duplicada o rechazada: el backend la devuelve en `placa`.
      const { general, campos } = leerError(e);
      setErrorPlaca(campos.placa ?? null);
      setErrorGeneral(campos.placa ? null : campos.tipo ?? general);
      if (campos.placa) campoPlaca.current?.focus();
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form className="tarjeta" onSubmit={enviar} noValidate aria-labelledby="titulo-agregar">
      <h2 id="titulo-agregar" className="bloque__titulo">
        Agregar vehículo
      </h2>
      <Aviso tipo="error">{errorGeneral}</Aviso>
      <Aviso tipo="exito">{exito}</Aviso>
      <SelectorTipo valor={tipo} onCambiar={cambiarTipo} disabled={enviando} />
      <Campo
        ref={campoPlaca}
        etiqueta="Placa"
        name="placa"
        value={placa}
        onChange={(e) => cambiarPlaca(e.target.value)}
        error={errorPlaca}
        ayuda={`Por ejemplo ${ejemploPlaca(tipo)}. Puedes escribirla con o sin guion.`}
        placeholder={ejemploPlaca(tipo)}
        maxLength={9}
        autoComplete="off"
        autoCapitalize="characters"
        spellCheck={false}
        readOnly={enviando}
      />
      <button type="submit" className="boton boton--primario boton--bloque" disabled={enviando}>
        {enviando ? 'Agregando…' : 'Agregar vehículo'}
      </button>
    </form>
  );
}

// ---- Pantalla ----------------------------------------------------------------------

export default function MisVehiculos() {
  const consulta = useConsulta('/api/vehiculos');
  const vehiculos = consulta.datos?.filter((v) => v.activo) ?? null;

  function agregar(vehiculo) {
    consulta.setDatos((lista) => [vehiculo, ...(lista ?? [])]);
  }

  return (
    <div className="conductor">
      <header className="saludo">
        <h1 className="saludo__titulo">Mis vehículos</h1>
        <p className="texto-suave">Los vehículos con los que puedes ingresar al parqueadero.</p>
      </header>

      <ListaVehiculos consulta={consulta} vehiculos={vehiculos} />

      <FormularioVehiculo onAgregado={agregar} />
    </div>
  );
}
