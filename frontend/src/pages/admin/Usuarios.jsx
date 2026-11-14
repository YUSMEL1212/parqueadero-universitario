/**
 * Usuarios y roles (/admin/usuarios): lista con buscador, rol y estado editables por
 * fila y un botón que guarda todos los cambios pendientes.
 *
 * Los cambios se acumulan en memoria (por id de usuario, con los valores originales)
 * hasta "Guardar cambios", así sobreviven a una nueva búsqueda. Al guardar se llama a
 * PATCH /api/usuarios/{id}/rol y PATCH /api/usuarios/{id} solo para lo que cambió; si un
 * usuario falla, sus cambios quedan pendientes y se muestra el motivo.
 *
 * El administrador no puede quitarse su propio rol ni desactivarse (el backend también
 * lo impide): en su fila esos controles van deshabilitados.
 */
import { useEffect, useState } from 'react';

import api from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import Aviso from '../../components/Aviso';
import Campo from '../../components/Campo';
import useConsulta from '../../hooks/useConsulta';
import { OPCIONES_ROL, mensajeError } from './admin';

/** `valor` con `ms` de retraso: evita una consulta por cada tecla del buscador. */
function useDiferido(valor, ms) {
  const [diferido, setDiferido] = useState(valor);
  useEffect(() => {
    const id = setTimeout(() => setDiferido(valor), ms);
    return () => clearTimeout(id);
  }, [valor, ms]);
  return diferido;
}

function hayDiferencia(cambio) {
  return cambio.rol !== cambio.usuario.rol || cambio.activo !== cambio.usuario.activo;
}

function NotaRoles() {
  return (
    <aside className="nota" aria-labelledby="titulo-roles">
      <h2 id="titulo-roles" className="bloque__titulo">
        Qué ve cada rol
      </h2>
      <dl className="nota__lista">
        <div>
          <dt>Conductor</dt>
          <dd>
            Su QR dinámico de entrada y salida, los cupos libres en vivo, sus vehículos, sus
            mensualidades y el historial de recibos.
          </dd>
        </div>
        <div>
          <dt>Guarda</dt>
          <dd>
            La portería: lector de QR para entradas y salidas, registro de invitados y cobro de
            las salidas.
          </dd>
        </div>
        <div>
          <dt>Administrador</dt>
          <dd>Este panel: usuarios y roles, tarifas, sensores y bahías, y reportes.</dd>
        </div>
      </dl>
      <p className="texto-suave nota__pie">
        Un cambio de rol rige desde la siguiente acción del usuario; para ver su nueva pantalla
        debe volver a abrir la app. Un usuario inactivo no puede iniciar sesión y su placa no
        abre la talanquera.
      </p>
    </aside>
  );
}

function Interruptor({ activo, onCambiar, disabled, etiqueta }) {
  return (
    <label className="interruptor">
      <input
        type="checkbox"
        role="switch"
        checked={activo}
        onChange={(e) => onCambiar(e.target.checked)}
        disabled={disabled}
        aria-label={etiqueta}
      />
      <span className="interruptor__pista" aria-hidden="true" />
      <span className={activo ? 'interruptor__texto' : 'interruptor__texto texto-suave'}>
        {activo ? 'Activo' : 'Inactivo'}
      </span>
    </label>
  );
}

function FilaUsuario({ usuario, cambio, esYo, onCambiar, deshabilitado }) {
  const rol = cambio?.rol ?? usuario.rol;
  const activo = cambio?.activo ?? usuario.activo;
  const modificada = cambio && hayDiferencia(cambio);
  const ayudaPropia = esYo ? 'No puedes cambiar tu propio rol ni desactivarte.' : undefined;

  return (
    <tr className={modificada ? 'fila--modificada' : undefined}>
      <td>
        <span className="tabla__principal">{usuario.nombre}</span>
        {esYo && <span className="chip chip--pequeno">Tú</span>}
      </td>
      <td className="tabla__correo">{usuario.email}</td>
      <td>
        <select
          className="campo__control campo__control--compacto"
          value={rol}
          onChange={(e) => onCambiar(usuario, 'rol', e.target.value)}
          disabled={esYo || deshabilitado}
          aria-label={`Rol de ${usuario.nombre}`}
          title={ayudaPropia}
        >
          {OPCIONES_ROL.map((o) => (
            <option key={o.valor} value={o.valor}>
              {o.texto}
            </option>
          ))}
        </select>
      </td>
      <td>
        <Interruptor
          activo={activo}
          onCambiar={(valor) => onCambiar(usuario, 'activo', valor)}
          disabled={esYo || deshabilitado}
          etiqueta={`Cuenta de ${usuario.nombre} activa`}
        />
      </td>
    </tr>
  );
}

export default function Usuarios() {
  const { usuario: yo } = useAuth();
  const [texto, setTexto] = useState('');
  const busqueda = useDiferido(texto.trim(), 300);
  const url = busqueda ? `/api/usuarios?buscar=${encodeURIComponent(busqueda)}` : '/api/usuarios';
  const { datos, error, cargando, recargar } = useConsulta(url);

  // id → { usuario (valores guardados), rol, activo }
  const [cambios, setCambios] = useState({});
  const [guardando, setGuardando] = useState(false);
  const [resultado, setResultado] = useState(null);

  const pendientes = Object.values(cambios);

  function cambiar(usuario, campo, valor) {
    setResultado(null);
    setCambios((anteriores) => {
      const actual = anteriores[usuario.id] ?? {
        usuario,
        rol: usuario.rol,
        activo: usuario.activo,
      };
      const nuevo = { ...actual, [campo]: valor };
      const siguientes = { ...anteriores };
      if (hayDiferencia(nuevo)) siguientes[usuario.id] = nuevo;
      else delete siguientes[usuario.id];
      return siguientes;
    });
  }

  async function guardar() {
    setGuardando(true);
    setResultado(null);
    const restantes = { ...cambios };
    const errores = [];
    let guardados = 0;

    for (const cambio of pendientes) {
      const { id, nombre } = cambio.usuario;
      try {
        if (cambio.rol !== cambio.usuario.rol) {
          await api.patch(`/api/usuarios/${id}/rol`, { rol: cambio.rol });
          // Si después falla el estado, el rol ya quedó guardado: no se vuelve a enviar.
          restantes[id] = { ...cambio, usuario: { ...cambio.usuario, rol: cambio.rol } };
        }
        if (cambio.activo !== cambio.usuario.activo) {
          await api.patch(`/api/usuarios/${id}`, { activo: cambio.activo });
        }
        delete restantes[id];
        guardados += 1;
      } catch (e) {
        errores.push(`${nombre}: ${mensajeError(e)}`);
      }
    }

    setCambios(restantes);
    setGuardando(false);
    setResultado({ guardados, errores });
    recargar();
  }

  let contenido;
  if (cargando && !datos) {
    contenido = (
      <div className="vacio" role="status">
        <span className="spinner" aria-hidden="true" />
        <span className="texto-suave">Cargando usuarios…</span>
      </div>
    );
  } else if (error) {
    contenido = (
      <div className="vacio">
        <p className="vacio__titulo">No se pudo cargar la lista de usuarios</p>
        <p className="texto-suave">{mensajeError(error)}</p>
        <button type="button" className="boton boton--primario" onClick={recargar}>
          Reintentar
        </button>
      </div>
    );
  } else if (!datos?.length) {
    contenido = (
      <div className="vacio">
        <p className="vacio__titulo">Sin resultados</p>
        <p className="texto-suave">Ningún usuario coincide con «{busqueda}».</p>
      </div>
    );
  } else {
    contenido = (
      <div className="tabla-contenedor">
        <table className="tabla">
          <caption className="sr-only">Usuarios del sistema</caption>
          <thead>
            <tr>
              <th scope="col">Nombre</th>
              <th scope="col">Correo</th>
              <th scope="col">Rol</th>
              <th scope="col">Estado</th>
            </tr>
          </thead>
          <tbody>
            {datos.map((u) => (
              <FilaUsuario
                key={u.id}
                usuario={u}
                cambio={cambios[u.id]}
                esYo={u.id === yo?.id}
                onCambiar={cambiar}
                deshabilitado={guardando}
              />
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="panel">
      <header className="saludo">
        <h1 className="saludo__titulo">Usuarios y roles</h1>
        <p className="texto-suave">Busca un usuario, cambia su rol o su estado y guarda.</p>
      </header>

      <div className="barra-herramientas">
        <div className="barra-herramientas__busqueda">
          <Campo
            etiqueta="Buscar"
            name="buscar"
            type="search"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Nombre o correo"
            autoComplete="off"
          />
        </div>
        <div className="barra-herramientas__acciones">
          {pendientes.length > 0 && (
            <button
              type="button"
              className="boton boton--secundario"
              onClick={() => setCambios({})}
              disabled={guardando}
            >
              Descartar
            </button>
          )}
          <button
            type="button"
            className="boton boton--primario"
            onClick={guardar}
            disabled={guardando || pendientes.length === 0}
          >
            {guardando
              ? 'Guardando…'
              : pendientes.length
                ? `Guardar cambios (${pendientes.length})`
                : 'Guardar cambios'}
          </button>
        </div>
      </div>

      {resultado?.guardados > 0 && (
        <Aviso tipo="exito">
          {resultado.guardados === 1
            ? 'Se guardaron los cambios de 1 usuario.'
            : `Se guardaron los cambios de ${resultado.guardados} usuarios.`}
        </Aviso>
      )}
      {resultado?.errores.length > 0 && (
        <Aviso tipo="error">
          <p>No se guardaron algunos cambios; siguen pendientes:</p>
          <ul className="aviso__lista">
            {resultado.errores.map((texto) => (
              <li key={texto}>{texto}</li>
            ))}
          </ul>
        </Aviso>
      )}
      {contenido}

      <NotaRoles />
    </div>
  );
}
