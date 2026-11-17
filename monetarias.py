"""Base monetaria y sus factores de explicación (API pública del BCRA, estadísticas v3). Solo consultas.
Escribe estudios/monetarias/variables.csv (catálogo) y estudios/monetarias/series.csv (desde DESDE, incremental)."""
import os, json
from pathlib import Path
import pandas as pd
import requests

SAL = Path("estudios/monetarias"); SAL.mkdir(parents=True, exist_ok=True)
URLS = ["https://api.bcra.gob.ar/estadisticas/v4.0/monetarias", "https://api.bcra.gob.ar/estadisticas/v3.0/monetarias"]
from datetime import date, timedelta
# Desde el 01/11/2025: un año antes de la licitación de noviembre de 2026, para conciliar con finanzas_tesoro.py (Domingo, 17/11/2026).
# Antes eran los últimos 150 días; con eso cada corrida borraba el principio del año.
DESDE = os.environ.get("DESDE") or "2025-11-01"
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
# agregados monetarios (M1, M2, M3 y sus componentes) y tipo de cambio / BADLAR, por id
IDS_FIJOS = {4, 5, 7, 17, 21, 22, 23, 24, 25, 109, 197}
elegidas = pd.concat([elegidas, cat[pd.to_numeric(cat[idc], errors="coerce").isin(IDS_FIJOS)]]).drop_duplicates(subset=[idc])
# Incremental (Domingo, 17/11/2026): lo que ya está guardado no se vuelve a pedir. Por variable se pide desde su último dato
# menos REPASO días (el BCRA corrige los últimos días de los factores), y solo esos días se reemplazan.
REPASO = 10
previo = pd.read_csv(SAL / "series.csv", dtype={"fecha": str}) if (SAL / "series.csv").exists() else pd.DataFrame(columns=["id", "descripcion", "fecha", "valor"])
ultimo = previo.groupby("id")["fecha"].max().to_dict() if len(previo) else {}
filas, pedidos = [], {}
for _, v in elegidas.iterrows():
    vid = int(v[idc])
    desde = DESDE
    if vid in ultimo and isinstance(ultimo[vid], str):
        desde = max(DESDE, (pd.Timestamp(ultimo[vid]) - pd.Timedelta(days=REPASO)).date().isoformat())
    try:
        q = pedir(f"{URL}/{vid}", params={"desde": desde, "hasta": date.today().isoformat(), "limit": 3000})
        nuevas = []
        for x in q.json().get("results", []):
            if isinstance(x, dict) and "detalle" in x:
                for y in x["detalle"]: nuevas.append(dict(id=vid, descripcion=v[desc], fecha=y.get("fecha"), valor=y.get("valor")))
            elif isinstance(x, dict):
                nuevas.append(dict(id=vid, descripcion=v[desc], fecha=x.get("fecha"), valor=x.get("valor")))
        if nuevas:
            filas += nuevas; pedidos[vid] = desde
    except Exception as e:
        print(vid, "falló (se conserva lo guardado)", e, flush=True)
nuevo = pd.DataFrame(filas, columns=["id", "descripcion", "fecha", "valor"])
# se conserva lo previo, salvo los días repasados de las variables que respondieron; y nada anterior a DESDE
quedan = previo[[not (int(i) in pedidos and f >= pedidos[int(i)]) for i, f in zip(previo["id"], previo["fecha"].astype(str))]] if len(previo) else previo
total = pd.concat([quedan, nuevo], ignore_index=True)
total = total[total["fecha"].astype(str) >= DESDE].drop_duplicates(subset=["id", "fecha"], keep="last")
total = total.sort_values(["id", "fecha"], ascending=[True, False])
total.to_csv(SAL / "series.csv", index=False)
print(f"{len(nuevo)} datos pedidos ({len(pedidos)} variables); {len(total)} guardados en total", flush=True)
# FIN monetarias.py
