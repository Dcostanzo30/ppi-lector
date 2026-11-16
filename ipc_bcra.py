"""IPC (inflación mensual del INDEC) desde la API del BCRA, serie 27, para ppi--datos/fuentes/ipc.csv.
Misma forma de consultar que monetarias.py (v4 con respaldo v3; certificado incompleto del BCRA tolerado).
Columnas: fecha (último día del mes, como la publica el BCRA), valor (variación % mensual), fuente, estado, consultado.
Uso: python ipc_bcra.py SALIDA.csv [DESDE]"""
import sys
from datetime import datetime
import requests

SAL, DESDE = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "2022-12-01")
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0"


def pedir(url, **kw):
    try:
        return s.get(url, timeout=60, **kw)
    except requests.exceptions.SSLError:
        import urllib3; urllib3.disable_warnings()
        return s.get(url, timeout=60, verify=False, **kw)


filas = None
for base in ("https://api.bcra.gob.ar/estadisticas/v4.0/monetarias", "https://api.bcra.gob.ar/estadisticas/v3.0/monetarias"):
    r = pedir(f"{base}/27", params={"desde": DESDE, "hasta": datetime.now().strftime("%Y-%m-%d"), "limit": 3000})
    if r.status_code != 200:
        print(f"::warning::{base} respondió {r.status_code}"); continue
    res = r.json().get("results") or []
    datos = []
    for x in res:
        datos += x.get("detalle", [x]) if isinstance(x, dict) else []
    filas = sorted({(d["fecha"][:10], float(d["valor"])) for d in datos if d.get("fecha") and d.get("valor") is not None})
    if filas: break
if not filas: raise SystemExit("::error::no se pudo leer la serie 27 del BCRA")
ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
with open(SAL, "w", encoding="utf-8") as fh:
    fh.write("fecha,valor,fuente,estado,consultado\n")
    for f, v in filas: fh.write(f"{f},{v},BCRA serie 27 (INDEC),definitivo,{ahora}\n")
print(f"IPC: {len(filas)} meses, {filas[0][0]} a {filas[-1][0]}; último {filas[-1][1]}%")
# FIN ipc_bcra.py
