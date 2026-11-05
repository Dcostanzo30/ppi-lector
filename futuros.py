"""Futuros de Matba Rofex (dólar y el resto del panel) leídos desde la API de PPI.
Solo consulta: no opera ni toca la cuenta. Usa las mismas credenciales (PPI_API_KEY / PPI_API_SECRET) que los demás lectores.

Qué hace:
  1. Averigua qué tipos de instrumento y mercados ofrece PPI y arma el listado de futuros (DLR y todo lo que sea derivado).
  2. Para cada futuro baja el precio actual y, si PPI lo ofrece, la historia diaria desde HISTORIA_DESDE.
  3. Con los contratos de dólar simples (DLR/NOV26, DLR/DIC26...) arma la curva y calcula la devaluación implícita contra el mayorista.
  4. Deja un DIAGNOSTICO.md con lo que encontró y lo que falló, para ajustar el código en la primera corrida si hace falta.

Salidas en estudios/futuros/: instrumentos.csv, precios_hoy.csv, historico.csv, curva_dolar.csv, CURVA.md, DIAGNOSTICO.md
"""
import csv, json, os, re, string, sys, time
from datetime import date, datetime, timedelta
from pathlib import Path

SAL = Path("estudios/futuros"); SAL.mkdir(parents=True, exist_ok=True)
HISTORIA_DESDE = date(2026, 6, 1)
MESES = {"ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12}
PLAZOS = ("INMEDIATA", "A-24HS")
MAX_FUTUROS = 600          # tope de seguridad de contratos a consultar
PAUSA = 0.15               # segundos entre consultas, para no pasar el límite de PPI
DIAG = []


def diag(t):
    print(t, flush=True)
    DIAG.append(t)


def nombre(t):
    if isinstance(t, dict):
        for k in ("value", "code", "name", "description", "id"):
            if t.get(k):
                return str(t[k])
    return str(t)


def ingresar():
    from ppi_client.ppi import PPI
    p = PPI(sandbox=False)
    p.account.login_api(os.environ["PPI_API_KEY"].strip(), os.environ["PPI_API_SECRET"].strip())
    return p


def buscar(ppi, tk, nm, mercado, tipo):
    """search_instrument tolerante: PPI exige ticker y nombre no vacíos desde el 26/10/2026; probamos variantes."""
    time.sleep(PAUSA)
    for a, b in ((tk, nm), (tk, tk), (tk, "")):
        try:
            r = ppi.marketdata.search_instrument(a, b, mercado, tipo)
            if isinstance(r, list):
                return r
        except Exception:
            continue
    return []


def es_futuro(reg, tipos_fut):
    tk = str(reg.get("ticker", "")).upper()
    tp = str(reg.get("type", "")).upper()
    return tp in tipos_fut or tk.startswith(("DLR", "DLR/"))


def listar(ppi):
    tipos = [nombre(t) for t in (ppi.configuration.get_instrument_types() or [])]
    mercados = [nombre(m) for m in (ppi.configuration.get_markets() or [])]
    diag(f"- Tipos de instrumento que ofrece PPI: {tipos}")
    diag(f"- Mercados que ofrece PPI: {mercados}")
    tipos_fut = {t.upper() for t in tipos if re.search(r"FUTUR|DERIV|ROFEX|MATBA", t, re.I)}
    diag(f"- Tipos considerados futuros: {sorted(tipos_fut) or 'ninguno por nombre; se filtra por el prefijo DLR'}")
    mercados_prueba = [""] + [m for m in mercados if re.search(r"ROFEX|MATBA|A3|DERIV|FUT", m, re.I)]
    tipos_prueba = [""] + sorted(tipos_fut)
    semillas = ["DLR"] + list(string.ascii_uppercase) + list(string.digits)
    hallados = {}
    for mer in mercados_prueba:
        for tp in tipos_prueba:
            n0 = len(hallados)
            for s in semillas:
                for r in buscar(ppi, s, "", mer, tp):
                    if isinstance(r, dict) and r.get("ticker") and es_futuro(r, tipos_fut):
                        hallados.setdefault((str(r["ticker"]).strip().upper(), str(r.get("type") or tp)), r)
                if s == "DLR" and len(hallados) > n0:
                    # con DLR ya encontramos los de dólar; seguimos con el resto del panel por letra
                    pass
            diag(f"- Búsqueda mercado='{mer}' tipo='{tp}': {len(hallados) - n0} futuros nuevos")
    return hallados, tipos_fut


def precio_hoy(ppi, tk, tipo):
    for pl in PLAZOS:
        time.sleep(PAUSA)
        try:
            c = ppi.marketdata.current(tk, tipo, pl)
            if c:
                return pl, c
        except Exception:
            continue
    return None, None


def historia(ppi, tk, tipo, plazo):
    out = []
    d0, d1 = HISTORIA_DESDE, date.today()
    for pl in ([plazo] if plazo else []) + [p for p in PLAZOS if p != plazo]:
        time.sleep(PAUSA)
        try:
            r = ppi.marketdata.search(tk, tipo, pl, d0.isoformat(), d1.isoformat()) or []
        except Exception:
            continue
        if r:
            for x in r:
                out.append(dict(ticker=tk, tipo=tipo, plazo=pl, fecha=str(x.get("date", ""))[:10], precio=x.get("price"),
                                apertura=x.get("openingPrice"), maximo=x.get("max"), minimo=x.get("min"), volumen=x.get("volume")))
            break
    return out


def ultimo_dia_habil(a, m):
    d = date(a + (m == 12), (m % 12) + 1, 1) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def vencimiento(tk):
    """DLR/NOV26 -> último día hábil de nov-2026 (los DLR vencen el último día hábil del mes; feriados no considerados)."""
    m = re.fullmatch(r"DLR/([A-Z]{3})(\d{2})", tk.upper())
    if not m or m.group(1) not in MESES:
        return None
    return ultimo_dia_habil(2000 + int(m.group(2)), MESES[m.group(1)])


def mayorista():
    """Último mayorista de referencia (BCRA, serie 5) del repo, para medir la devaluación implícita."""
    ruta = Path("estudios/monetarias/series.csv")
    if not ruta.exists():
        return None, None
    ult = None
    with open(ruta, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("id") == "5" and (ult is None or r["fecha"] > ult[0]):
                ult = (r["fecha"], float(r["valor"]))
    return ult if ult else (None, None)


def curva(precios):
    fm, spot = mayorista()
    filas = []
    for p in precios:
        v = vencimiento(p["ticker"])
        px = p.get("precio")
        if not v or not px:
            continue
        dias = (v - date.today()).days
        if dias <= 0:
            continue
        fila = dict(ticker=p["ticker"], vencimiento=v.isoformat(), dias=dias, precio=px, plazo=p.get("plazo"))
        if spot:
            imp = px / spot - 1
            fila.update(mayorista=spot, fecha_mayorista=fm, devaluacion_implicita_pct=round(imp * 100, 2),
                        anualizada_pct=round(((1 + imp) ** (365 / dias) - 1) * 100, 1))
        filas.append(fila)
    filas.sort(key=lambda f: f["vencimiento"])
    return filas


def csv_dic(ruta, filas):
    if not filas:
        return
    cols = []
    for f in filas:
        for k in f:
            if k not in cols:
                cols.append(k)
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(filas)


def main():
    diag(f"# Diagnóstico futuros — {datetime.now():%Y-%m-%d %H:%M}\n")
    try:
        ppi = ingresar()
        diag("Ingreso a PPI correcto.\n")
    except Exception as e:
        diag(f"No se pudo ingresar a PPI: {type(e).__name__} {str(e)[:200]}")
        (SAL / "DIAGNOSTICO.md").write_text("\n".join(DIAG), encoding="utf-8")
        return
    try:
        hallados, tipos_fut = listar(ppi)
    except Exception as e:
        diag(f"Falló el listado: {type(e).__name__} {str(e)[:300]}")
        hallados = {}
    diag(f"\n**Futuros encontrados: {len(hallados)}**\n")
    csv_dic(SAL / "instrumentos.csv", [dict(ticker=k[0], tipo=k[1], registro=json.dumps(r, ensure_ascii=False, default=str))
                                       for k, r in sorted(hallados.items())])
    # primero los DLR simples, luego el resto
    orden = sorted(hallados, key=lambda k: (0 if vencimiento(k[0]) else 1, k[0]))[:MAX_FUTUROS]
    hoy, hist, sin_precio = [], [], []
    for tk, tipo in orden:
        pl, c = precio_hoy(ppi, tk, tipo)
        if not c:
            sin_precio.append(tk)
            continue
        hoy.append(dict(ticker=tk, tipo=tipo, plazo=pl, fecha=str(c.get("date", ""))[:19], precio=c.get("price"),
                        volumen=c.get("volume"), apertura=c.get("openingPrice"), maximo=c.get("max"), minimo=c.get("min"),
                        ajuste=c.get("settlementPrice") or c.get("adjustment"), interes_abierto=c.get("openInterest"),
                        registro=json.dumps(c, ensure_ascii=False, default=str)))
        if vencimiento(tk):          # historia solo de los DLR simples (la de los demás, en una segunda etapa)
            hist += historia(ppi, tk, tipo, pl)
    diag(f"- Con precio actual: {len(hoy)}; sin precio: {len(sin_precio)} {sin_precio[:15]}")
    diag(f"- Filas de historia diaria (DLR simples): {len(hist)}")
    csv_dic(SAL / "precios_hoy.csv", hoy)
    csv_dic(SAL / "historico.csv", hist)
    cur = curva(hoy)
    csv_dic(SAL / "curva_dolar.csv", cur)
    md = [f"# Curva de dólar futuro — {date.today():%d/%m/%Y}", ""]
    if cur:
        md += ["| Contrato | Vence | Días | Precio | Devaluación implícita | Anualizada |", "|---|---|---|---|---|---|"]
        for f in cur:
            md.append(f"| {f['ticker']} | {f['vencimiento']} | {f['dias']} | {f['precio']} | {f.get('devaluacion_implicita_pct', '')}% | {f.get('anualizada_pct', '')}% |")
        fm, spot = mayorista()
        md += ["", f"Mayorista de referencia usado: {spot} ({fm}). Devaluación implícita = precio del futuro / mayorista − 1. "
                   "Los vencimientos se suponen el último día hábil del mes (sin ajustar feriados)."]
    else:
        md.append("No se pudo armar la curva (ver DIAGNOSTICO.md).")
    (SAL / "CURVA.md").write_text("\n".join(md), encoding="utf-8")
    (SAL / "DIAGNOSTICO.md").write_text("\n".join(DIAG), encoding="utf-8")
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as fh:
            fh.write("\n".join(DIAG) + "\n\n" + "\n".join(md) + "\n")


if __name__ == "__main__":
    main()
