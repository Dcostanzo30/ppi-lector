"""Tasas en pesos del BCRA (API de estadísticas) para ppi--datos/fuentes/tasa_*.csv. Mismo formato que la capa de fuentes:
fecha, valor (% nominal anual), fuente, estado, consultado, otras. Una fila por día hábil desde 2023.
Con el esquema de agregados de 2026 el BCRA no fija tasa de política (sus pases activos y pasivos están en cero): la referencia
la dan el mercado de dinero y los bancos. Ids del catálogo estudios/monetarias/variables.csv.
Se pide la serie completa en cada corrida (el BCRA publica con uno o dos días de atraso y a veces corrige); las filas que ya
estaban y no vinieron se conservan.
Uso: python tasas_bcra.py CARPETA_FUENTES"""
import csv, sys
from datetime import date, datetime
from pathlib import Path
import requests

TASAS = {"tasa_pases_1d": 150,   # pases entre terceros a 1 día (rueda REPO): tasa de mercado de referencia
         "tasa_baibar": 11,      # préstamos entre bancos privados (call)
         "tasa_tamar": 44,       # TAMAR bancos privados (depósitos de $1.000 millones o más, 30 a 35 días)
         "tasa_badlar": 7,       # BADLAR bancos privados (más de $1 millón, 30 a 35 días)
         "tasa_tm20": 8,         # TM20 bancos privados ($20 millones o más)
         "tasa_pf_30d": 12}      # plazo fijo a 30 días, total del sistema
DESDE = "2023-01-01"
COLS = ["fecha", "valor", "fuente", "estado", "consultado", "otras"]
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0"


def pedir(url, **kw):
    try:
        return s.get(url, timeout=60, **kw)
    except requests.exceptions.SSLError:
        import urllib3; urllib3.disable_warnings()      # el certificado del BCRA suele venir sin la cadena intermedia
        return s.get(url, timeout=60, verify=False, **kw)


def serie(var):
    for base in ("https://api.bcra.gob.ar/estadisticas/v4.0/monetarias", "https://api.bcra.gob.ar/estadisticas/v3.0/monetarias"):
        try:
            r = pedir(f"{base}/{var}", params={"desde": DESDE, "hasta": date.today().isoformat(), "limit": 3000})
        except Exception as e:
            print(f"::warning::{base}/{var}: {e}"); continue
        if r.status_code != 200:
            print(f"::warning::{base}/{var} respondió {r.status_code}"); continue
        datos = []
        for x in r.json().get("results") or []:
            datos += x.get("detalle", [x]) if isinstance(x, dict) else []
        out = {d["fecha"][:10]: float(d["valor"]) for d in datos if d.get("fecha") and d.get("valor") is not None}
        out = {f: v for f, v in out.items() if date.fromisoformat(f).weekday() < 5 and 0 <= v <= 500}
        if out: return out
    return {}


def main(carpeta):
    carpeta = Path(carpeta); ahora = datetime.now().strftime("%Y-%m-%d %H:%M"); fallas = 0
    for dato, var in TASAS.items():
        p = carpeta / f"{dato}.csv"
        fil = {r["fecha"]: r for r in csv.DictReader(open(p, encoding="utf-8"))} if p.exists() else {}
        nuevo = serie(var)
        if not nuevo:
            print(f"::warning::{dato} (variable {var}): sin datos del BCRA; queda como estaba"); fallas += 1; continue
        cambios = 0
        for f, v in nuevo.items():
            prev = fil.get(f)
            if prev and prev.get("valor") not in ("", None) and float(prev["valor"]) == v: continue
            fil[f] = dict(fecha=f, valor=f"{v:g}", fuente=f"bcra (variable {var})", estado="definitivo", consultado=ahora, otras="")
            cambios += 1
        with open(p, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, COLS, extrasaction="ignore"); w.writeheader()
            for f in sorted(fil): w.writerow(fil[f])
        u = max(fil)
        print(f"{dato}: {len(fil)} días, {cambios} cambios; último {u} = {fil[u]['valor']}")
    if fallas == len(TASAS): raise SystemExit("::error::el BCRA no respondió ninguna tasa")


if __name__ == "__main__":
    main(sys.argv[1])
# FIN tasas_bcra.py
