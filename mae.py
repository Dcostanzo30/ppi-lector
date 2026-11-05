"""Datos públicos de A3 Mercados (marketdata.mae.com.ar), leídos de su API abierta. Solo consulta.

Qué baja:
  - Histórico de cauciones por plazo y moneda desde HISTORIA_DESDE (tasa promedio ponderada, monto concertado, colocador/tomador).
  - Foto diaria de: futuros de dólar (resumen DDF), derivados (DER, para dejar constancia de si hay opciones), forex y volumen por categoría.
Salidas en estudios/mae/: cauciones_historico.csv, ddf_hoy.csv, der_hoy.csv, forex_hoy.csv, volumen_categoria.csv, DIAGNOSTICO.md
"""
import csv, json, time
from datetime import date, datetime, timedelta
from pathlib import Path
import requests

API = "https://api.marketdata.mae.com.ar/api/mercado"
HISTORIA_DESDE = date(2026, 6, 1)
SAL = Path("estudios/mae"); SAL.mkdir(parents=True, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/120 Safari/537.36", "Accept": "application/json",
     "Origin": "https://marketdata.mae.com.ar", "Referer": "https://marketdata.mae.com.ar/"}
DIAG = []


def diag(t):
    print(t, flush=True)
    DIAG.append(t)


def get(ruta, params=None, reintentos=3):
    for i in range(reintentos):
        try:
            r = requests.get(f"{API}/{ruta}", params=params, headers=H, timeout=40)
            if r.status_code == 200:
                return r.json()
            diag(f"  - {ruta}: HTTP {r.status_code}")
            if r.status_code in (400, 404):
                return None
        except Exception as e:
            diag(f"  - {ruta}: {type(e).__name__} {str(e)[:80]}")
        time.sleep(2)
    return None


def escribir(nombre, filas):
    if not filas:
        return
    cols = []
    for f in filas:
        for k in f:
            if k not in cols:
                cols.append(k)
    with open(SAL / nombre, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(filas)


def planas(lista, extra=None):
    out = []
    for x in lista or []:
        if isinstance(x, dict):
            f = {k: v for k, v in x.items() if not isinstance(v, (dict, list))}
            f.update(extra or {})
            out.append(f)
    return out


def cauciones():
    filas, d0 = [], HISTORIA_DESDE
    while d0 <= date.today():
        d1 = min(d0 + timedelta(days=30), date.today())
        q = json.dumps({"fechaDesde": d0.isoformat(), "fechaHasta": d1.isoformat()}, separators=(",", ":"))
        r = get("titulo/historicocauciones", {"oTitulo": q})
        n = 0
        for dia in r or []:
            for det in dia.get("details") or []:
                f = {k: v for k, v in det.items() if not isinstance(v, (dict, list))}
                f["fecha_dia"] = str(dia.get("fecha"))[:10]
                f["volumen_dia"] = dia.get("volumen")
                filas.append(f)
                n += 1
        diag(f"- Cauciones {d0} a {d1}: {n} filas")
        d0 = d1 + timedelta(days=1)
        time.sleep(0.5)
    escribir("cauciones_historico.csv", filas)
    if filas:
        diag(f"  Columnas: {list(filas[0])}")
        diag(f"  Ejemplo: {json.dumps(filas[0], ensure_ascii=False, default=str)[:400]}")


def fotos():
    hoy = datetime.now().strftime("%Y-%m-%d")
    for ruta, arch in (("resumen/DDF", "ddf_hoy.csv"), ("datos/DER", "der_hoy.csv"), ("datos/FOR", "forex_hoy.csv"), ("datos/DDF", "ddf_datos_hoy.csv")):
        r = get(ruta)
        filas = planas(r if isinstance(r, list) else [], {"consulta": hoy})
        diag(f"- {ruta}: {len(filas)} filas" + ("  <- sin operaciones" if r == [] else ""))
        if filas:
            diag(f"  Ejemplo: {json.dumps(filas[0], ensure_ascii=False, default=str)[:300]}")
            escribir(arch, filas)
    cat = []
    for mon in ("ARS", "USD"):
        r = get(f"volumen-categoria/{mon}")
        cat += planas(r if isinstance(r, list) else [], {"consulta": hoy})
    diag(f"- volumen-categoria: {len(cat)} filas; categorías: {sorted({c.get('nombre') for c in cat})}")
    escribir("volumen_categoria.csv", cat)


def main():
    diag(f"# Diagnóstico A3 market data — {datetime.now():%Y-%m-%d %H:%M}\n")
    cauciones()
    fotos()
    (SAL / "DIAGNOSTICO.md").write_text("\n".join(DIAG), encoding="utf-8")


if __name__ == "__main__":
    main()
