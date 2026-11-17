"""Seguimiento de la base monetaria: cuánto se expande o se contrae y por qué (factores de explicación del BCRA), con las
licitaciones del Tesoro y sus vencimientos al lado.

Fuentes (no consulta afuera):
- estudios/monetarias/series.csv (monetarias.py, API del BCRA): base monetaria (id 15) y factores de explicación (ids 46 a 59),
  en millones de pesos, diarios. El BCRA los publica con algunos días de atraso.
- ppi--datos/fuentes/calendario_licitaciones.csv: fechas de licitación y liquidación del Tesoro (cronograma oficial).
- ppi--datos/fuentes/licitaciones_tesoro.csv: resultados oficiales de cada licitación (valor efectivo adjudicado, VNO en circulación).
- estudios/letras/instrumentos.csv: pago final de cada LECAP por 100 nominales (calculadora de PPI).

Lectura (a validar con varias licitaciones): una licitación con colocación neta (el Tesoro toma más pesos de los que paga por
vencimientos) debería contraer la base el día de la liquidación. No está probado en qué factor del BCRA aparece: en la liquidación
del 30/10/2026 el factor "Tesoro" dio casi cero y el movimiento grande cayó en "Otros". Por eso se muestran los dos. Vencimientos: VNO en circulación del último comunicado
de cada instrumento por su pago final (LECAP); para los demás se informa solo el VNO.
Escribe estudios/base_monetaria/BASE.md (se rehace entero en cada corrida).
Uso: python base_monetaria.py [--datos ../ppi--datos]"""
import argparse
from datetime import date
from pathlib import Path
import pandas as pd

SAL = Path("estudios/base_monetaria")
GRUPOS = {  # factores de explicación del BCRA (ids de la API), agrupados para leer de un vistazo
    "Compra de divisas": [47, 48],              # al sector privado y al Tesoro
    "Tesoro": [49, 50, 51],                     # adelantos transitorios, utilidades, resto de operaciones (licitaciones, depósitos)
    "Pases y letras del BCRA": [52, 53, 56, 58],  # pases, LELIQ, LEBAC, letras fiscales de liquidez
    "Otros": [54, 55, 57, 59],                  # redescuentos, intereses, cuasimonedas, otras
}
BIL = 1e6   # millones -> billones


def n(x, d=2):
    return "s/d" if x is None or pd.isna(x) else f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fd(f):
    return pd.Timestamp(f).strftime("%d/%m/%Y")


def tabla(cab, filas):
    return ["| " + " | ".join(cab) + " |", "|" + "---|" * len(cab)] + ["| " + " | ".join(f) + " |" for f in filas]


def main(datos):
    s = pd.read_csv("estudios/monetarias/series.csv")
    s["fecha"] = pd.to_datetime(s.fecha.str[:10]); s["valor"] = pd.to_numeric(s.valor, errors="coerce")
    p = s.pivot_table(index="fecha", columns="id", values="valor", aggfunc="last").sort_index()
    base = p[15].dropna() if 15 in p else pd.Series(dtype=float)
    fac = p[[c for c in range(46, 60) if c in p]].dropna(how="all")
    G = pd.DataFrame({g: fac[[i for i in ids if i in fac]].sum(axis=1, min_count=1) for g, ids in GRUPOS.items()})
    G["Total"] = fac[46] if 46 in fac else G.sum(axis=1)
    L = [f"# Base monetaria: expansión y contracción", "",
         f"Rehecho el {date.today():%d/%m/%Y}. Montos en billones de pesos. Fuente: factores de explicación de la base monetaria del BCRA "
         "(API de estadísticas), que se publican con algunos días de atraso.", ""]

    if len(base):
        u = base.index[-1]; b = base.iloc[-1]
        fm = base[base.index < u.replace(day=1)]
        h30 = base[base.index <= u - pd.Timedelta(days=30)]
        L += [f"**Base monetaria al {fd(u)}: $ {n(b / BIL)} billones.**", ""]
        filas = []
        if len(fm): filas.append([f"Desde fin de mes ({fd(fm.index[-1])})", n((b - fm.iloc[-1]) / BIL), n((b / fm.iloc[-1] - 1) * 100, 1) + "%"])
        if len(h30): filas.append([f"Últimos 30 días (desde {fd(h30.index[-1])})", n((b - h30.iloc[-1]) / BIL), n((b / h30.iloc[-1] - 1) * 100, 1) + "%"])
        filas.append([f"Desde el primer dato ({fd(base.index[0])})", n((b - base.iloc[0]) / BIL), n((b / base.iloc[0] - 1) * 100, 1) + "%"])
        L += tabla(["Período", "Variación", "%"], filas) + [""]

    if len(G):
        M = G.resample("ME").sum(min_count=1)
        L += [f"## Factores por mes (último dato de factores: {fd(G.index[-1])})", "",
              "Positivo = expande la base (el BCRA entrega pesos); negativo = la contrae.", ""]
        L += tabla(["Mes"] + list(G.columns), [[f"{m:%m/%Y}"] + [n(v / BIL) for v in r] for m, r in M.iterrows()]) + [""]
        L += ["## Últimos 10 días con factores", ""]
        L += tabla(["Fecha"] + list(G.columns), [[fd(f)] + [n(v / BIL) for v in r] for f, r in G.tail(10).iterrows()]) + [""]

    dat = Path(datos) / "fuentes" if datos else None
    if dat and (dat / "licitaciones_tesoro.csv").exists():
        lic = pd.read_csv(dat / "licitaciones_tesoro.csv", parse_dates=["licitacion", "liquidacion", "vencimiento"])
        tot = lic[lic.ticker == "TOTAL"]
        L += ["## Licitaciones del Tesoro y la base el día de la liquidación", "",
              "Factores del BCRA el día de la liquidación. Todavía no está probado en cuál aparece la licitación: se valida a medida "
              "que se juntan licitaciones con sus vencimientos.", ""]
        filas = []
        for r in tot.itertuples():
            v = lambda g: G[g].get(r.liquidacion) if len(G) else None
            t, o, x = v("Tesoro"), v("Otros"), v("Total")
            sd = lambda z: n(z / BIL) if z is not None and pd.notna(z) else "s/d"
            filas.append([fd(r.licitacion), fd(r.liquidacion), n(r.ve_adjudicado_pesos / BIL), sd(t), sd(o), sd(x)])
        L += tabla(["Licitación", "Liquidación", "Adjudicado (VE)", "Tesoro", "Otros", "Total del día"], filas)
        L += ["", "s/d: el BCRA todavía no publicó los factores de ese día.", ""]

        ins = lic[lic.ticker != "TOTAL"].sort_values("licitacion").groupby("ticker").last().reset_index().sort_values("vencimiento")
        pago = {}
        if Path("estudios/letras/instrumentos.csv").exists():
            pago = dict(pd.read_csv("estudios/letras/instrumentos.csv")[["ticker", "pago_final"]].values)
        L += ["## Vencimientos conocidos", "",
              "VNO en circulación según el último comunicado oficial de cada instrumento. El pago se estima solo para las LECAP "
              "(pago final de la calculadora de PPI); los demás dependen de la TAMAR, del CER o del dólar al vencimiento.", ""]
        filas = []
        for r in ins.itertuples():
            pg = r.vno_circulacion * pago[r.ticker] / 100 if r.ticker in pago else None
            mon = "USD" if r.moneda_vn == "USD" else "$"
            filas.append([fd(r.vencimiento), r.ticker, r.tipo.upper(), f"{mon} {n(r.vno_circulacion / BIL if mon == '$' else r.vno_circulacion / 1e3)}"
                          + (" billones" if mon == "$" else " mil millones"), f"$ {n(pg / BIL)} billones" if pg else "—",
                          f"comunicado del {fd(r.licitacion)}"])
        if pago:   # LECAP con pago conocido que no figuran en ningún comunicado cargado: vencimiento sin VNO
            ins_l = pd.read_csv("estudios/letras/instrumentos.csv", parse_dates=["vencimiento"])
            for r in ins_l[(~ins_l.ticker.isin(ins.ticker)) & (ins_l.vencimiento >= pd.Timestamp(date.today()))].itertuples():
                filas.append([fd(r.vencimiento), r.ticker, "LECAP", "s/d", f"{n(r.pago_final)} por cada 100 VNO",
                              "falta el VNO: no hay comunicado cargado"])
            filas.sort(key=lambda f: pd.Timestamp(f[0].split("/")[2] + "-" + f[0].split("/")[1] + "-" + f[0].split("/")[0]))
        L += tabla(["Vence", "Instrumento", "Tipo", "VNO en circulación", "Pago estimado", "Dato"], filas) + [""]

    if dat and (dat / "calendario_licitaciones.csv").exists():
        cal = pd.read_csv(dat / "calendario_licitaciones.csv", parse_dates=["licitacion", "llamado", "liquidacion"])
        prox = cal[cal.licitacion >= pd.Timestamp(date.today())].head(3)
        if len(prox):
            L += ["## Próximas licitaciones (cronograma oficial)", ""]
            L += tabla(["Llamado", "Licitación", "Liquidación"], [[fd(r.llamado), fd(r.licitacion), fd(r.liquidacion)] for r in prox.itertuples()]) + [""]

    SAL.mkdir(parents=True, exist_ok=True)
    (SAL / "BASE.md").write_text("\n".join(L), encoding="utf-8")
    print(f"base_monetaria: base al {fd(base.index[-1]) if len(base) else 's/d'}, factores al {fd(G.index[-1]) if len(G) else 's/d'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--datos"); a = ap.parse_args()
    main(a.datos)
# FIN base_monetaria.py
