"""Base monetaria y sus factores de explicación (API pública del BCRA, estadísticas v3). Solo consultas.
Escribe estudios/monetarias/variables.csv (catálogo) y estudios/monetarias/series.csv (desde DESDE)."""
import os, json
from pathlib import Path
import pandas as pd
import requests

SAL = Path("estudios/monetarias"); SAL.mkdir(parents=True, exist_ok=True)
URLS = ["https://api.bcra.gob.ar/estadisticas/v4.0/monetarias", "https://api.bcra.gob.ar/estadisticas/v3.0/monetarias"]
DESDE = os.environ.get("DESDE", "2026-08-01")
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0"
def pedir(url, **kw):
    try:
        return s.get(url, timeout=60, **kw)
    except requests.exceptions.SSLError:
        # el certificado del BCRA suele venir sin la cadena intermedia; son datos públicos de solo lectura
        print("::warning::certificado del BCRA incompleto: se reintenta sin verificar la cadena", flush=True)
        import urllib3; urllib3.disable_warnings()
        return s.get(url, timeout=60, verify=False, **kw)

URL, r = None, None
for u in URLS:
    try:
        r = pedir(u)
        if r.status_code == 200: URL = u; break
        print(f"::warning::{u} respondió {r.status_code}: {r.text[:200]}", flush=True)
    except Exception as e:
        print(f"::warning::{u} falló: {str(e)[:200]}", flush=True)
if not URL: raise SystemExit("::error::no respondió ninguna versión de la API del BCRA")
print("usando", URL, flush=True)
cat = pd.DataFrame(r.json()["results"]); cat.to_csv(SAL / "variables.csv", index=False)
print(len(cat), "variables", flush=True)
print("columnas:", list(cat.columns), flush=True)
desc = cat.columns[[("desc" in c.lower()) for c in cat.columns]][0]
idc = cat.columns[[("idvariable" in c.lower()) for c in cat.columns]][0]
claves = ["base monetaria", "efecto", "circulación", "circulacion", "reservas internacionales", "depósitos en cuenta", "pases", "lefi", "tesoro"]
elegidas = cat[cat[desc].str.lower().str.contains("|".join(claves), na=False)]
filas = []
for _, v in elegidas.iterrows():
    try:
        q = pedir(f"{URL}/{v[idc]}", params={"desde": DESDE, "hasta": "2026-12-31", "limit": 3000})
        for x in q.json().get("results", []):
            if isinstance(x, dict) and "detalle" in x:
                for y in x["detalle"]: filas.append(dict(id=v[idc], descripcion=v[desc], fecha=y.get("fecha"), valor=y.get("valor")))
            elif isinstance(x, dict):
                filas.append(dict(id=v[idc], descripcion=v[desc], fecha=x.get("fecha"), valor=x.get("valor")))
    except Exception as e:
        print(v[idc], "falló", e, flush=True)
pd.DataFrame(filas).to_csv(SAL / "series.csv", index=False)
print(len(filas), "datos de", len(elegidas), "variables", flush=True)
# FIN monetarias.py
