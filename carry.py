"""Carry del inversor de a pie, con costos: Lecap sin cobertura, Lecap cubierta con dólar futuro y caución en pesos.
Calcula todos los días, con los datos del propio repositorio, cuánto queda neto de comisiones y de la fricción de cambiar dólares.
No lee de ninguna fuente externa: usa estudios/letras, estudios/futuros, estudios/monetarias, estudios/mae y (si existe) estudios/mep.

Costos (en %): PPI, cuenta por internet, vigentes desde el 1/7/2026 (portfoliopersonal.com/Contenido/comisiones).
Los derechos de mercado, la garantía de los futuros y las puntas de los bonos no están en esa tabla: se avisan como no incluidos.

Salidas en estudios/carry/: CARRY.md (tabla del día), historico.csv (una fila por letra y día)
"""
import csv, statistics
from datetime import date, datetime
from pathlib import Path

E = Path("estudios")
SAL = E / "carry"; SAL.mkdir(parents=True, exist_ok=True)

# --- Costos (% sobre el monto) ---
LECAP_COMPRA = 0.20
LECAP_AMORT = 0.26                 # "hasta"; se cobra al vencimiento
FUT_POR_OPERACION = 0.5 * 1.21     # 0,5% + IVA; se cobra en la compra y en el vencimiento
FX_COMISIONES = 2 * 2 * 0.60       # ida y vuelta = 4 operaciones de bonos a 0,60% (dos por cada cambio)
CAUCION_COLOCADORA_ANUAL = 2.0 * 1.21   # 2% + IVA anual (prorrateado por días)


def leer(ruta):
    p = E / ruta
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def spread_medido():
    """Costo de ida y vuelta del MEP por bonos medido con las puntas (estudios/mep/mep.csv), mediana de las lecturas con mercado abierto."""
    filas = [r for r in leer("mep/mep.csv") if r.get("via") == "MEP" and r.get("plazo") == "A-24HS"]
    vals = []
    for r in filas:
        try:
            v = float(r["costo_ida_vuelta_pct"])
        except Exception:
            continue
        if 0 < v < 5:                       # descarta lecturas con puntas viejas o fuera de mercado
            vals.append(v)
    return (statistics.median(vals), len(vals)) if vals else (None, 0)


def ultima_tasa_caucion():
    filas = [r for r in leer("mae/cauciones_historico.csv") if r.get("ticker") == "CAARS" and str(r.get("plazo", "")).lstrip("0") == "1"]
    por_dia = {}
    for r in filas:
        try:
            por_dia.setdefault(r["fecha_dia"], []).append((float(r["tasaPP"]), float(r["montoConcertado"])))
        except Exception:
            continue
    dias = sorted(por_dia)[-10:]
    ponder = []
    for d in dias:
        m = sum(x[1] for x in por_dia[d])
        if m:
            ponder.append(sum(x[0] * x[1] for x in por_dia[d]) / m)
    return (sum(ponder) / len(ponder), dias[-1]) if ponder else (None, None)


def main():
    hoy = datetime.now().date()
    sp, n_sp = spread_medido()
    fx = FX_COMISIONES + (sp if sp is not None else 0.0)
    fx_txt = (f"{FX_COMISIONES:.1f}% de comisiones + {sp:.2f}% de puntas medidas ({n_sp} lecturas)" if sp is not None
              else f"{FX_COMISIONES:.1f}% de comisiones (puntas de los bonos todavía sin medir)")
    curva = [r for r in leer("futuros/curva_dolar.csv")]
    for r in curva:
        r["_v"] = date.fromisoformat(r["vencimiento"])
        r["_p"] = float(r["precio"])
    spot = float(curva[0]["mayorista"]) if curva and curva[0].get("mayorista") else None
    inst = {r["ticker"]: r for r in leer("letras/instrumentos.csv")}
    ult = {}
    for r in leer("letras/historico_tea.csv"):
        if r["plazo"] != "A-24HS":
            continue
        try:
            tea, dias = float(r["tea"]), int(r["dias"])
        except Exception:
            continue
        if 5 <= tea <= 60 and (r["ticker"] not in ult or r["fecha"] > ult[r["ticker"]]["fecha"]):
            ult[r["ticker"]] = r
    filas = []
    for tk, r in sorted(ult.items()):
        i = inst.get(tk)
        if not i or not spot:
            continue
        precio, pago = float(r["precio"]), float(i["pago_final"])
        v = date.fromisoformat(i["vencimiento"])
        dias = int(r["dias"])
        if dias < 30:                      # letras a menos de 30 días: el costo fijo no se amortiza y la tasa es ruidosa
            continue
        g = pago / precio
        tea_bruta = (g ** (365 / dias) - 1) * 100
        c_sin = LECAP_COMPRA + LECAP_AMORT + fx
        punto_equilibrio = (g * (1 - c_sin / 100) - 1) * 100            # suba máxima del dólar en el período para no perder, sin cobertura
        fut = next((f for f in curva if f["_v"] >= v), None)
        fila = dict(fecha=r["fecha"], letra=tk, vence=i["vencimiento"], dias=dias, tea_lecap=round(tea_bruta, 1),
                    equilibrio_sin_cobertura_pct=round(punto_equilibrio, 2))
        if fut:
            cub_bruta = (g * spot / fut["_p"] - 1) * 100
            c_cub = LECAP_COMPRA + LECAP_AMORT + fx + 2 * FUT_POR_OPERACION
            tea_cub = ((1 + cub_bruta / 100) ** (365 / dias) - 1) * 100
            dias_eq = (c_cub / (tea_cub / 365)) if tea_cub > 0 else None
            fila.update(futuro=fut["ticker"], dev_implicita_pct=round((fut["_p"] / spot - 1) * 100, 2), cubierta_bruta_pct=round(cub_bruta, 2),
                        costos_cubierta_pct=round(c_cub, 2), cubierta_neta_pct=round(cub_bruta - c_cub, 2),
                        dias_para_cubrir_costos=round(dias_eq) if dias_eq else "nunca")
        filas.append(fila)
    tna, dia_c = ultima_tasa_caucion()
    cau = {}
    if tna:
        for n in (7, 30, 90):
            bruta = tna * n / 365
            com = CAUCION_COLOCADORA_ANUAL * n / 365
            cau[n] = (bruta, com, bruta - com - fx)
    # historico
    if filas:
        ruta = SAL / "historico.csv"
        nuevo = not ruta.exists()
        cols = ["consulta"] + [c for c in dict.fromkeys(k for f in filas for k in f)]
        with open(ruta, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            if nuevo:
                w.writeheader()
            for f in filas:
                w.writerow(dict(consulta=hoy.isoformat(), **f))
    md = [f"# Carry del inversor de a pie — {hoy:%d/%m/%Y}", "",
          f"Dólar mayorista de referencia: {spot}. Costo de ida y vuelta del cambio de dólares por bonos: {fx_txt} (= {fx:.2f}%).", "",
          "## Lecap, sin cobertura y cubierta con dólar futuro", "",
          "| Letra | Vence | Días | TEA Lecap | Suba máx. del dólar sin perder (sin cobertura) | Futuro usado | Devaluación implícita | Cubierta bruta | Costos | **Cubierta neta** | Días para cubrir costos |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for f in filas:
        md.append(f"| {f['letra']} | {f['vence']} | {f['dias']} | {f['tea_lecap']}% | {f['equilibrio_sin_cobertura_pct']}% | {f.get('futuro', '-')} | "
                  f"{f.get('dev_implicita_pct', '-')}% | {f.get('cubierta_bruta_pct', '-')}% | {f.get('costos_cubierta_pct', '-')}% | "
                  f"**{f.get('cubierta_neta_pct', '-')}%** | {f.get('dias_para_cubrir_costos', '-')} |")
    md += ["", "- *Suba máxima del dólar sin perder:* cuánto puede subir el dólar en el período (hasta el vencimiento) para que la Lecap sin cobertura, ya descontados los costos, no rinda menos que haber quedado en dólares.",
           "- *Cubierta bruta / neta:* resultado en dólares, en el período, de comprar la Lecap y fijar el precio de vuelta con el futuro del vencimiento igual o inmediato posterior. La neta resta los costos.", ""]
    if cau:
        md += [f"## Caución colocadora en pesos a 1 día, renovada (tasa promedio ponderada de A3 de las últimas 10 ruedas hasta {dia_c}: {tna:.1f}% TNA)", "",
               "| Plazo | Rinde en pesos | Comisión PPI | Costo de cambio | **Neto en pesos de ida y vuelta** |", "|---|---|---|---|---|"]
        for n, (b, c, neto) in cau.items():
            md.append(f"| {n} días | {b:.2f}% | {c:.2f}% | {fx:.2f}% | **{neto:.2f}%** |")
        md += ["", "El neto es lo que deja, antes de que se mueva el dólar, pasar de dólares a pesos, prestar en caución y volver a dólares. Si el dólar sube más que ese neto, se pierde."]
    md += ["", "## No incluido", "- Derechos de mercado de A3 y BYMA.", "- Garantía inmovilizada y ajustes diarios de los futuros (costo de oportunidad y liquidez).",
           "- Diferencia entre la base del mayorista (que cubre el futuro) y el MEP/CCL con el que se cambia (riesgo de brecha).",
           "- Impuestos y la diferencia de plazos entre el vencimiento de la letra y el del futuro."]
    (SAL / "CARRY.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
