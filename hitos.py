"""Calendario de hitos hasta las elecciones de 2027 (pedido de Domingo, 25/11/2026: "en vez de un año de terror, una lista de pruebas";
"eso sirve para aprovechar mejor oportunidades"). Para cada hito: cómo estaban y cómo quedaron cinco indicadores alrededor de la fecha.
  - Riesgo país (EMBI): ppi--datos/fuentes/riesgo_pais.csv
  - Pendiente de la curva (TIR AL41 − AL30): calculada con dolar_bonos.py sobre mercado_total
  - MEP y brecha CCL–MEP de AL30: mercado_total
  - Depósitos del Tesoro en dólares en el BCRA: estudios/reservas/reservas.csv (semanal)
Hitos: estudios/hitos/hitos.csv (a mano: pagos, FMI, electorales) + las licitaciones del Tesoro de ppi--datos/fuentes/calendario_licitaciones.csv.
Escribe <salida>/hitos.md. Uso: python hitos.py <mercado_total> <fuentes de ppi--datos> <estudios de ppi-lector> <salida>
No es pronóstico ni recomendación: muestra qué pasó alrededor de cada prueba.
"""
import sys, datetime as dt
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from dolar_bonos import leer_bonos, pendiente  # noqa: E402


def main():
    mt, fuentes, est, sal = sys.argv[1:5]
    hoy = dt.date.today().isoformat()
    H = pd.read_csv(Path(est) / "hitos" / "hitos.csv", dtype=str).fillna("")
    cal = Path(fuentes) / "calendario_licitaciones.csv"
    if cal.exists():
        C = pd.read_csv(cal, dtype=str)
        H = pd.concat([H, pd.DataFrame(dict(fecha=C.liquidacion, hito="Licitación del Tesoro del " + pd.to_datetime(C.licitacion).dt.strftime("%d/%m/%Y")
                                            + " (liquida ese día)", tipo="licitación en pesos", fuente="Secretaría de Finanzas", nota=""))])
    # indicadores por día
    rp = pd.read_csv(Path(fuentes) / "riesgo_pais.csv", usecols=[0, 1], names=["f", "v"], header=0).set_index("f").v
    B = leer_bonos(mt); B["MEP"] = B.AL30 / B.AL30D; B["brecha"] = (B.AL30D / B.AL30C - 1) * 100
    P = {f: t["AL41D"] - t["AL30D"] for f, t in pendiente_dict(mt)}
    R = pd.read_csv(Path(est) / "reservas" / "reservas.csv").set_index("fecha").dep_gobierno
    def valor(serie, f, antes=True):
        s = serie.dropna(); s = s[s.index <= f] if antes else s[s.index >= f]
        return (s.index[-1], s.iloc[-1]) if antes and len(s) else ((s.index[0], s.iloc[0]) if len(s) else (None, None))
    n = lambda x, d=0: "s/d" if x is None or pd.isna(x) else f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    md = ["## Calendario de hitos hasta las elecciones de 2027\n",
          "Cada hito es una prueba: se mira cómo estaban los indicadores el día hábil anterior y cómo quedaron después. No es pronóstico.\n",
          "### Próximos\n", "| Fecha | Faltan | Hito | Tipo | Nota |", "|---|---|---|---|---|"]
    fut = H[(H.fecha >= hoy) | (H.fecha == "s/d")].sort_values("fecha")
    for r in fut.head(8).itertuples():
        falta = (dt.date.fromisoformat(r.fecha) - dt.date.today()).days if r.fecha != "s/d" else None
        md.append(f"| {pd.Timestamp(r.fecha):%d/%m/%Y} | {falta} días | {r.hito} | {r.tipo} | {r.nota} |" if r.fecha != "s/d"
                  else f"| a confirmar | | {r.hito} | {r.tipo} | {r.nota} |")
    pas = H[(H.fecha < hoy) & (H.fecha != "s/d") & (H.fecha >= (dt.date.today() - dt.timedelta(days=45)).isoformat())].sort_values("fecha")
    if len(pas):
        md += ["", "### Los últimos 45 días: antes y después", "| Fecha | Hito | Riesgo país | Pendiente AL41−AL30 | MEP | Brecha CCL–MEP | Depósitos Tesoro US$ |",
               "|---|---|---|---|---|---|---|"]
        for r in pas.itertuples():
            ant = lambda s: valor(s, (pd.Timestamp(r.fecha) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"))[1]
            des = lambda s: valor(s, r.fecha, antes=False)[1]
            par = lambda s, d=0, m=1: f"{n(ant(s) * m if ant(s) is not None else None, d)} → {n(des(s) * m if des(s) is not None else None, d)}"
            Ps = pd.Series(P)
            md.append(f"| {pd.Timestamp(r.fecha):%d/%m/%Y} | {r.hito} | {par(rp)} | {par(Ps, 0, 100)} pb | {par(B.MEP)} | {par(B.brecha, 1)}% | {par(R, 1)} mil M |")
    Path(sal).mkdir(parents=True, exist_ok=True)
    Path(sal, "hitos.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"hitos: {len(fut)} próximos, {len(pas)} recientes")


def pendiente_dict(mt):
    """Reusa el cálculo de TIR de dolar_bonos (las filas de la tabla) para tener la pendiente por fecha."""
    import json
    rs = sorted(Path(mt).glob("*_rendimientos.csv"))
    if not rs: return []
    from dolar_bonos import tir
    R = pd.read_csv(rs[-1]); fl = {}
    for r in R.itertuples():
        if r.ticker in ("AL30D", "AL41D"):
            fl[r.ticker] = [(dt.date.fromisoformat(x["cuttingDate"][:10]), (x.get("rent") or 0) + (x.get("amortization") or 0)) for x in json.loads(r.calculadora)["flows"]]
    out = []
    for f in sorted(Path(mt).glob("20??-??-??.csv"))[-60:]:
        try:
            d = pd.read_csv(f); d = d[d.plazo == "A-24HS"].set_index("ticker").price
        except Exception:
            continue
        liq = dt.date.fromisoformat(f.stem) + dt.timedelta(days=1)
        t = {k: tir(fl.get(k, []), d.get(k), liq) for k in ("AL30D", "AL41D")}
        if not any(pd.isna(v) for v in t.values()): out.append((f.stem, t))
    return out


if __name__ == "__main__":
    main()
# FIN hitos.py
