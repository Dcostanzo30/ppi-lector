"""Control cruzado: monto operado por especie según BYMA (datos abiertos de BYMADATA) contra la foto del mercado total de PPI.
Solo consulta páginas públicas de BYMA. Escribe estudios/control_byma/FECHA_byma.json (crudo) y FECHA_cruce.md.
Uso: python byma_control.py FECHA_PPI
"""
import json, sys, csv
from pathlib import Path
import requests

BASE = "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free/"
PANELES = {"leading-equity": "acciones panel líder", "general-equity": "acciones panel general", "cedears": "CEDEARs",
           "public-bonds": "bonos", "negociable-obligations": "ONs", "short-term-government-bonds": "letras", "options": "opciones"}
CUERPO = {"excludeZeroPxAndQty": True, "T2": True, "T1": False, "T0": False}
H = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0", "Origin": "https://open.bymadata.com.ar", "Referer": "https://open.bymadata.com.ar/"}


def main():
    fecha = sys.argv[1]
    sal = Path("estudios/control_byma"); sal.mkdir(parents=True, exist_ok=True)
    crudo, filas = {}, []
    for ep, nombre in PANELES.items():
        try:
            r = requests.post(BASE + ep, json=CUERPO, headers=H, timeout=60)
            print(ep, r.status_code, len(r.content), flush=True)
            d = r.json()
            lista = d.get("data", d) if isinstance(d, dict) else d
            crudo[ep] = lista
            if lista and isinstance(lista, list): print("  ejemplo:", json.dumps(lista[0], ensure_ascii=False)[:600], flush=True)
        except Exception as e:
            print(ep, "error", str(e)[:200], flush=True); crudo[ep] = {"error": str(e)[:300]}
    (sal / f"{fecha}_byma.json").write_text(json.dumps(crudo, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
# FIN byma_control.py
