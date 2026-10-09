import random
import sys
import time
from pathlib import Path

import requests

API = "http://127.0.0.1:8000"

codigo = sys.argv[1].strip().upper() if len(sys.argv) > 1 else input("Código de activación: ").strip().upper()
archivo_clave = Path(f".clave_{codigo}.txt")

# La API key se guarda en un archivo, igual que el Arduino la guardaría en su memoria
if archivo_clave.exists():
    clave = archivo_clave.read_text().strip()
    print("Equipo ya activado, usando la clave guardada.")
else:
    r = requests.post(f"{API}/equipo/activar", json={"codigo_activacion": codigo}, timeout=5)
    if r.status_code != 200:
        print("No se pudo activar:", r.json().get("detail", r.text))
        sys.exit(1)
    clave = r.json()["api_key"]
    archivo_clave.write_text(clave)
    print("✅ Equipo activado.")

humedad = 40.0
ciclos_bomba = 0  # cuántos envíos más queda encendida la bomba

while True:
    bomba = ciclos_bomba > 0
    if bomba:
        humedad = min(100.0, humedad + 7)
        ciclos_bomba -= 1
    else:
        humedad = max(0.0, humedad - random.uniform(0, 1.5))

    try:
        r = requests.post(
            f"{API}/equipo/lecturas",
            headers={"X-API-Key": clave},
            json={"humedad": round(humedad, 1), "deposito_bajo": False, "bomba_activa": bomba},
            timeout=5,
        )
        r.raise_for_status()
        resp = r.json()
        if resp["riego_manual"]:
            ciclos_bomba = 3
            print("🚿 Riego manual recibido desde la app")
        elif humedad < resp["umbral_humedad"] and ciclos_bomba == 0:
            ciclos_bomba = 3
            print("🤖 Riego automático: humedad bajo el umbral")
    except requests.RequestException as error:
        print("Error de conexión:", error)

    print(f"humedad={humedad:.1f}%  bomba={'ENCENDIDA' if bomba else 'apagada'}")
    time.sleep(5)