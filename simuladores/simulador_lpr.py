"""
Simulador de cámara LPR en portería (Historia H15).

- Envía lecturas de placa al endpoint POST /api/lpr/lecturas con cabecera X-Device-Key.
- Permite probar todos los escenarios de aceptación:
  1. Vehículo con mensualidad activa -> crea ticket, guarda foto y responde abrir=True.
  2. Vehículo sin mensualidad activa -> responde abrir=False (pasa a lector QR).
  3. Placa no registrada -> responde abrir=False (pasa a lector QR).
  4. Lectura ilegible / confianza baja -> responde abrir=False (pasa a lector QR).
"""

import argparse
import base64
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Pixel PNG mínimo en base64 para simular captura fotográfica real de la cámara
FOTO_BASE64_EJEMPLO = (
    'data:image/png;base64,'
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
)


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


def enviar_lectura_lpr(
    base_url: str,
    device_key: str,
    camara_id: str,
    placa: str | None,
    confianza: float | None,
    foto: str | None,
):
    endpoint = f"{base_url.rstrip('/')}/api/lpr/lecturas"
    payload = {
        'camara_id': camara_id,
        'placa': placa,
        'confianza': confianza,
        'foto': foto,
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'X-Device-Key': device_key,
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            status = resp.status
            cuerpo = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as err:
        status = err.code
        detalle = err.read().decode('utf-8', errors='ignore')
        try:
            cuerpo = json.loads(detalle)
        except json.JSONDecodeError:
            cuerpo = {'detail': detalle}
    except Exception as exc:
        status = 0
        cuerpo = {'detail': str(exc)}

    print('\n--- Resultado Cámara LPR ---')
    print(f'HTTP Status : {status}')
    print(f'Placa leída : {placa or "(sin lectura)"} | Confianza: {confianza}')
    if status == 200:
        abrir = cuerpo.get('abrir')
        motivo = cuerpo.get('motivo')
        ticket_id = cuerpo.get('ticket_id')
        accion = 'TALANQUERA ABIERTA (ingreso automático)' if abrir else 'NO ABRE -> Pasar a lector QR'
        print(f'Decisión    : {accion}')
        print(f'Motivo      : {motivo}')
        print(f'Ticket ID   : {ticket_id}')
    else:
        print(f'Error API   : {cuerpo}')
    print('----------------------------\n')


def menu_interactivo(base_url: str, device_key: str, camara_id: str):
    print('=== Simulador de Cámara LPR (H15) ===')
    print(f'Endpoint: {base_url.rstrip("/")}/api/lpr/lecturas | Cámara: {camara_id}\n')

    while True:
        print('Selecciona una prueba de captura:')
        print('  1. Leer placa personalizada (ej. ABC123, XYZ12A, DEF456)')
        print('  2. Simular lectura borrosa / sin placa (debe responder abrir=false)')
        print('  3. Simular lectura con confianza baja 0.45 (debe responder abrir=false)')
        print('  0. Salir')
        opcion = input('Opción: ').strip()

        if opcion == '0':
            break
        elif opcion == '1':
            placa = input('Ingresa la placa detectada (ej. ABC123): ').strip().upper()
            conf_txt = input('Confianza (0.0 a 1.0, Enter para 0.95): ').strip()
            confianza = float(conf_txt) if conf_txt else 0.95
            enviar_lectura_lpr(base_url, device_key, camara_id, placa, confianza, FOTO_BASE64_EJEMPLO)
        elif opcion == '2':
            enviar_lectura_lpr(base_url, device_key, camara_id, None, 0.0, FOTO_BASE64_EJEMPLO)
        elif opcion == '3':
            placa = input('Placa con baja nitidez (Enter para ABC123): ').strip().upper() or 'ABC123'
            enviar_lectura_lpr(base_url, device_key, camara_id, placa, 0.45, FOTO_BASE64_EJEMPLO)
        else:
            print('Opción inválida.\n')


def main():
    parser = argparse.ArgumentParser(description='Simulador de cámara LPR (H15)')
    parser.add_argument('--url', default='http://127.0.0.1:8000', help='URL base de la API')
    parser.add_argument('--camara', default='CAM-ENTRADA', help='Identificador de la cámara LPR')
    parser.add_argument('--placa', help='Ejecución directa de una placa sin menú interactivo')
    parser.add_argument('--confianza', type=float, default=0.95, help='Confianza de lectura (0 a 1)')
    args = parser.parse_args()

    device_key = cargar_env('IOT_DEVICE_KEY')
    if not device_key:
        raise SystemExit('ERROR: No se encontró IOT_DEVICE_KEY en el archivo .env')

    if args.placa is not None:
        placa_limpia = args.placa.strip().upper() or None
        enviar_lectura_lpr(
            args.url, device_key, args.camara, placa_limpia, args.confianza, FOTO_BASE64_EJEMPLO
        )
    else:
        menu_interactivo(args.url, device_key, args.camara)


if __name__ == '__main__':
    main()