"""Semáforo de riesgo político: ningún indicio solo alcanza, así que se combinan varios débiles.
Cada día se evalúan, con información de ese día y anteriores (sin mirar el futuro), estas condiciones:
  1. Riesgo país en su máximo de los últimos 60 días hábiles.
  2. Brecha CCL–MEP arriba del percentil 90 de los últimos 250 días hábiles.
  3. Curva: en 3 días, los Globales largos (GD41D, GD46D) caen al menos 1 punto más que el corto (GD30D).
  4. Régimen: en 5 días, bancos y empresas de tarifas reguladas (GGAL, BMA, SUPV, BBAR, EDN, CEPU, TRAN, TGSU2, TGNO4)
     rinden al menos 1,5 puntos menos que el resto del panel (mediana contra mediana).
  5. Volumen en las líneas C (YPFDC, GGALC, PAMPC) muy por encima de lo normal: se suma cuando haya historia (desde el 4/11/2026).
Alerta = al menos 3 condiciones encendidas. Los umbrales se fijaron antes de mirar resultados y no se ajustan con ellos.
Escribe estudios/SEMAFORO.md y estudios/historico/semaforo.csv.
"""
from pathlib import Path
import numpy as np
import pandas as pd

H = Path("estudios/historico")
REGIMEN = ["GGAL", "BMA", "SUPV", "BBAR", "EDN", "CEPU", "TRAN", "TGSU2", "TGNO4"]
PANEL = ["ALUA", "BBAR", "BMA", "BYMA", "CEPU", "COME", "CRES", "ECOG", "EDN", "GGAL", "IRSA", "LOMA", "METR", "PAMP",
         "SUPV", "TECO2", "TGNO4", "TGSU2", "TRAN", "TXAR", "VALO", "YPFD"]
ELECCIONES = {"2019-08-11": "PASO 2019", "2019-10-27": "Generales 2019", "2021-09-12": "PASO 2021", "2021-11-14": "Legislativas 2021",
              "2023-08-13": "PASO 2023", "2023-10-22": "Generales 2023", "2023-11-19": "Balotaje 2023",
              "2025-09-07": "Provincia de Buenos Aires 2025", "2025-10-26": "Legislativas 2025"}


def ar(x, d=1):
    return "—" if x != x else f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def armar():
    D = pd.read_csv(H / "dolares_diarios.csv", index_col=0, parse_dates=True)
    R = pd.read_csv(H / "riesgo_pais.csv"); R = R.set_index(pd.to_datetime(R.fecha)).valor.sort_index()
    P = pd.read_csv(H / "semaforo_precios.csv", parse_dates=["fecha"]).pivot_table(index="fecha", columns="ticker", values="cierre")
    for c in P:          # desdoblamientos (YPFD 10 a 1 en ago-2026, etc.): se ajusta el pasado al precio nuevo
        r = P[c] / P[c].ffill().shift(1)
        for fe in r.index[(r < 0.25) | (r > 4)]:
            P.loc[P.index < fe, c] /= round(1 / r[fe]) if r[fe] < 1 else 1 / round(r[fe])
    d = pd.DataFrame(index=P.index[P.index >= "2019-01-01"])
    d["rp"] = R.reindex(d.index, method="ffill")
    d["brecha"] = (D.contadoconliqui / D.bolsa - 1).reindex(d.index, method="ffill") * 100
    # 1. riesgo país en máximo de 60 días
    d["c1"] = d.rp >= d.rp.rolling(60, min_periods=40).max()
    # 2. brecha arriba del p90 de 250 días anteriores
    p90 = d.brecha.shift(1).rolling(250, min_periods=120).quantile(0.9)
    d["c2"] = np.where(p90.notna() & d.brecha.notna(), d.brecha > p90, np.nan)
    # 3. curva: largos contra corto en 3 días
    if {"GD41D", "GD46D", "GD30D"} <= set(P.columns):
        r3 = P[["GD41D", "GD46D", "GD30D"]].pct_change(3, fill_method=None) * 100
        dif = r3[["GD41D", "GD46D"]].mean(axis=1, skipna=True) - r3.GD30D     # GD41D sin datos de PPI en 2026: queda GD46D
        d["c3"] = np.where(dif.notna(), dif <= -1.0, np.nan)
    else:
        d["c3"] = np.nan
    # 4. régimen: bancos y reguladas contra el resto en 5 días
    r5 = P[[c for c in PANEL if c in P]].pct_change(5, fill_method=None) * 100
    reg = r5[[c for c in REGIMEN if c in r5]].median(axis=1); resto = r5[[c for c in r5 if c not in REGIMEN]].median(axis=1)
    d["c4"] = np.where(reg.notna() & resto.notna(), (reg - resto) <= -1.5, np.nan)
    C = d[["c1", "c2", "c3", "c4"]].astype(float)
    d["encendidas"] = C.sum(axis=1, min_count=1); d["disponibles"] = C.notna().sum(axis=1)
    d["alerta"] = (d.encendidas >= 3) & (d.disponibles >= 3)
    # lo que pasó después (solo para evaluar; nunca entra en la señal)
    idx = P[[c for c in PANEL if c in P]]
    panel = np.exp(np.log(idx / idx.shift(1)).median(axis=1, skipna=True).fillna(0).cumsum())
    for h in (20, 60):
        d[f"rp_{h}d"] = (d.rp.shift(-h) / d.rp - 1) * 100
        d[f"panel_{h}d"] = (panel.shift(-h) / panel - 1).reindex(d.index) * 100
    return d


def informe(d):
    hoy = d.dropna(subset=["rp"]).iloc[-1]; f = d.dropna(subset=["rp"]).index[-1]
    nom = {"c1": "Riesgo país en máximo de 60 días", "c2": "Brecha CCL–MEP arriba del percentil 90 (250 días)",
           "c3": "Bonos largos caen ≥1 punto más que el corto (3 días)", "c4": "Bancos y reguladas ≥1,5 puntos peor que el resto (5 días)"}
    l = ["# Semáforo de riesgo político", "",
         f"Al {f.date():%d/%m/%Y}: **{'ALERTA' if hoy.alerta else 'sin alerta'}** — {int(hoy.encendidas)} de {int(hoy.disponibles)} condiciones encendidas "
         f"(riesgo país {ar(hoy.rp, 0)}, brecha CCL–MEP {ar(hoy.brecha, 2)}%).", "",
         "| Condición | Hoy |", "|---|---|"]
    for c, n in nom.items():
        v = hoy[c]; l.append(f"| {n} | {'—' if v != v else ('encendida' if v else 'apagada')} |")
    l.append("| Volumen en líneas C muy por encima de lo normal | se mide desde el 4/11/2026 |")
    # episodios: primer día de cada racha de alerta
    a = d.alerta.astype(int); ini = d.index[(a == 1) & (a.shift(1, fill_value=0) == 0)]
    l += ["", "## Episodios de alerta desde 2019", "",
          "Primer día de cada racha. Riesgo país y panel líder (mediana, en pesos) 20 y 60 días hábiles después.", "",
          "| Inicio | Días en alerta | Riesgo país | RP +20d | RP +60d | Panel +20d | Panel +60d | Elección en los 60 días siguientes |", "|---|---|---|---|---|---|---|---|"]
    for i in ini:
        dur = 0
        for v in a[a.index >= i]:
            if not v: break
            dur += 1
        el = [n for fe, n in ELECCIONES.items() if 0 <= (pd.Timestamp(fe) - i).days <= 90]
        r = d.loc[i]
        l.append(f"| {i.date():%d/%m/%Y} | {dur} | {ar(r.rp, 0)} | {ar(r.rp_20d)}% | {ar(r.rp_60d)}% | {ar(r.panel_20d)}% | {ar(r.panel_60d)}% | {', '.join(el) or '—'} |")
    s = d.dropna(subset=["rp_20d"]); al, no = s[s.alerta], s[~s.alerta]
    l += ["", "## ¿Sirve? (días en alerta contra el resto)", "", "| | Días | RP +20d (media) | Prob. RP +10% en 20d | Panel +20d (media) | Panel +60d (media) |", "|---|---|---|---|---|---|"]
    for n, g in (("En alerta", al), ("Sin alerta", no)):
        l.append(f"| {n} | {len(g)} | {ar(g.rp_20d.mean())}% | {ar((g.rp_20d > 10).mean() * 100, 0)}% | {ar(g.panel_20d.mean())}% | {ar(g.panel_60d.mean())}% |")
    l += ["", "Para cada elección: ¿estaba encendido el semáforo en los 20 días hábiles previos?", "", "| Elección | Días en alerta (de 20 previos) | Máximo de condiciones |", "|---|---|---|"]
    for fe, n in ELECCIONES.items():
        w = d[(d.index < fe)].tail(20)
        if len(w): l.append(f"| {n} ({pd.Timestamp(fe):%d/%m/%Y}) | {int(w.alerta.sum())} | {int(w.encendidas.max()) if w.encendidas.notna().any() else '—'} |")
    l += ["", "## Cómo leerlo", "",
          "- Es un estado, no un pronóstico ni una orden: dice \"estamos en régimen de riesgo político\" y obliga a revisar posiciones con reglas fijadas de antemano.",
          "- Umbrales fijados antes de ver resultados. Antes de septiembre de 2020 no existen los Globales: se evalúan 3 condiciones.",
          "- 2020–2023 con cepo: la brecha CCL–MEP medía regulaciones, no solo expectativas.",
          "- Fuentes: riesgo país y dólares de argentinadatos; precios diarios de PPI."]
    Path("estudios/SEMAFORO.md").write_text("\n".join(l) + "\n", encoding="utf-8")
    d.to_csv(H / "semaforo.csv")
    print("\n".join(l), flush=True)


if __name__ == "__main__":
    informe(armar())
# FIN semaforo.py
