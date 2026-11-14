/**
 * Historial (/conductor/historial): recibos de las salidas del conductor, del más
 * reciente al más antiguo, con filtro por tipo de cobro.
 *
 * El recibo no trae el motivo del cobro; se deduce de la tarifa aplicada:
 *   tarifa null        → mensualidad activa (cobro 0)
 *   tarifa.concepto    → 'hasta_2h' o 'mas_2h' (cobro por fracción)
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { leerError } from '../../api/errores';
import useConsulta from '../../hooks/useConsulta';
import { RUTA_INICIO_CONDUCTOR } from './rutas';
import { NOMBRE_TIPO, formatearPlaca } from './vehiculos';

const MOTIVOS = {
  mensualidad_activa: 'Mensualidad activa',
  hasta_2h: 'Hasta 2 horas',
  mas_2h: 'Más de 2 horas',
};

const FILTROS = [
  { valor: 'todos', texto: 'Todos' },
  { valor: 'fraccion', texto: 'Fracción' },
  { valor: 'mensualidad', texto: 'Mensualidad' },
];

const VACIO_FILTRO = {
  fraccion: 'No tienes recibos pagados por fracción.',
  mensualidad: 'No tienes recibos cubiertos por mensualidad.',
};

const formatoPesos = new Intl.NumberFormat('es-CO', {
  style: 'currency',
  currency: 'COP',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});
const formatoFecha = new Intl.DateTimeFormat('es-CO', { day: 'numeric', month: 'long', year: 'numeric' });
const formatoHora = new Intl.DateTimeFormat('es-CO', { hour: 'numeric', minute: '2-digit' });
const formatoDiaCorto = new Intl.DateTimeFormat('es-CO', { day: 'numeric', month: 'short' });

function motivoDe(recibo) {
  return recibo.tarifa ? recibo.tarifa.concepto : 'mensualidad_activa';
}

function categoriaDe(recibo) {
  return motivoDe(recibo) === 'mensualidad_activa' ? 'mensualidad' : 'fraccion';
}

/** 45 → "45 min"; 90 → "1 h 30 min"; 120 → "2 h". */
function formatearDuracion(minutos) {
  const total = Math.max(0, Number(minutos) || 0);
  const horas = Math.floor(total / 60);
  const resto = total % 60;
  if (!horas) return `${resto} min`;
  return resto ? `${horas} h ${resto} min` : `${horas} h`;
}

function mismoDia(a, b) {
  return a.toDateString() === b.toDateString();
}

function Recibo({ recibo }) {
  const entrada = new Date(recibo.hora_entrada);
  const salida = new Date(recibo.hora_salida);
  const motivo = motivoDe(recibo);
  const conMensualidad = motivo === 'mensualidad_activa';
  // Si salió otro día, la hora de salida lleva su fecha.
  const textoSalida = mismoDia(entrada, salida)
    ? formatoHora.format(salida)
    : `${formatoDiaCorto.format(salida)}, ${formatoHora.format(salida)}`;

  return (
    <li>
      <article className="recibo" aria-label={`Recibo de ${formatearPlaca(recibo.placa)}`}>
        <div className="recibo__encabezado">
          <div className="recibo__vehiculo">
            <span className="placa placa--pequena">{formatearPlaca(recibo.placa)}</span>
            <span className="texto-suave">{NOMBRE_TIPO[recibo.tipo_vehiculo] ?? recibo.tipo_vehiculo}</span>
          </div>
          <time className="recibo__fecha texto-suave" dateTime={recibo.hora_entrada}>
            {formatoFecha.format(entrada)}
          </time>
        </div>

        <div className="recibo__cobro">
          <p className="recibo__valor">{formatoPesos.format(recibo.valor_cobrado ?? 0)}</p>
          <p className={conMensualidad ? 'recibo__motivo recibo__motivo--mensualidad' : 'recibo__motivo'}>
            {MOTIVOS[motivo] ?? motivo}
          </p>
        </div>

        <dl className="recibo__tiempos">
          <div>
            <dt>Entrada</dt>
            <dd>
              <time dateTime={recibo.hora_entrada}>{formatoHora.format(entrada)}</time>
            </dd>
          </div>
          <div>
            <dt>Salida</dt>
            <dd>
              <time dateTime={recibo.hora_salida}>{textoSalida}</time>
            </dd>
          </div>
          <div>
            <dt>Tiempo total</dt>
            <dd>{formatearDuracion(recibo.minutos)}</dd>
          </div>
        </dl>
      </article>
    </li>
  );
}

function Filtro({ valor, onCambiar, conteos }) {
  return (
    <fieldset className="segmentos">
      <legend className="sr-only">Filtrar recibos por tipo</legend>
      <div className="segmentos__opciones">
        {FILTROS.map((f) => (
          <label key={f.valor} className="segmentos__opcion">
            <input
              type="radio"
              name="filtro"
              value={f.valor}
              checked={valor === f.valor}
              onChange={() => onCambiar(f.valor)}
            />
            <span>{f.texto}</span>
            <span className="segmentos__conteo">{conteos[f.valor]}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export default function Historial() {
  const { datos, error, cargando, recargar } = useConsulta('/api/accesos/historial');
  const [filtro, setFiltro] = useState('todos');

  let contenido;
  if (cargando && !datos) {
    contenido = (
      <div className="vacio" role="status">
        <span className="spinner" aria-hidden="true" />
        <span className="texto-suave">Cargando tus recibos…</span>
      </div>
    );
  } else if (error) {
    contenido = (
      <div className="vacio">
        <p className="vacio__titulo">No se pudo cargar tu historial</p>
        <p className="texto-suave">{leerError(error).general}</p>
        <button type="button" className="boton boton--primario" onClick={recargar}>
          Reintentar
        </button>
      </div>
    );
  } else if (!datos?.length) {
    contenido = (
      <div className="vacio">
        <p className="vacio__titulo">Aún no tienes recibos</p>
        <p className="texto-suave">
          Cada vez que salgas del parqueadero, aquí aparecerá tu recibo con la hora de entrada y
          de salida, el tiempo total y el valor.
        </p>
        <Link to={RUTA_INICIO_CONDUCTOR} className="boton boton--secundario">
          Ir al inicio
        </Link>
      </div>
    );
  } else {
    const recibos = [...datos].sort((a, b) => Date.parse(b.hora_salida) - Date.parse(a.hora_salida));
    const conteos = { todos: recibos.length, fraccion: 0, mensualidad: 0 };
    for (const r of recibos) conteos[categoriaDe(r)] += 1;
    const visibles = filtro === 'todos' ? recibos : recibos.filter((r) => categoriaDe(r) === filtro);

    contenido = (
      <>
        <Filtro valor={filtro} onCambiar={setFiltro} conteos={conteos} />
        {visibles.length ? (
          <ul className="lista-tarjetas" aria-label="Recibos">
            {visibles.map((r) => (
              <Recibo key={r.id} recibo={r} />
            ))}
          </ul>
        ) : (
          <div className="vacio">
            <p className="texto-suave">{VACIO_FILTRO[filtro]}</p>
          </div>
        )}
      </>
    );
  }

  return (
    <div className="conductor">
      <header className="saludo">
        <h1 className="saludo__titulo">Historial</h1>
        <p className="texto-suave">Tus recibos de salida, del más reciente al más antiguo.</p>
      </header>
      {contenido}
    </div>
  );
}
