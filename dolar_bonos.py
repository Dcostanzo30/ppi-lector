"""Dólar implícito en bonos: seguimiento diario (pedido de Domingo, 24/11/2026: "conviene hacer ese seguimiento sobre todo en este
mes, que es de turbulencia importante").
MEP y CCL implícitos de AL30 y GD30 (cierre de mercado_total, plazo 24 hs) contra el mayorista, el oficial y el blue
(ppi--datos/fuentes), y una lectura de cada día según cómo se movieron el bono en pesos y el bono en dólares:
  - desfasaje: el bono en dólares cae bastante más que en pesos (el MEP sube por la venta en el segmento dólar);
  - demanda de dólares: el MEP sube con el bono en dólares quieto o en alza (sube el precio en pesos: compran dólares);
  - corrección: el MEP baja;  - estable: se mueve menos de 0,5%.
Escribe <salida>/dolar_bonos.md. Uso: python dolar_bonos.py <carpeta mercado_total> <carpeta fuentes de ppi--datos> <salida>
"""
import sys
from pathlib import Path
import pandas as pd

UMBRAL = 0.5   # % de movimiento del MEP para que cuente


def leer_bonos(mt):
    filas = []
    for f in sorted(Path(mt).glob("20??-??-??.csv"))[-25:]:
        try:
            d = pd.read_csv(f)
        except Exception:
            continue
        d = d[(d.plazo == "A-24HS") & d.ticker.isin(["AL30", "AL30D", "AL30C", "GD30", "GD30D", "GD30C"])]
        p = d.set_index("ticker").price.to_dict()
        if all(k in p and p[k] for k in ("AL30", "AL30D", "AL30C")):
            filas.append(dict(fecha=f.stem, **p))
    return pd.DataFrame(filas).set_index("fecha")


def serie(fuentes, nombre):
    try:
        s = pd.read_csv(Path(fuentes) / f"{nombre}.csv", usecols=[0, 1], names=["fecha", "valor"], header=0)
        return s.set_index("fecha").valor.astype(float)
    except Exception:
        return pd.Series(dtype=float)


def lectura(dp, dd, dm):
    if pd.isna(dm): return ""
    if dm > UMBRAL:
        if dd < -1 and dp - dd > UMBRAL: return "desfasaje: el bono en dólares cae más que en pesos"
        return "demanda de dólares: el MEP sube sin caída fuerte del bono en dólares"
    if dm < -UMBRAL: return "corrección: baja el MEP"
    return "estable"


def tir(flujos, precio, liq):
    cf = [(d, c) for d, c in flujos if d > liq]
    if not cf or not precio: return float("nan")
    f = lambda y: sum(c / (1 + y) ** ((d - liq).days / 365) for d, c in cf) - precio
    lo, hi = -0.5, 3.0
    for _ in range(80):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if f(m) > 0 else (lo, m)
    return m * 100


def pendiente(mt, n):
    """TIR de AL30D, AL41D, GD30D y GD41D al cierre de cada día (flujos del último *_rendimientos.csv) y pendiente 2030–2041."""
    import json, datetime as dt
    rs = sorted(Path(mt).glob("*_rendimientos.csv"))
    if not rs: return ["## Pendiente de la curva\n\nSin flujos de los bonos: s/d."]
    R = pd.read_csv(rs[-1]); fl = {}
    for r in R.itertuples():
        if r.ticker in ("AL30D", "AL41D", "GD30D", "GD41D"):
            try:
                fl[r.ticker] = [(dt.date.fromisoformat(x["cuttingDate"][:10]), (x.get("rent") or 0) + (x.get("amortization") or 0))
                                for x in json.loads(r.calculadora)["flows"]]
            except Exception:
                pass
    filas = []
    for f in sorted(Path(mt).glob("20??-??-??.csv"))[-n:]:
        try:
            d = pd.read_csv(f); d = d[d.plazo == "A-24HS"].set_index("ticker").price
        except Exception:
            continue
        liq = dt.date.fromisoformat(f.stem) + dt.timedelta(days=1)
        t = {k: tir(fl.get(k, []), d.get(k), liq) for k in ("AL30D", "AL41D", "GD30D", "GD41D")}
        if not all(pd.isna(v) for v in t.values()): filas.append((f.stem, t))   # feriados: la foto existe pero sin precios
    pc = lambda x: "s/d" if pd.isna(x) else f"{x:.1f}%".replace(".", ",")
    pb = lambda x: "s/d" if pd.isna(x) else f"{x * 100:+.0f} pb"
    if not filas: return []
    md = [f"## Pendiente de la curva en dólares del {pd.Timestamp(filas[0][0]):%d/%m/%Y} al {pd.Timestamp(filas[-1][0]):%d/%m/%Y}\n",
          "| Fecha | TIR AL30 | TIR AL41 | AL41 − AL30 | TIR GD30 | TIR GD41 | GD41 − GD30 |", "|---|---|---|---|---|---|---|"]
    for f, t in filas:
        md.append(f"| {pd.Timestamp(f):%d/%m/%Y} | {pc(t['AL30D'])} | {pc(t['AL41D'])} | {pb(t['AL41D'] - t['AL30D'])} | "
                  f"{pc(t['GD30D'])} | {pc(t['GD41D'])} | {pb(t['GD41D'] - t['GD30D'])} |")
    md.append("\nPendiente negativa (el 2030 rinde más que el 2041) = el mercado pone el riesgo en los próximos años (período electoral y "
              f"vencimientos 2027–2028); cuanto más negativa, más concentrado. TIR propia con los flujos de {rs[-1].stem[:10]} y el cierre de cada día.")
    return md


def main():
    mt, fuentes, sal = sys.argv[1:4]
    B = leer_bonos(mt)
    if B.empty:
        Path(sal, "dolar_bonos.md").write_text("## Dólar implícito en bonos\n\nSin datos de mercado_total: s/d.\n", encoding="utf-8"); return
    B["MEP"] = B.AL30 / B.AL30D; B["CCL"] = B.AL30 / B.AL30C
    if "GD30D" in B: B["MEP_GD"] = B.GD30 / B.GD30D
    may, ofi, blue = serie(fuentes, "mayorista"), serie(fuentes, "oficial"), serie(fuentes, "blue")
    B["may"] = [may.get(f) for f in B.index]; B["blue"] = [blue.get(f) for f in B.index]; B["ofi"] = [ofi.get(f) for f in B.index]
    B["dp"] = B.AL30.pct_change() * 100; B["dd"] = B.AL30D.pct_change() * 100; B["dm"] = B.MEP.pct_change() * 100
    n = lambda x, d=0: "s/d" if pd.isna(x) else f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    pc = lambda x: "s/d" if pd.isna(x) else f"{x:+.1f}%".replace(".", ",")
    f0 = pd.Timestamp(B.index[-10] if len(B) >= 10 else B.index[0]); f1 = pd.Timestamp(B.index[-1])
    md = [f"## Dólar implícito en bonos (AL30, cierre 24 hs) del {f0:%d/%m/%Y} al {f1:%d/%m/%Y}\n",
          "| Fecha | MEP | CCL | CCL/MEP | MEP/mayorista | MEP/blue | AL30 $ | AL30D US$ | Lectura |",
          "|---|---|---|---|---|---|---|---|---|"]
    for f, r in B.tail(10).iterrows():
        md.append(f"| {pd.Timestamp(f):%d/%m/%Y} | {n(r.MEP)} | {n(r.CCL)} | {pc((r.CCL / r.MEP - 1) * 100)} | "
                  f"{pc((r.MEP / r.may - 1) * 100) if r.may else 's/d'} | {pc((r.MEP / r.blue - 1) * 100) if r.blue else 's/d'} | "
                  f"{n(r.AL30)} ({pc(r.dp)}) | {n(r.AL30D, 2)} ({pc(r.dd)}) | {lectura(r.dp, r.dd, r.dm)} |")
    u = B.iloc[-1]
    md.append("")
    md.append(f"Último: MEP {n(u.MEP)}, CCL {n(u.CCL)}, mayorista {n(u.may)}, oficial {n(u.ofi)}, blue {n(u.blue)}. "
              + (f"MEP–GD30 {n(u.MEP_GD)}. " if "MEP_GD" in B and not pd.isna(u.get('MEP_GD')) else ""))
    if u.blue and not pd.isna(u.blue):
        dif = (u.MEP / u.blue - 1) * 100
        md.append(f"Ventana de arbitraje MEP–blue: {pc(dif)}. "
                  + ("Con una diferencia tan chica no conviene arbitrar (costos y riesgo del blue): una corrección del MEP, si llega, "
                     "no tiene por qué ser inmediata." if abs(dif) < 3 else "Con 3% o más la diferencia empieza a pagar el arbitraje entre los dos mercados: la corrección puede acelerarse."))
    umbral_txt = str(UMBRAL).replace(".", ",")
    md.append("\n*Lecturas*: desfasaje = el bono en dólares cae más de 1% y bastante más que en pesos; demanda de dólares = el MEP sube con el "
              f"bono en dólares quieto o en alza; corrección = el MEP baja más de {umbral_txt}%. Fuentes: mercado_total (PPI) y fuentes/ del sistema "
              "(mayorista del BCRA, oficial y blue de argentinadatos; el valor del día puede ser provisorio).")
    md += [""] + pendiente(mt, 10)
    Path(sal).mkdir(parents=True, exist_ok=True)
    Path(sal, "dolar_bonos.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"dolar_bonos: {len(B)} ruedas, último {f1:%d/%m/%Y} MEP {u.MEP:.1f}")


if __name__ == "__main__":
    main()
# FIN dolar_bonos.py
