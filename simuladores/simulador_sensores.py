"""
Simulador de sensores ultrasónicos ESP32 (Historia H14).

- Simula N bahías enviando cambios de ocupación y latidos periódicos.
- Permite apagar/encender un sensor en tiempo real para probar la alerta de
  desconexión (> 90 segundos sin pulso en GET /api/iot/sensores).
- Envía exactamente el contrato JSON definido en CLAUDE.md con cabecera X-Device-Key.
"""

import argparse
import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SENSORES_POR_DEFECTO = [
    'ESP32-C01', 'ESP32-C02', 'ESP32-C03', 'ESP32-C04',
    'ESP32-C05', 'ESP32-C06', 'ESP32-C07', 'ESP32-C08',
    'ESP32-M01', 'ESP32-M02', 'ESP32-M03', 'ESP32-M04',
]


def cargar_env(clave: str, defecto: str = '') -> str:
    if os.getenv(clave):
        return os.environ[clave]
    ruta_env = Path(__file__).resolve().parent.parent / '.env'
    if ruta_env.exists():
        for linea in ruta_env.read_text(encoding='utf-8').splitlines():
            linea = linea.strip()
            if linea and not linea.startswith('#') and '=' in linea:
                k, v = linea.split('=', 1)
                if k.strip() == clave:
                    return v.strip()
    return defecto


class SimuladorSensores:
    def __init__(self, base_url: str, device_key: str, sensores: list[str], intervalo_latido: int):
        self.endpoint = f"{base_url.rstrip('/')}/api/iot/sensores/estado"
        self.device_key = device_key
        self.intervalo_latido = intervalo_latido
        self.lock = threading.Lock()
        self.activo = True

        # Estado interno por sensor: encendido (envía datos) y ocupado (True/False)
        self.estado = {
            uid: {'encendido': True, 'ocupado': False}
            for uid in sensores
        }

    def _enviar_json(self, payload: dict) -> tuple[int, dict]:
        datos = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            self.endpoint,
            data=datos,
            headers={
                'Content-Type': 'application/json',
                'X-Device-Key': self.device_key,
            },
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                cuerpo = json.loads(resp.read().decode('utf-8'))
                return resp.status, cuerpo
        except urllib.error.HTTPError as err:
            detalle = err.read().decode('utf-8', errors='ignore')
            try:
                return err.code, json.loads(detalle)
            except json.JSONDecodeError:
                return err.code, {'detail': detalle}
        except Exception as exc:
            return 0, {'detail': str(exc)}

    def enviar_latido(self, uid: str):
        payload = {
            'device_uid': uid,
            'latido': True,
            'ts': datetime.now(timezone.utc).isoformat(),
        }
        status, resp = self._enviar_json(payload)
        if status == 200:
            print(f"[LATIDO OK] {uid} -> bahía {resp.get('codigo')} ({resp.get('estado')})")
        else:
            print(f"[ERROR LATIDO {status}] {uid} -> {resp}")

    def enviar_cambio_ocupacion(self, uid: str, ocupado: bool):
        distancia_cm = random.randint(18, 65) if ocupado else random.randint(180, 260)
        payload = {
            'device_uid': uid,
            'ocupado': ocupado,
            'distancia_cm': distancia_cm,
            'ts': datetime.now(timezone.utc).isoformat(),
        }
        status, resp = self._enviar_json(payload)
        estado_txt = 'OCUPADA' if ocupado else 'LIBRE'
        if status == 200:
            with self.lock:
                self.estado[uid]['ocupado'] = ocupado
            print(
                f"[EVENTO OK] {uid} -> {estado_txt} ({distancia_cm} cm) | "
                f"bahía {resp.get('codigo')}"
            )
        else:
            print(f"[ERROR EVENTO {status}] {uid} -> {resp}")

    def ciclo_automatico(self):
        ultimo_latido = 0.0
        while self.activo:
            ahora = time.time()

            # 1. Enviar latidos periódicos de todos los sensores encendidos
            if ahora - ultimo_latido >= self.intervalo_latido:
                with self.lock:
                    encendidos = [u for u, info in self.estado.items() if info['encendido']]
                for uid in encendidos:
                    if not self.activo:
                        break
                    self.enviar_latido(uid)
                ultimo_latido = time.time()

            # 2. Simular entrada/salida aleatoria en una bahía encendida
            time.sleep(6)
            if not self.activo:
                break
            with self.lock:
                encendidos = [u for u, info in self.estado.items() if info['encendido']]
                if encendidos:
                    elegido = random.choice(encendidos)
                    nuevo_estado = not self.estado[elegido]['ocupado']
                else:
                    elegido = None
                    nuevo_estado = False
            if elegido:
                self.enviar_cambio_ocupacion(elegido, nuevo_estado)

    def interfaz_comandos(self):
        print('\n=== Simulador Ultrasónico ESP32 (H14) Iniciado ===')
        print(f'Endpoint: {self.endpoint}')
        print(f'Sensores activos ({len(self.estado)}): {", ".join(self.estado.keys())}')
        print('\nComandos disponibles en consola:')
        print('  estado                -> Ver qué sensores están encendidos/apagados')
        print('  apagar <UID>          -> Apaga un sensor para probar alerta (>90s sin pulso)')
        print('  encender <UID>        -> Vuelve a encender el sensor')
        print('  ocupar <UID>          -> Fuerza evento de vehículo estacionado')
        print('  liberar <UID>         -> Fuerza evento de bahía libre')
        print('  salir                 -> Detiene el simulador\n')

        while self.activo:
            try:
                entrada = input('> ').strip()
            except (EOFError, KeyboardInterrupt):
                self.activo = False
                break

            if not entrada:
                continue
            partes = entrada.split()
            cmd = partes[0].lower()

            if cmd == 'salir':
                self.activo = False
                print('Deteniendo simulador...')
                break
            elif cmd == 'estado':
                with self.lock:
                    for uid, info in self.estado.items():
                        on_off = 'ENCENDIDO' if info['encendido'] else 'APAGADO (sin latidos)'
                        ocu = 'ocupada' if info['ocupado'] else 'libre'
                        print(f'  - {uid}: {on_off} | bahía={ocu}')
            elif cmd in {'apagar', 'encender', 'ocupar', 'liberar'} and len(partes) == 2:
                uid = partes[1].upper()
                if uid not in self.estado:
                    print(f'Sensor desconocido: {uid}')
                    continue
                if cmd == 'apagar':
                    with self.lock:
                        self.estado[uid]['encendido'] = False
                    print(f'[APAGADO] {uid} dejó de enviar latidos. En >90s aparecerá desconectado.')
                elif cmd == 'encender':
                    with self.lock:
                        self.estado[uid]['encendido'] = True
                    print(f'[ENCENDIDO] {uid} reactivado.')
                    self.enviar_latido(uid)
                elif cmd == 'ocupar':
                    self.enviar_cambio_ocupacion(uid, True)
                elif cmd == 'liberar':
                    self.enviar_cambio_ocupacion(uid, False)
            else:
                print('Comando no reconocido. Usa: estado | apagar <UID> | encender <UID> | ocupar <UID> | liberar <UID> | salir')


def main():
    parser = argparse.ArgumentParser(description='Simulador de sensores ultrasónicos ESP32 (H14)')
    parser.add_argument('--url', default='http://127.0.0.1:8000', help='URL base de la API')
    parser.add_argument('--bahias', type=int, default=12, help='Número de bahías a simular (1 a 12)')
    parser.add_argument('--latido', type=int, default=20, help='Segundos entre ciclos de latido')
    args = parser.parse_args()

    device_key = cargar_env('IOT_DEVICE_KEY')
    if not device_key:
        raise SystemExit('ERROR: No se encontró IOT_DEVICE_KEY en el archivo .env')

    cantidad = max(1, min(args.bahias, len(SENSORES_POR_DEFECTO)))
    sensores = SENSORES_POR_DEFECTO[:cantidad]

    sim = SimuladorSensores(args.url, device_key, sensores, args.latido)
    hilo = threading.Thread(target=sim.ciclo_automatico, daemon=True)
    hilo.start()
    sim.interfaz_comandos()


if __name__ == '__main__':
    main()