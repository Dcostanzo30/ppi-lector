"""Cápsula de reservas del BCRA: reservas brutas y netas estimadas con la metodología del FMI, a partir del balance semanal.
Fuente: Estado resumido de activos y pasivos del BCRA (serie semanal en Excel, en miles de pesos, días 7, 15, 23 y fin de mes).
Método (TMU del acuerdo con el FMI, staff report de mayo 2026, párrafo 11):
  netas = brutas − encajes en dólares (Cuentas corrientes en otras monedas) − swaps y otros pasivos de reserva (Otros pasivos,
          que contiene el swap con China) − crédito neto del FMI recibido desde 2025 + ajuste de calibración.
  Los depósitos del Tesoro en el BCRA NO se restan (así lo define el FMI).
  "A tipos del programa": el oro se valúa a la cantidad de onzas de fin de 2025 por US$4.326 (precio fijo del programa).
Calibración: el ajuste es la diferencia promedio contra los datos del FMI a fin de 2024 (−2,4) y fin de 2025 (−11,7).
Validación fuera de muestra: fin de marzo 2026 a tipos del programa (FMI: −12,9 aprox.) y fin de 2023 (FMI: −11,2).
Escribe estudios/reservas/reservas.csv y estudios/reservas/RESERVAS.md. Solo lee archivos públicos ya descargados.
"""
import re, unicodedata
from datetime import date
from pathlib import Path
import pandas as pd

CRUDO = Path("estudios/reservas/crudo/estados-resumidos-activos-pasivos-bcra-serie-anual-1998-actualidad.xls")
SAL = Path("estudios/reservas")
CLAVES = {"brutas": ["ORO, DIVISAS"], "oro": ["- ORO (NETO"], "encajes": ["CUENTAS CORRIENTES EN OTRAS MONEDAS"],
          "dep_gobierno": ["DEPOSITOS DEL GOBIERNO"], "bopreal": ["EN MONEDA EXTRANJERA"], "pases": ["OBLIGACIONES POR OPERACIONES DE PASE"],
          "otros_pasivos": ["OTROS PASIVOS"], "tc": ["TIPO DE CAMBIO"]}
# Crédito neto del FMI desde 2025 (miles de millones de US$, acumulado): desembolsos menos devoluciones de capital.
# Supuestos a verificar: 12,0 (abril 2025), 2,0 (agosto 2025), 1,0 (mayo 2026), −0,9 (fines de sep. 2026, primera devolución del EFF 2022).
FMI = [(date(2025, 4, 15), 12.0), (date(2025, 8, 4), 2.0), (date(2026, 5, 21), 1.0), (date(2026, 9, 25), -0.9)]
OFICIAL = {date(2023, 12, 31): -11.2, date(2024, 12, 31): -2.4, date(2025, 12, 31): -11.7}   # FMI, a tipos corrientes
CALIBRA = [date(2024, 12, 31), date(2025, 12, 31)]
ORO_PROGRAMA = 4326.01


def norm(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()


def leer():
    x = pd.ExcelFile(CRUDO)
    filas = []
    for s in x.sheet_names:
        if not re.search(r"20(2[2-9]|[3-9]\d)", s): continue
        d = pd.read_excel(x, s, header=None)
        fila_f = next(i for i in range(10) if any(hasattr(c, "year") for c in d.iloc[i, 1:]))
        pos = {}
        for k, pats in CLAVES.items():
            for i in range(len(d)):
                if any(p in norm(d.iat[i, 0]) for p in pats) and d.iloc[i, 1:].notna().any():
                    pos[k] = i; break
        for j in range(1, d.shape[1]):
            f = d.iat[fila_f, j]
            if not hasattr(f, "year"): continue
            r = {"fecha": pd.Timestamp(f).date()}
            for k, i in pos.items(): r[k] = pd.to_numeric(d.iat[i, j], errors="coerce")
            filas.append(r)
    df = pd.DataFrame(filas).dropna(subset=["brutas", "tc"]).drop_duplicates("fecha", keep="last").sort_values("fecha").reset_index(drop=True)
    for k in CLAVES:
        if k != "tc": df[k] = df[k] / df["tc"] / 1e6   # miles de $ -> miles de millones de US$
    return df


def fmi_acum(f):
    return sum(v for d, v in FMI if d <= f)


def main():
    df = leer()
    df["fmi_desde_2025"] = df["fecha"].map(fmi_acum)
    df["netas_sin_ajuste"] = df["brutas"] - df["encajes"] - df["otros_pasivos"] - df["fmi_desde_2025"]
    def en(f):
        return df[df["fecha"] <= f].iloc[-1]
    ajuste = sum(OFICIAL[f] - en(f)["netas_sin_ajuste"] for f in CALIBRA) / len(CALIBRA)
    df["netas_fmi"] = df["netas_sin_ajuste"] + ajuste
    onzas = en(date(2025, 12, 31))["oro"] / ORO_PROGRAMA
    df["netas_fmi_tipos_programa"] = df["netas_fmi"] - df["oro"] + onzas * ORO_PROGRAMA
    df["netas_acidas"] = df["netas_fmi"] - df["bopreal"] - df["dep_gobierno"]
    SAL.mkdir(parents=True, exist_ok=True)
    df.round(3).to_csv(SAL / "reservas.csv", index=False)
    escribir_md(df, ajuste, en)
    u = df.iloc[-1]
    print(f"Reservas {u['fecha']}: brutas {u['brutas']:.2f}, netas FMI {u['netas_fmi']:.2f}, ajuste {ajuste:.2f}", flush=True)


def ar(x, d=1):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def escribir_md(df, ajuste, en):
    u = df.iloc[-1]
    l = ["# Reservas del BCRA: brutas y netas (método FMI, estimación propia)", "",
         f"Último balance semanal: **{u['fecha']}** (el BCRA lo publica con una semana de demora). En miles de millones de US$.", "",
         "| | Último | Hace 4 balances | Fin de 2025 |", "|---|---|---|---|"]
    a = df.iloc[-5] if len(df) > 5 else df.iloc[0]; f25 = en(date(2025, 12, 31))
    for c, n in [("brutas", "Reservas brutas (BCRA)"), ("encajes", "− Encajes en dólares"), ("otros_pasivos", "− Swaps y otros pasivos (incluye China)"),
                 ("fmi_desde_2025", "− Crédito neto del FMI desde 2025"), ("netas_fmi", "**= Netas método FMI**"),
                 ("netas_fmi_tipos_programa", "Netas FMI a tipos del programa (oro a US$4.326)"), ("bopreal", "− BOPREAL"),
                 ("dep_gobierno", "− Depósitos del Gobierno"), ("netas_acidas", "**= Netas ácidas**")]:
        l.append(f"| {n} | {ar(u[c])} | {ar(a[c])} | {ar(f25[c])} |")
    l += ["", f"Fechas: hace 4 balances = {a['fecha']}; fin de 2025 = {f25['fecha']}.", "",
          "## Control contra los datos oficiales del FMI", "", "| Fecha | FMI | Nuestra estimación | Diferencia | Uso |", "|---|---|---|---|---|"]
    for f, v in OFICIAL.items():
        r = en(f)
        l.append(f"| {r['fecha']} | {ar(v)} | {ar(r['netas_fmi'])} | {ar(r['netas_fmi'] - v)} | {'calibración' if f in CALIBRA else 'validación'} |")
    m = en(date(2026, 3, 31))
    onzas = en(date(2025, 12, 31))["oro"] / ORO_PROGRAMA
    v_mar = m["netas_fmi"] - m["oro"] + onzas * 2808.08          # oro al precio del programa vigente hasta marzo 2026
    l.append(f"| {m['fecha']} (oro a US$2.808, programa de ene-2025) | −12,9 (−2,4 − 10,5) | {ar(v_mar)} | {ar(v_mar + 12.9)} | validación (aprox.) |")
    l += ["", f"Ajuste de calibración: {ar(ajuste, 2)} (otros pasivos del FMI que el balance no muestra por separado: SEDESA, ALADI, repos de corto plazo, diferencias de valuación).", "",
          "## Últimos 12 balances", "", "| Fecha | Brutas | Netas FMI | Netas FMI (tipos programa) | Netas ácidas |", "|---|---|---|---|---|"]
    for _, r in df.tail(12).iloc[::-1].iterrows():
        l.append(f"| {r['fecha']} | {ar(r['brutas'])} | {ar(r['netas_fmi'])} | {ar(r['netas_fmi_tipos_programa'])} | {ar(r['netas_acidas'])} |")
    l += ["", "Notas: el FMI resta el swap con China completo, los encajes y su propio crédito desde 2025, y no resta los depósitos del Tesoro.",
          "\"Netas ácidas\" además resta BOPREAL y los depósitos del Gobierno (que incluyen pesos, así que es una cota exigente).",
          "El crédito del FMI es un supuesto cargado a mano en reservas.py (desembolsos y devoluciones); hay que actualizarlo en cada movimiento.", ""]
    (SAL / "RESERVAS.md").write_text("\n".join(l), encoding="utf-8")


if __name__ == "__main__":
    main()
# FIN reservas.py
