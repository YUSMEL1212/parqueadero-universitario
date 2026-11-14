/**
 * Tarifas (/admin/tarifas): los seis valores vigentes como campos editables y, debajo,
 * el historial de cambios.
 *
 * Guardar pide confirmación mostrando qué cambia, porque el cambio aplica a los cobros
 * nuevos: el motor de cobro usa la tarifa vigente al momento de la salida. Luego llama a
 * PUT /api/tarifas con los seis valores; el backend solo crea filas para los que cambian
 * y cierra la vigencia de las anteriores.
 *
 * El historial (GET /api/tarifas/historial) trae cada versión de cada tarifa; el valor
 * anterior de una fila es el de la versión previa del mismo tipo y concepto.
 */
import { useMemo, useState } from 'react';

import api from '../../api/client';
import Aviso from '../../components/Aviso';
import useConsulta from '../../hooks/useConsulta';
import { formatoFecha, formatoHora, formatoPesos } from '../../utils/formato';
import { NOMBRE_TIPO } from '../conductor/vehiculos';
import { CONCEPTOS_TARIFA, NOMBRE_CONCEPTO, TIPOS_VEHICULO, mensajeError } from './admin';

const clave = (tipo, concepto) => `${tipo}.${concepto}`;

/** Lista de tarifas vigentes → { 'carro.hasta_2h': 7000, ... }. */
function valoresVigentes(tarifas) {
  const valores = {};
  for (const t of tarifas ?? []) valores[clave(t.tipo_vehiculo, t.concepto)] = t.valor;
  return valores;
}

/** Errores de DRF del PUT ({ moto: { hasta_2h: ['…'] } }) → { 'moto.hasta_2h': '…' }. */
function erroresPorCelda(error) {
  const data = error?.response?.status === 400 ? error.response.data : null;
  const errores = {};
  if (!data || typeof data !== 'object') return errores;
  for (const tipo of TIPOS_VEHICULO) {
    const porTipo = data[tipo];
    if (!porTipo || typeof porTipo !== 'object' || Array.isArray(porTipo)) continue;
    for (const [concepto, mensajes] of Object.entries(porTipo)) {
      errores[clave(tipo, concepto)] = [].concat(mensajes).join(' ');
    }
  }
  return errores;
}

/** Versiones de tarifas → cambios (con valor anterior), del más reciente al más antiguo. */
function cambiosDelHistorial(filas) {
  const ordenadas = [...filas].sort(
    (a, b) => Date.parse(a.vigente_desde) - Date.parse(b.vigente_desde) || a.id - b.id,
  );
  const ultimo = {};
  const cambios = ordenadas.map((fila) => {
    const k = clave(fila.tipo_vehiculo, fila.concepto);
    const anterior = ultimo[k] ?? null;
    ultimo[k] = fila.valor;
    return { ...fila, anterior };
  });
  return cambios.reverse();
}

function nombreTarifa(tipo, concepto) {
  return `${NOMBRE_TIPO[tipo] ?? tipo} · ${NOMBRE_CONCEPTO[concepto] ?? concepto}`;
}

// ---- Tabla editable ----------------------------------------------------------------

function TablaTarifas({ valores, guardados, errores, onCambiar, disabled }) {
  return (
    <div className="tabla-contenedor">
      <table className="tabla tabla--tarifas">
        <caption className="sr-only">Tarifas vigentes en pesos colombianos</caption>
        <thead>
          <tr>
            <th scope="col">Vehículo</th>
            {CONCEPTOS_TARIFA.map((c) => (
              <th key={c} scope="col">
                {NOMBRE_CONCEPTO[c]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {TIPOS_VEHICULO.map((tipo) => (
            <tr key={tipo}>
              <th scope="row">{NOMBRE_TIPO[tipo]}</th>
              {CONCEPTOS_TARIFA.map((concepto) => {
                const k = clave(tipo, concepto);
                const error = errores[k];
                const cambiado = valores[k] !== String(guardados[k] ?? '');
                const id = `tarifa-${tipo}-${concepto}`;
                return (
                  <td key={concepto}>
                    <div className={error ? 'campo campo--error' : 'campo'}>
                      <div className="campo-pesos">
                        <span className="campo-pesos__signo" aria-hidden="true">
                          $
                        </span>
                        <input
                          id={id}
                          className={
                            cambiado
                              ? 'campo__control campo__control--compacto campo__control--cambiado'
                              : 'campo__control campo__control--compacto'
                          }
                          inputMode="numeric"
                          autoComplete="off"
                          value={valores[k]}
                          onChange={(e) => onCambiar(k, e.target.value.replace(/\D/g, ''))}
                          disabled={disabled}
                          aria-label={nombreTarifa(tipo, concepto)}
                          aria-invalid={error ? true : undefined}
                          aria-describedby={error ? `${id}-error` : undefined}
                          maxLength={10}
                        />
                      </div>
                      {error && (
                        <p id={`${id}-error`} className="campo__error">
                          {error}
                        </p>
                      )}
                      {cambiado && !error && guardados[k] != null && (
                        <p className="campo__ayuda">Antes {formatoPesos.format(guardados[k])}</p>
                      )}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Confirmacion({ cambios, onConfirmar, onVolver, enviando }) {
  return (
    <div className="confirmacion" role="alertdialog" aria-labelledby="titulo-confirmar" aria-describedby="texto-confirmar">
      <p id="titulo-confirmar" className="confirmacion__titulo">
        ¿Guardar {cambios.length === 1 ? 'este cambio' : `estos ${cambios.length} cambios`}?
      </p>
      <ul className="confirmacion__lista">
        {cambios.map(({ k, tipo, concepto, antes, despues }) => (
          <li key={k}>
            <span>{nombreTarifa(tipo, concepto)}</span>
            <span className="confirmacion__valores">
              {antes != null ? formatoPesos.format(antes) : 'Sin valor'} →{' '}
              <strong>{formatoPesos.format(despues)}</strong>
            </span>
          </li>
        ))}
      </ul>
      <p id="texto-confirmar">
        El cambio aplica a los cobros nuevos desde este momento, incluidos los vehículos que ya
        están adentro y salgan después. Los recibos ya cobrados conservan la tarifa con la que se
        cobraron, y las mensualidades pagadas no cambian.
      </p>
      <div className="confirmacion__acciones">
        <button type="button" className="boton boton--secundario" onClick={onVolver} disabled={enviando}>
          Volver
        </button>
        <button type="button" className="boton boton--primario" onClick={onConfirmar} disabled={enviando}>
          {enviando ? 'Guardando…' : 'Confirmar y guardar'}
        </button>
      </div>
    </div>
  );
}

// ---- Historial ---------------------------------------------------------------------

function Historial({ consulta }) {
  const { datos, error, cargando, recargar } = consulta;
  const cambios = useMemo(() => cambiosDelHistorial(datos ?? []), [datos]);

  if (cargando && !datos) {
    return (
      <div className="vacio" role="status">
        <span className="spinner" aria-hidden="true" />
        <span className="texto-suave">Cargando el historial…</span>
      </div>
    );
  }
  if (error) {
    return (
      <div className="vacio">
        <p className="vacio__titulo">No se pudo cargar el historial</p>
        <p className="texto-suave">{mensajeError(error)}</p>
        <button type="button" className="boton boton--primario" onClick={recargar}>
          Reintentar
        </button>
      </div>
    );
  }
  if (!cambios.length) {
    return (
      <div className="vacio">
        <p className="texto-suave">Todavía no hay tarifas registradas.</p>
      </div>
    );
  }

  return (
    <div className="tabla-contenedor">
      <table className="tabla">
        <caption className="sr-only">Historial de cambios de tarifas</caption>
        <thead>
          <tr>
            <th scope="col">Fecha</th>
            <th scope="col">Usuario</th>
            <th scope="col">Tarifa</th>
            <th scope="col" className="num">
              Valor anterior
            </th>
            <th scope="col" className="num">
              Valor nuevo
            </th>
          </tr>
        </thead>
        <tbody>
          {cambios.map((c) => {
            const fecha = new Date(c.vigente_desde);
            return (
              <tr key={c.id}>
                <td className="tabla__fecha">
                  <time dateTime={c.vigente_desde}>
                    {formatoFecha.format(fecha)}
                    <span className="texto-suave"> · {formatoHora.format(fecha)}</span>
                  </time>
                </td>
                <td>{c.creado_por_nombre ?? <span className="texto-suave">Carga inicial</span>}</td>
                <td>
                  {nombreTarifa(c.tipo_vehiculo, c.concepto)}
                  {c.vigente_hasta == null && <span className="chip chip--pequeno">Vigente</span>}
                </td>
                <td className="num">
                  {c.anterior != null ? formatoPesos.format(c.anterior) : <span className="texto-suave">—</span>}
                </td>
                <td className="num tabla__principal">{formatoPesos.format(c.valor)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---- Pantalla ----------------------------------------------------------------------

export default function Tarifas() {
  const vigentes = useConsulta('/api/tarifas');
  const historial = useConsulta('/api/tarifas/historial');
  const guardados = useMemo(() => valoresVigentes(vigentes.datos), [vigentes.datos]);

  // Solo lo que el administrador escribió; lo demás se toma de `guardados`.
  const [editados, setEditados] = useState({});
  const [errores, setErrores] = useState({});
  const [confirmando, setConfirmando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState(null);

  const valores = {};
  for (const tipo of TIPOS_VEHICULO) {
    for (const concepto of CONCEPTOS_TARIFA) {
      const k = clave(tipo, concepto);
      valores[k] = editados[k] ?? String(guardados[k] ?? '');
    }
  }

  const cambios = Object.keys(valores)
    .filter((k) => valores[k] !== String(guardados[k] ?? ''))
    .map((k) => {
      const [tipo, concepto] = k.split('.');
      return { k, tipo, concepto, antes: guardados[k] ?? null, despues: Number(valores[k]) };
    });

  function cambiar(k, valor) {
    setAviso(null);
    setConfirmando(false);
    setErrores((anteriores) => {
      const siguientes = { ...anteriores };
      delete siguientes[k];
      return siguientes;
    });
    setEditados((e) => ({ ...e, [k]: valor }));
  }

  function validar() {
    const nuevos = {};
    for (const [k, valor] of Object.entries(valores)) {
      if (!valor) nuevos[k] = 'Escribe un valor.';
      else if (Number(valor) <= 0) nuevos[k] = 'Debe ser mayor que 0.';
    }
    setErrores(nuevos);
    return Object.keys(nuevos).length === 0;
  }

  function pedirConfirmacion() {
    setAviso(null);
    if (validar()) setConfirmando(true);
  }

  async function guardar() {
    const cuerpo = {};
    for (const tipo of TIPOS_VEHICULO) {
      cuerpo[tipo] = {};
      for (const concepto of CONCEPTOS_TARIFA) cuerpo[tipo][concepto] = Number(valores[clave(tipo, concepto)]);
    }
    setEnviando(true);
    try {
      const { data } = await api.put('/api/tarifas', cuerpo);
      vigentes.setDatos(data.vigentes);
      setEditados({});
      setConfirmando(false);
      const n = data.creadas.length;
      setAviso({
        tipo: 'exito',
        texto: n === 1 ? 'Se guardó 1 tarifa nueva.' : `Se guardaron ${n} tarifas nuevas.`,
      });
      historial.recargar();
    } catch (e) {
      const porCelda = erroresPorCelda(e);
      setErrores(porCelda);
      setConfirmando(false);
      const conflicto = e?.response?.status === 409;
      setAviso({
        tipo: 'error',
        texto: Object.keys(porCelda).length ? 'Revisa los valores marcados.' : mensajeError(e),
      });
      // Otro administrador cambió las tarifas: se traen las vigentes para comparar.
      if (conflicto) vigentes.recargar();
    } finally {
      setEnviando(false);
    }
  }

  let editor;
  if (vigentes.cargando && !vigentes.datos) {
    editor = (
      <div className="vacio" role="status">
        <span className="spinner" aria-hidden="true" />
        <span className="texto-suave">Cargando tarifas…</span>
      </div>
    );
  } else if (vigentes.error) {
    editor = (
      <div className="vacio">
        <p className="vacio__titulo">No se pudieron cargar las tarifas</p>
        <p className="texto-suave">{mensajeError(vigentes.error)}</p>
        <button type="button" className="boton boton--primario" onClick={vigentes.recargar}>
          Reintentar
        </button>
      </div>
    );
  } else {
    editor = (
      <>
        <TablaTarifas
          valores={valores}
          guardados={guardados}
          errores={errores}
          onCambiar={cambiar}
          disabled={enviando}
        />
        {confirmando ? (
          <Confirmacion
            cambios={cambios}
            enviando={enviando}
            onConfirmar={guardar}
            onVolver={() => setConfirmando(false)}
          />
        ) : (
          <div className="barra-herramientas barra-herramientas--fin">
            <p className="texto-suave barra-herramientas__nota">
              El cambio aplica a los cobros nuevos; los recibos ya cobrados no cambian.
            </p>
            <div className="barra-herramientas__acciones">
              {cambios.length > 0 && (
                <button
                  type="button"
                  className="boton boton--secundario"
                  onClick={() => {
                    setEditados({});
                    setErrores({});
                  }}
                >
                  Descartar
                </button>
              )}
              <button
                type="button"
                className="boton boton--primario"
                onClick={pedirConfirmacion}
                disabled={cambios.length === 0}
              >
                Guardar tarifas
              </button>
            </div>
          </div>
        )}
      </>
    );
  }

  return (
    <div className="panel">
      <header className="saludo">
        <h1 className="saludo__titulo">Tarifas</h1>
        <p className="texto-suave">Valores vigentes en pesos colombianos.</p>
      </header>

      {aviso && <Aviso tipo={aviso.tipo}>{aviso.texto}</Aviso>}

      <section className="bloque" aria-label="Tarifas vigentes">
        {editor}
      </section>

      <section className="bloque" aria-labelledby="titulo-historial">
        <h2 id="titulo-historial" className="bloque__titulo">
          Historial de cambios
        </h2>
        <Historial consulta={historial} />
      </section>
    </div>
  );
}
