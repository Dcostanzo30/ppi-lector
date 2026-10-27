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
    variantes = [CUERPO, {**CUERPO, "T1": True}, {**CUERPO, "T0": True, "T1": True}, {"excludeZeroPxAndQty": False, "T2": True, "T1": False, "T0": False},
                 {**CUERPO, "Content-Type": "application/json"}]
    for ep, nombre in PANELES.items():
        lista = None
        for i, cuerpo in enumerate(variantes):
            try:
                r = requests.post(BASE + ep, json=cuerpo, headers=H, timeout=60)
                d = r.json() if r.content else {}
                l_ = d.get("data", d) if isinstance(d, dict) else d
                print(ep, "variante", i, r.status_code, len(r.content), (len(l_) if isinstance(l_, list) else r.text[:160]), flush=True)
                if isinstance(l_, list) and l_:
                    lista = l_; break
            except Exception as e:
                print(ep, "variante", i, "error", str(e)[:160], flush=True)
        crudo[ep] = lista or []
    (sal / f"{fecha}_byma.json").write_text(json.dumps(crudo, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
# FIN byma_control.py
