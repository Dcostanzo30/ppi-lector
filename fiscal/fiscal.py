"""Fiscal (pedido de Domingo, 24/11/2026): recaudación (ARCA) y gasto base caja del Sector Público Nacional, para integrar
al seguimiento de la base monetaria. Fuente: API de series de tiempo de datos.gob.ar (Ministerio de Economía), mensual.
  - Recaudación: dataset "Recursos tributarios totales y por tributo", mensual (total y por impuesto).
  - Gasto: IMIG (Informe Mensual de Ingresos y Gastos del SPN no financiero), mensual: jubilaciones y pensiones
    contributivas, prestaciones sociales, remuneraciones, gasto primario.
Salidas en estudios/fiscal/: series.csv (id, descripcion, fecha, valor; millones de pesos) y FISCAL.md (recaudación con
variación interanual nominal y real, y la estimación del aguinaldo público de diciembre con su método y su control).
Las series se buscan por descripción en cada corrida (los ids de datos.gob.ar cambian poco, pero no se fijan a mano).
Uso: python fiscal/fiscal.py [--ipc ruta/a/ipc.csv]
"""
import argparse, re, time
from pathlib import Path
import pandas as pd
import requests

API = "https://apis.datos.gob.ar/series/api"
SAL = Path(__file__).resolve().parent.parent / "estudios" / "fiscal"
DESDE = "2023-01-01"
# (búsqueda, regex sobre la descripción, dataset esperado, nombre corto)
BUSCAR = [
    ("Recursos tributarios totales y por tributo Mensual", r"de los Recursos tributarios totales y por tributo\. Mensual", "Recursos tributarios", None),
    ("IMIG jubilaciones y pensiones contributivas", r"^IMIG\. Gastos primarios\. Gastos corrientes primarios\. Prestaciones sociales\. Jubilaciones y pensiones contributivas$", "IMIG", "jubilaciones"),
    ("IMIG prestaciones sociales", r"^IMIG\. Gastos primarios\. Gastos corrientes primarios\. Prestaciones sociales$", "IMIG", "prestaciones"),
    ("IMIG remuneraciones", r"^IMIG\. Gastos primarios\. Gastos corrientes primarios\. Gastos de funcionamiento y otros\. (Salarios|Remuneraciones)$|^IMIG\. Gastos primarios\. Gastos corrientes primarios\. (Gastos de funcionamiento\. )?(Salarios|Remuneraciones)$", "IMIG", "remuneraciones"),
    ("IMIG gastos primarios", r"^IMIG\. Gastos primarios$", "IMIG", "gasto_primario"),
    ("Exportaciones de manufacturas de origen agropecuario Intercambio Comercial Argentino", r"^Exportaciones de manufacturas de origen agropecuario\. En millones de dólares\.?$", "Intercambio Comercial Argentino", "expo_moa"),
    ("IMIG ingresos tributarios", r"^IMIG\. Ingresos totales\. Ingresos tributarios$", "IMIG", "ingresos_tributarios"),
]


# Balanza energética (pedido de Domingo, 25/11/2026: "Vaca Muerta todavía no reemplaza al agro"): INDEC, ICA, millones de US$
FIJAS = {"74.3_IECE_0_M_35": ("expo_energia", "Exportación de combustibles y energía"),
         "74.3_IICL_0_M_42": ("impo_combustibles", "Importaciones de combustibles y lubricantes"),
         "74.3_IET_0_M_16": ("expo_total", "Exportaciones totales"),
         "74.3_IEPP_0_M_35": ("expo_primarios", "Exportaciones de productos primarios")}


def pedir(url, **params):
    for i in range(4):
        try:
            r = requests.get(url, params=params, timeout=60)
            if r.status_code == 200: return r.json()
        except Exception:
            pass
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"sin respuesta: {url} {params}")


def descubrir():
    elegidas = {}
    for q, rx, ds, corto in BUSCAR:
        vistos = 0
        for off in range(0, 200, 50):
            r = pedir(f"{API}/search/", q=q, limit=50, start=off)
            for x in r.get("data", []):
                f, d = x.get("field", {}), x.get("dataset", {})
                if f.get("frequency") != "R/P1M" or ds not in (d.get("title") or ""): continue
                if re.search(rx, f.get("description") or ""):
                    elegidas[f["id"]] = (corto or f["description"], f["description"])
                    vistos += 1
            if len(r.get("data", [])) < 50: break
        print(f"{q}: {vistos} series", flush=True)
    return elegidas


def bajar(ids):
    filas = []
    lista = list(ids)
    for i in range(0, len(lista), 20):
        lote = lista[i:i + 20]
        r = pedir(f"{API}/series/", ids=",".join(lote), start_date=DESDE, limit=1000, format="json", metadata="none")
        for fila in r.get("data", []):
            for sid, v in zip(lote, fila[1:]):
                if v is not None: filas.append(dict(id=sid, corto=ids[sid][0], descripcion=ids[sid][1], fecha=fila[0][:10], valor=float(v)))
    return pd.DataFrame(filas)


def nombre_tributo(desc):
    m = re.match(r"(.+?) de los Recursos tributarios", desc)
    return m.group(1).strip() if m else desc


def informe(S, ipc):
    fmt = lambda x, d=0: "s/d" if pd.isna(x) else f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    pct = lambda x: "s/d" if pd.isna(x) else f"{x:+.1f}%".replace(".", ",")
    md = [f"# Fiscal: recaudación y gasto base caja\n\nRehecho el {pd.Timestamp.today():%d/%m/%Y}. Fuente: API de series de datos.gob.ar "
          "(Ministerio de Economía), mensual, millones de pesos. La recaudación sale con unos dos meses de atraso en esta API "
          "(ARCA la informa el primer día hábil del mes siguiente); el IMIG, con unos tres.\n"]
    # --- recaudación
    R = S[S.descripcion.str.contains("Recursos tributarios totales y por tributo")].copy()
    if len(R):
        R["tributo"] = R.descripcion.map(nombre_tributo)
        P = R.pivot_table(index="fecha", columns="tributo", values="valor").sort_index()
        tot = [c for c in P.columns if c.lower() == "total recursos tributarios"]
        ult = P.index.max()
        md.append(f"## Recaudación (ARCA), último mes: {pd.Timestamp(ult):%m/%Y}\n")
        if ipc is not None:
            md.append("Variación real: deflactada con el IPC nacional (INDEC, serie del BCRA que guarda el sistema).\n")
        md.append(f"| Concepto | {pd.Timestamp(ult):%m/%Y} | Var. i.a. nominal | Var. i.a. real |\n|---|---|---|---|")
        hace = (pd.Timestamp(ult) - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
        orden = tot + sorted([c for c in P.columns if c not in tot and not c.lower().startswith("total con")], key=lambda c: -P.loc[ult, c] if not pd.isna(P.loc[ult, c]) else 0)
        for c in orden[:14]:
            v, a = P.loc[ult, c], P[c].get(hace)
            nom = (v / a - 1) * 100 if a and not pd.isna(a) else float("nan")
            real = float("nan")
            if ipc is not None and not pd.isna(nom):
                i1, i0 = ipc.get(ult[:7]), ipc.get(hace[:7])
                if i1 and i0: real = ((v / a) / (i1 / i0) - 1) * 100
            md.append(f"| {c} | {fmt(v)} | {pct(nom)} | {pct(real)} |")
        md.append("")
        if tot:
            t = P[tot[0]].dropna()
            md.append("**Total por mes (últimos 13)**\n\n| Mes | Total | Var. i.a. nominal |\n|---|---|---|")
            for f in t.index[-13:]:
                a = t.get((pd.Timestamp(f) - pd.DateOffset(years=1)).strftime("%Y-%m-%d"))
                md.append(f"| {pd.Timestamp(f):%m/%Y} | {fmt(t[f])} | {pct((t[f] / a - 1) * 100 if a else float('nan'))} |")
            md.append("")
    # --- aguinaldo público (compromiso conocido)
    G = S[S.corto.isin(["jubilaciones", "remuneraciones"])].pivot_table(index="fecha", columns="corto", values="valor").sort_index()
    md.append("## Aguinaldo del sector público nacional: estimación propia a confirmar\n")
    if len(G) and {"jubilaciones", "remuneraciones"} <= set(G.columns):
        G["suma"] = G.jubilaciones + G.remuneraciones
        md.append("Método: el aguinaldo es medio haber/sueldo. **Control**: en cada diciembre conocido, el exceso del gasto de diciembre "
                  "sobre el promedio de octubre y noviembre, dividido el promedio, tendría que dar cerca de 0,5 (en junio pasa lo mismo).\n")
        md.append("| Año | Jubilaciones + remuneraciones, prom. oct-nov | Diciembre | Exceso | Exceso / promedio |\n|---|---|---|---|---|")
        razones = {}
        for y in sorted({f[:4] for f in G.index}):
            o, n, d = G.suma.get(f"{y}-10-01"), G.suma.get(f"{y}-11-01"), G.suma.get(f"{y}-12-01")
            if o and n and d:
                p = (o + n) / 2; razones[y] = (d - p) / p
                md.append(f"| {y} | {fmt(p)} | {fmt(d)} | {fmt(d - p)} | {fmt((d - p) / p, 2)} |")
        u = G.suma.dropna(); um = u.index.max()
        md.append("")
        # diciembre de 2023 queda fuera del promedio: inflación de 25,5% en el mes (devaluación), el exceso no es solo aguinaldo
        usar = {y: v for y, v in razones.items() if y >= "2024"}
        if len(usar):
            r = sum(usar.values()) / len(usar)
            # llevar el último mes conocido a diciembre del año en curso con el IPC (jubilaciones se indexan por IPC); meses sin IPC: el último disponible
            base, f = u[um], pd.Timestamp(um)
            dic = pd.Timestamp(f"{pd.Timestamp.today().year}-12-01")
            ajuste, meses, ult_ipc = 1.0, [], None
            if ipc is not None:
                claves = sorted(ipc)
                for k in range(1, (dic.year - f.year) * 12 + dic.month - f.month + 1):
                    m = (f + pd.DateOffset(months=k)).strftime("%Y-%m")
                    ant = (f + pd.DateOffset(months=k - 1)).strftime("%Y-%m")
                    if m in ipc and ant in ipc: g = ipc[m] / ipc[ant]
                    else: g = (ipc[claves[-1]] / ipc[claves[-2]]) if len(claves) > 1 else 1.0; meses.append(m)
                    ajuste *= g
            est = base * ajuste * r
            md.append(f"**Estimación del aguinaldo de diciembre de {dic.year}: $ {fmt(est / 1e6, 2)} billones** "
                      f"(= último mes conocido {f:%m/%Y}: {fmt(base)} M, llevado a diciembre con el IPC ×{fmt(ajuste, 3)}"
                      f"{' (meses sin IPC todavía, con el último dato: ' + ', '.join(meses) + ')' if meses else ''}, por el exceso promedio "
                      f"de diciembre {', '.join(sorted(usar))}: {fmt(r, 2)}; 2023 queda afuera por la inflación de ese diciembre). Incluye solo jubilaciones contributivas y remuneraciones del SPN; no incluye "
                      "otras prestaciones ni transferencias a provincias o universidades. Tipo: compromiso conocido en el monto, estimado en la fecha "
                      "(se paga en la segunda quincena de diciembre). Estado: a confirmar con el IMIG de diciembre.\n")
        else:
            md.append("Sin diciembres completos en la serie: s/d.\n")
    else:
        md.append("No se encontraron las series del IMIG: s/d.\n")
    # --- balanza energética contra el agro
    E = S[S.corto.isin(["expo_energia", "impo_combustibles", "expo_total", "expo_primarios", "expo_moa"])].pivot_table(index="fecha", columns="corto", values="valor").sort_index()
    md.append("## Balanza energética y agro (INDEC, Intercambio Comercial Argentino; millones de US$)\n")
    if {"expo_energia", "impo_combustibles"} <= set(E.columns):
        E["saldo_energia"] = E.expo_energia - E.impo_combustibles
        if {"expo_primarios", "expo_moa"} <= set(E.columns): E["agro"] = E.expo_primarios + E.expo_moa
        u = E.dropna(subset=["expo_energia"]).index.max()
        md.append(f"Último mes: {pd.Timestamp(u):%m/%Y}. Agro = productos primarios + manufacturas de origen agropecuario (incluye algo de no agro, como minerales, dentro de primarios).\n")
        md.append("| Mes | Expo energía | Impo combustibles | Saldo energético | Expo agro | Expo totales | Energía / totales |\n|---|---|---|---|---|---|---|")
        for f in E.index[-13:]:
            r = E.loc[f]
            md.append(f"| {pd.Timestamp(f):%m/%Y} | {fmt(r.expo_energia)} | {fmt(r.impo_combustibles)} | {fmt(r.saldo_energia)} | {fmt(r.get('agro'))} | {fmt(r.get('expo_total'))} | "
                      f"{fmt(r.expo_energia / r.expo_total * 100, 1) + '%' if r.get('expo_total') else 's/d'} |")
        md.append("\n**Últimos 12 meses acumulados (millones de US$)**\n\n| Hasta | Saldo energético | Expo energía | Expo agro | Energía / agro |\n|---|---|---|---|---|")
        for f in [E.index[-1], (pd.Timestamp(E.index[-1]) - pd.DateOffset(years=1)).strftime("%Y-%m-%d"), (pd.Timestamp(E.index[-1]) - pd.DateOffset(years=2)).strftime("%Y-%m-%d")]:
            w = E.loc[:f].tail(12)
            if len(w) < 12: continue
            ag = w.agro.sum() if "agro" in w else float("nan")
            md.append(f"| {pd.Timestamp(f):%m/%Y} | {fmt(w.saldo_energia.sum())} | {fmt(w.expo_energia.sum())} | {fmt(ag)} | {fmt(w.expo_energia.sum() / ag * 100, 1) + '%' if ag else 's/d'} |")
        md.append("")
    else:
        md.append("No se encontraron las series del ICA: s/d.\n")
    (SAL / "FISCAL.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--ipc"); a = ap.parse_args()
    SAL.mkdir(parents=True, exist_ok=True)
    ids = descubrir()
    ids.update(FIJAS)
    S = bajar(ids).sort_values(["id", "fecha"])
    S.to_csv(SAL / "series.csv", index=False)
    ipc = None
    if a.ipc and Path(a.ipc).exists():
        I = pd.read_csv(a.ipc, dtype={"fecha": str}).sort_values("fecha")
        I["mes"] = I.fecha.str[:7]; I["indice"] = (1 + I.valor.astype(float) / 100).cumprod()
        ipc = dict(zip(I.mes, I.indice))
    informe(S, ipc)
    print(f"fiscal: {S.id.nunique()} series, {len(S)} datos, hasta {S.fecha.max()}", flush=True)


if __name__ == "__main__":
    main()
# FIN fiscal.py
