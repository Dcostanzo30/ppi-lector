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
    md.append("\n*Lecturas*: desfasaje = el bono en dólares cae más de 1% y bastante más que en pesos; demanda de dólares = el MEP sube con el "
              f"bono en dólares quieto o en alza; corrección = el MEP baja más de {str(UMBRAL).replace(".", ",")}%. Fuentes: mercado_total (PPI) y fuentes/ del sistema "
              "(mayorista del BCRA, oficial y blue de argentinadatos; el valor del día puede ser provisorio).")
    Path(sal).mkdir(parents=True, exist_ok=True)
    Path(sal, "dolar_bonos.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"dolar_bonos: {len(B)} ruedas, último {f1:%d/%m/%Y} MEP {u.MEP:.1f}")


if __name__ == "__main__":
    main()
# FIN dolar_bonos.py
