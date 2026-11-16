"""Exploración (16/11): qué da la ficha técnica de BYMADATA (datos abiertos) por especie: emisor, tipo, moneda, emisión,
vencimiento, tasa, amortización, ley... Prueba varias rutas y guarda las respuestas crudas en explorar.json para ver
cuál sirve antes de armar el lector definitivo. Solo lectura; no toca PPI.
Uso: python -m fuentes.byma_fichas.explorar --solo AL30,M30A7,NZC7D
"""
import argparse, json, time
from pathlib import Path
import requests

AQUI = Path(__file__).parent
BASE = "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free/"
H = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0", "Origin": "https://open.bymadata.com.ar",
     "Referer": "https://open.bymadata.com.ar/"}
RUTAS = ["bnown/fichatecnica/especies/general", "bnown/fichatecnica/especies/cronograma", "bnown/fichatecnica/especies/emisor",
         "bnown/fichatecnica/especies/prospecto", "bnown/especies/fichatecnica", "bnown/fichatecnica/especies",
         "bnown/seriesHistoricas/fichatecnica", "bnown/fichatecnica/especies/flujo"]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--solo", required=True); a = ap.parse_args()
    out = {}
    try:                                                                # primero, una ruta que ya usa mercado_total
        r = requests.post(BASE + "public-bonds", json={"excludeZeroPxAndQty": True, "T2": True, "T1": False, "T0": False}, headers=H, timeout=20)
        print("control public-bonds:", r.status_code, len(r.text), r.text[:300], flush=True)
        out["control public-bonds"] = {"status": r.status_code, "texto": r.text[:2000]}
    except Exception as e:
        print("control public-bonds: sin conexión:", repr(e)[:800], flush=True)
        (AQUI / "explorar.json").write_text(json.dumps({"control": repr(e)[:800]}, ensure_ascii=False), encoding="utf-8")
        return
    for t in a.solo.split(","):
        for ruta in RUTAS:
            for metodo, cuerpo in (("POST", {"symbol": t, "Content-Type": "application/json"}), ("POST", {"symbol": t}), ("GET", None)):
                clave = f"{t} {metodo} {ruta} {json.dumps(cuerpo) if cuerpo else ''}"
                try:
                    r = requests.post(BASE + ruta, json=cuerpo, headers=H, timeout=15) if metodo == "POST" else \
                        requests.get(BASE + ruta, params={"symbol": t}, headers=H, timeout=15)
                    out[clave] = {"status": r.status_code, "texto": r.text[:4000]}
                    print(clave, r.status_code, len(r.text), flush=True)
                    if r.status_code == 200 and len(r.text) > 40: break
                except Exception as e:
                    out[clave] = {"error": str(e)[:300]}; print(clave, "error", repr(e)[-300:], flush=True)
                time.sleep(0.5)
    (AQUI / "explorar.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
# FIN explorar.py
