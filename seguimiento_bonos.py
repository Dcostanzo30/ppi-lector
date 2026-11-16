"""Seguimiento nocturno de soberanos largos en dólares: precio en D y en pesos, MEP implícito, TIR, paridad, monto y riesgo país.
No consulta a PPI: usa la foto diaria del mercado total (mercado_total/FECHA.csv) y los flujos de la calculadora
guardados en mercado_total/2026-10-23_rendimientos.csv. La primera vez rellena desde el 8/7/2026 con estudios/bonos/historial_ppi.csv.
Escribe estudios/bonos/seguimiento.csv (historia) y estudios/bonos/SEGUIMIENTO.md (tabla para leer en el teléfono).
Convención verificada: el precio de BYMA incluye el interés corrido (precio sucio); la TIR se calcula sobre ese precio.
Uso: python seguimiento_bonos.py [AAAA-MM-DD]   (por defecto, todas las fotos del mercado total que falten)
"""
import csv, glob, json, os, sys, urllib.request
from datetime import date, timedelta
from pathlib import Path

BONOS = ["AE38", "GD38", "AL41", "GD41", "AL35", "GD35", "AL30", "GD30"]
FOCO = ["AE38", "AL41", "GD38"]
FLUJOS_DE = "mercado_total/2026-10-23_rendimientos.csv"
SAL = Path("estudios/bonos")
CAMPOS = ["fecha", "bono", "precio_d", "precio_pesos", "mep_implicito", "var_d_pct", "tir_pct", "paridad_pct", "monto_d_usd", "monto_pesos", "riesgo_pais", "brent"]
csv.field_size_limit(10**9)


def flujos():
    out = {}
    with open(FLUJOS_DE, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["ticker"] in BONOS and r["calculadora"]:
                j = json.loads(r["calculadora"])
                out[r["ticker"]] = [(date.fromisoformat(f["cuttingDate"][:10]), float(f["total"]), float(f["rent"]),
                                     float(f["amortization"]), float(f["residualValue"])) for f in j["flows"]]
    return out


def liquidacion(d):
    d += timedelta(days=1)
    while d.weekday() >= 5: d += timedelta(days=1)
    return d


def calcular(fl, precio, fecha):
    """TIR (precio sucio), paridad = precio / (residual + corrido). Flujos posteriores a la liquidación."""
    s = liquidacion(fecha)
    fut = [f for f in fl if f[0] > s]
    if not fut or not precio: return None, None
    prox = fut[0]
    ant = date(prox[0].year if prox[0].month == 7 else prox[0].year - 1, 1 if prox[0].month == 7 else 7, 9)
    corrido = prox[2] * (s - ant).days / max((prox[0] - ant).days, 1)
    residual = prox[4] * 100
    def vp(y): return sum(c / (1 + y) ** ((d - s).days / 365) for d, c, *_ in fut)
    lo, hi = -0.5, 2.0
    for _ in range(100):
        m = (lo + hi) / 2
        if vp(m) > precio: lo = m
        else: hi = m
    return round(m * 100, 2), round(precio / (residual + corrido) * 100, 2)


def riesgo_pais():
    import fuentes_datos
    rp = fuentes_datos.serie("riesgo_pais")                         # capa de fuentes de ppi--datos (15/11/2026)
    if rp: return rp
    try:
        req = urllib.request.Request("https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais", headers={"User-Agent": "Mozilla/5.0"})
        datos = json.load(urllib.request.urlopen(req, timeout=30))
        return {str(x["fecha"])[:10]: x["valor"] for x in datos}
    except Exception as e:
        print("Riesgo país no disponible:", str(e)[:120], flush=True)
        return {}


def brent():
    """Cierre diario del Brent: de la capa de fuentes de ppi--datos; si no está, futuro BZ=F de Yahoo Finance. Si falla, vacío."""
    import fuentes_datos
    b = fuentes_datos.serie("brent")
    if b: return {d: round(v, 2) for d, v in b.items() if d >= "2026-07-01"}
    try:
        import yfinance as yf
        h = yf.download("BZ=F", start="2026-07-01", progress=False, auto_adjust=False)["Close"]
        h = h.iloc[:, 0] if hasattr(h, "columns") else h
        return {i.strftime("%Y-%m-%d"): round(float(v), 2) for i, v in h.dropna().items()}
    except Exception as e:
        print("Brent no disponible:", str(e)[:120], flush=True)
        return {}


BONOS_VR = ["AL29D", "GD29D", "AL30D", "GD30D", "AL35D", "GD35D", "AE38D", "GD38D", "AL41D", "GD41D", "GD46D"]


def paridad_vr():
    """Soberanos en dólar MEP (16/11): precio / valor residual, sin intereses en el denominador. Valor residual = residualValue
    del primer flujo posterior a la liquidación (calculadora de PPI guardada), por 100. Historia en estudios/bonos/paridad_vr.csv."""
    vr = {}
    with open(FLUJOS_DE, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["ticker"] in BONOS_VR and r["calculadora"]:
                vr[r["ticker"]] = [(date.fromisoformat(f["cuttingDate"][:10]), float(f["residualValue"]) * 100) for f in json.loads(r["calculadora"])["flows"]]
    filas, ant = [], {}
    for f in sorted(glob.glob("mercado_total/????-??-??.csv")):
        d = Path(f).stem; p = precios_foto(f)
        for b in BONOS_VR:
            pr = p.get(b, (0, 0))[0]
            if not pr or b not in vr: continue
            s = liquidacion(date.fromisoformat(d))
            fut = [x for x in vr[b] if x[0] > s]
            res = fut[0][1] if fut else None
            var = round((pr / ant[b] - 1) * 100, 2) if ant.get(b) else ""
            filas.append({"fecha": d, "bono": b, "precio": pr, "var_pct": var, "valor_residual": round(res, 4) if res else "",
                          "precio_sobre_vr_pct": round(pr / res * 100, 2) if res else ""})
            ant[b] = pr
    with open(SAL / "paridad_vr.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, ["fecha", "bono", "precio", "var_pct", "valor_residual", "precio_sobre_vr_pct"]); w.writeheader(); w.writerows(filas)
    if not filas: return []
    u = max(x["fecha"] for x in filas)
    l = ["## Soberanos en dólar MEP: precio / valor residual", "", f"Rueda **{u}** (cierre A-24HS). Valor residual cada 100 de nominal, según los flujos de la calculadora de PPI. "
         "El precio de BYMA incluye el interés corrido desde el último cupón: el cociente queda apenas por encima de la paridad limpia.", "",
         "| Bono | Precio | Var. | Valor residual | Precio / valor residual |", "|---|---|---|---|---|"]
    for b in BONOS_VR:
        r = next((x for x in filas if x["fecha"] == u and x["bono"] == b), None)
        if r: l.append(f"| {b} | {ar(r['precio'])} | {ar(r['var_pct'])}% | {ar(r['valor_residual'], 2)} | {ar(r['precio_sobre_vr_pct'], 1)}% |")
    return l + [""]


def precios_foto(f):
    p = {}
    with open(f, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["plazo"] == "A-24HS" and r["tipo"] == "BONOS": p[r["ticker"]] = (float(r["price"] or 0), float(r["volume"] or 0))
    return p


def main():
    fl = flujos(); rp = riesgo_pais(); br = brent()
    SAL.mkdir(parents=True, exist_ok=True)
    hist_f = SAL / "seguimiento.csv"
    filas = {}
    if hist_f.exists():
        with open(hist_f, encoding="utf-8") as fh:
            for r in csv.DictReader(fh): filas[(r["fecha"], r["bono"])] = r
    dias = {}  # fecha -> {ticker: (precio, monto)}
    if not filas and Path(SAL / "historial_ppi.csv").exists():
        with open(SAL / "historial_ppi.csv", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["fecha"] >= "2026-07-08": dias.setdefault(r["fecha"], {})[r["ticker"]] = (float(r["cierre"] or 0), float(r["monto"] or 0))
    pedido = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None
    for f in sorted(glob.glob("mercado_total/????-??-??.csv")):
        d = Path(f).stem
        if pedido and d != pedido: continue
        dias[d] = precios_foto(f)
    for d in sorted(dias):
        p = dias[d]
        for b in BONOS:
            pd_, md = p.get(b + "D", (0, 0)); pp, mp = p.get(b, (0, 0))
            if not pd_: continue
            tir, par = calcular(fl[b], pd_, date.fromisoformat(d)) if b in fl else (None, None)
            ant = max([(dd, float(r["precio_d"] or 0)) for (dd, bb), r in filas.items() if bb == b and dd < d] or [("", 0)])
            filas[(d, b)] = {"fecha": d, "bono": b, "precio_d": pd_, "precio_pesos": pp, "mep_implicito": round(pp / pd_, 2) if pp else "",
                             "var_d_pct": round((pd_ / ant[1] - 1) * 100, 2) if ant[1] and not (ant[0] < "2026-07-09" <= d) else "",
                             "tir_pct": tir, "paridad_pct": par, "monto_d_usd": round(md), "monto_pesos": round(mp),
                             "riesgo_pais": rp.get(d, filas.get((d, b), {}).get("riesgo_pais", ""))}
    for r in filas.values():
        if not r.get("riesgo_pais") and r["fecha"] in rp: r["riesgo_pais"] = rp[r["fecha"]]
        if r["fecha"] in br: r["brent"] = br[r["fecha"]]
    with open(hist_f, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, CAMPOS); w.writeheader()
        for k in sorted(filas): w.writerow({c: filas[k].get(c, "") for c in CAMPOS})
    escribir_md(filas, paridad_vr())
    print(f"Seguimiento: {len(filas)} filas, última fecha {max(k[0] for k in filas) if filas else '-'}", flush=True)


def ar(x, dec=2):
    try: return f"{float(x):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError): return "—"


def brecha(filas, d, a, b):
    try: return ar(float(filas[(d, a)]["tir_pct"]) - float(filas[(d, b)]["tir_pct"]))
    except (KeyError, TypeError, ValueError): return "—"


def escribir_md(filas, vr_lineas=()):
    fechas = sorted({k[0] for k in filas})
    if not fechas: return
    u = fechas[-1]
    l = [f"# Seguimiento de soberanos largos en dólares", "", f"Última rueda: **{u}**. Riesgo país: **{ar(filas.get((u, BONOS[0]), {}).get('riesgo_pais'), 0)}**. Brent: **US$ {ar(filas.get((u, BONOS[0]), {}).get('brent'))}**.", "",
         *vr_lineas, "## Largos en foco", "",
         "Precio en D en dólares (incluye interés corrido). TIR sobre ese precio. Paridad = precio / (residual + corrido).", "",
         "| Bono | Precio D | Var. día | TIR | Paridad | MEP implícito | Monto D (US$) |", "|---|---|---|---|---|---|---|"]
    for b in BONOS:
        r = filas.get((u, b))
        if r: l.append(f"| {'**'+b+'**' if b in FOCO else b} | {ar(r['precio_d'])} | {ar(r['var_d_pct'])}% | {ar(r['tir_pct'])}% | {ar(r['paridad_pct'], 1)}% | {ar(r['mep_implicito'])} | {ar(r['monto_d_usd'], 0)} |")
    l += ["", "## Últimas 15 ruedas: TIR de los tres en foco y riesgo país", "", "| Fecha | Riesgo país | Brent | " + " | ".join(f"TIR {b}" for b in FOCO) + " | " + " | ".join(f"Precio {b}D" for b in FOCO) + " | Ley local AE38−GD38 | Ley local AL41−GD41 |",
          "|---" * (5 + 2 * len(FOCO)) + "|"]
    for d in fechas[-15:][::-1]:
        rr = [filas.get((d, b), {}) for b in FOCO]
        l.append(f"| {d} | {ar(filas.get((d, BONOS[0]), {}).get('riesgo_pais'), 0)} | {ar(filas.get((d, BONOS[0]), {}).get('brent'))} | " + " | ".join(f"{ar(r.get('tir_pct'))}%" for r in rr) + " | " + " | ".join(ar(r.get('precio_d')) for r in rr) + f" | {brecha(filas, d, 'AE38', 'GD38')} | {brecha(filas, d, 'AL41', 'GD41')} |")
    l += ["", "Ley local = TIR del bono de ley argentina menos la de su par de ley Nueva York (puntos). Si se abre sin que suba el riesgo país, el mercado cobra más el riesgo de canje o reperfilamiento de ley local.",
          "", "Fuentes: precios y montos de PPI (cierre A-24HS); flujos de la calculadora de PPI; riesgo país de argentinadatos.com (JP Morgan EMBI); Brent de Yahoo Finance (futuro BZ=F).", ""]
    (SAL / "SEGUIMIENTO.md").write_text("\n".join(l), encoding="utf-8")


if __name__ == "__main__":
    main()
# FIN seguimiento_bonos.py
