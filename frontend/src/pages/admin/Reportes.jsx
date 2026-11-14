/**
 * Reportes (/admin/reportes): ingresos y cobros por día en un rango de fechas, desde
 * GET /api/reportes/ingresos.
 *
 * Los ingresos se cuentan el día en que el vehículo entra y lo cobrado el día en que
 * sale (cuando se recibe la plata). El pago de mensualidades no entra en este reporte.
 */
import { useState } from 'react';

import Campo from '../../components/Campo';
import useConsulta from '../../hooks/useConsulta';
import { formatoPesos } from '../../utils/formato';
import { fechaDeISO, fechaISO, mensajeError, sumarDias } from './admin';

const MAX_DIAS = 366;

const formatoDia = new Intl.DateTimeFormat('es-CO', { weekday: 'short', day: 'numeric', month: 'short' });
const formatoDiaAnio = new Intl.DateTimeFormat('es-CO', {
  weekday: 'short',
  day: 'numeric',
  month: 'short',
  year: 'numeric',
});
const formatoNumero = new Intl.NumberFormat('es-CO');

function rangoUltimos(dias) {
  const hoy = new Date();
  return { desde: fechaISO(sumarDias(hoy, -(dias - 1))), hasta: fechaISO(hoy) };
}

function rangoMesActual() {
  const hoy = new Date();
  return { desde: fechaISO(new Date(hoy.getFullYear(), hoy.getMonth(), 1)), hasta: fechaISO(hoy) };
}

const ATAJOS = [
  { texto: 'Últimos 7 días', rango: () => rangoUltimos(7) },
  { texto: 'Últimos 30 días', rango: () => rangoUltimos(30) },
  { texto: 'Este mes', rango: rangoMesActual },
];

function validarRango({ desde, hasta }) {
  if (!desde || !hasta) return 'Elige las dos fechas.';
  if (desde > hasta) return 'La fecha inicial no puede ser posterior a la final.';
  const dias = Math.round((fechaDeISO(hasta) - fechaDeISO(desde)) / 86400000) + 1;
  if (dias > MAX_DIAS) return `El rango no puede superar ${MAX_DIAS} días.`;
  return null;
}

function Metrica({ etiqueta, valor, nota }) {
  return (
    <div className="metrica">
      <p className="metrica__etiqueta">{etiqueta}</p>
      <p className="metrica__valor metrica__valor--dinero">{valor}</p>
      {nota && <p className="metrica__nota">{nota}</p>}
    </div>
  );
}

function TablaIngresos({ reporte }) {
  const { dias, totales } = reporte;
  const formato = reporte.desde.slice(0, 4) === reporte.hasta.slice(0, 4) ? formatoDia : formatoDiaAnio;
  const n = formatoNumero.format;
  const p = formatoPesos.format;

  return (
    <div className="tabla-contenedor">
      <table className="tabla tabla--reporte">
        <caption className="sr-only">Ingresos y valores cobrados por día</caption>
        <thead>
          <tr>
            <th scope="col" rowSpan={2}>
              Fecha
            </th>
            <th scope="colgroup" colSpan={3} className="tabla__grupo">
              Ingresos
            </th>
            <th scope="colgroup" colSpan={3} className="tabla__grupo">
              Cobrado
            </th>
          </tr>
          <tr>
            <th scope="col" className="num">
              Total
            </th>
            <th scope="col" className="num">
              Registrados
            </th>
            <th scope="col" className="num">
              Invitados
            </th>
            <th scope="col" className="num">
              Total
            </th>
            <th scope="col" className="num">
              Registrados
            </th>
            <th scope="col" className="num">
              Invitados
            </th>
          </tr>
        </thead>
        <tbody>
          {dias.map((d) => (
            <tr key={d.fecha} className={d.ingresos === 0 && d.cobrado === 0 ? 'fila--vacia' : undefined}>
              <th scope="row" className="tabla__fecha">
                <time dateTime={d.fecha}>{formato.format(fechaDeISO(d.fecha))}</time>
              </th>
              <td className="num tabla__principal">{n(d.ingresos)}</td>
              <td className="num">{n(d.ingresos_registrados)}</td>
              <td className="num">{n(d.ingresos_invitados)}</td>
              <td className="num tabla__principal">{p(d.cobrado)}</td>
              <td className="num">{p(d.cobrado_registrados)}</td>
              <td className="num">{p(d.cobrado_invitados)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">Total</th>
            <td className="num">{n(totales.ingresos)}</td>
            <td className="num">{n(totales.ingresos_registrados)}</td>
            <td className="num">{n(totales.ingresos_invitados)}</td>
            <td className="num">{p(totales.cobrado)}</td>
            <td className="num">{p(totales.cobrado_registrados)}</td>
            <td className="num">{p(totales.cobrado_invitados)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

export default function Reportes() {
  const [formulario, setFormulario] = useState(() => rangoUltimos(7));
  const [consulta, setConsulta] = useState(formulario);
  const [errorRango, setErrorRango] = useState(null);

  const url = `/api/reportes/ingresos?desde=${consulta.desde}&hasta=${consulta.hasta}`;
  const { datos, error, cargando, recargar } = useConsulta(url);
  const actualizando = cargando || datos?.desde !== consulta.desde || datos?.hasta !== consulta.hasta;

  function aplicar(rango) {
    const problema = validarRango(rango);
    setErrorRango(problema);
    if (!problema) setConsulta(rango);
  }

  function enviar(evento) {
    evento.preventDefault();
    aplicar(formulario);
  }

  function usarAtajo(atajo) {
    const rango = atajo.rango();
    setFormulario(rango);
    aplicar(rango);
  }

  let contenido;
  if (error) {
    contenido = (
      <div className="vacio">
        <p className="vacio__titulo">No se pudo cargar el reporte</p>
        <p className="texto-suave">{mensajeError(error)}</p>
        <button type="button" className="boton boton--primario" onClick={recargar}>
          Reintentar
        </button>
      </div>
    );
  } else if (!datos) {
    contenido = (
      <div className="vacio" role="status">
        <span className="spinner" aria-hidden="true" />
        <span className="texto-suave">Cargando el reporte…</span>
      </div>
    );
  } else {
    const { totales, dias } = datos;
    contenido = (
      <div className={actualizando ? 'bloque bloque--actualizando' : 'bloque'} aria-busy={actualizando}>
        <div className="metricas metricas--3">
          <Metrica
            etiqueta="Total cobrado"
            valor={formatoPesos.format(totales.cobrado)}
            nota={`Registrados ${formatoPesos.format(totales.cobrado_registrados)} · Invitados ${formatoPesos.format(totales.cobrado_invitados)}`}
          />
          <Metrica
            etiqueta="Ingresos"
            valor={formatoNumero.format(totales.ingresos)}
            nota={`Registrados ${formatoNumero.format(totales.ingresos_registrados)} · Invitados ${formatoNumero.format(totales.ingresos_invitados)}`}
          />
          <Metrica
            etiqueta="Promedio cobrado por día"
            valor={formatoPesos.format(Math.round(totales.cobrado / dias.length))}
            nota={dias.length === 1 ? '1 día' : `${dias.length} días`}
          />
        </div>
        <TablaIngresos reporte={datos} />
        <p className="texto-suave nota-pie">
          Los ingresos se cuentan el día en que el vehículo entra; lo cobrado, el día en que sale.
          Las salidas con mensualidad activa suman $ 0. No incluye el pago de mensualidades.
        </p>
      </div>
    );
  }

  return (
    <div className="panel">
      <header className="saludo">
        <h1 className="saludo__titulo">Reportes</h1>
        <p className="texto-suave">Ingresos y valores cobrados por día.</p>
      </header>

      <form className="tarjeta filtro-fechas" onSubmit={enviar} noValidate>
        <div className="filtro-fechas__campos">
          <Campo
            etiqueta="Desde"
            name="desde"
            type="date"
            value={formulario.desde}
            max={formulario.hasta || undefined}
            onChange={(e) => setFormulario((f) => ({ ...f, desde: e.target.value }))}
          />
          <Campo
            etiqueta="Hasta"
            name="hasta"
            type="date"
            value={formulario.hasta}
            min={formulario.desde || undefined}
            onChange={(e) => setFormulario((f) => ({ ...f, hasta: e.target.value }))}
          />
          <button type="submit" className="boton boton--primario">
            Consultar
          </button>
        </div>
        {errorRango && (
          <p className="campo__error" role="alert">
            {errorRango}
          </p>
        )}
        <div className="filtro-fechas__atajos">
          {ATAJOS.map((a) => (
            <button key={a.texto} type="button" className="boton boton--texto" onClick={() => usarAtajo(a)}>
              {a.texto}
            </button>
          ))}
        </div>
      </form>

      {contenido}
    </div>
  );
}
