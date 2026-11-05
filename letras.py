"""Tasa de las Lecap (letras capitalizables del Tesoro) día por día desde junio, con datos de PPI.
Solo consulta. Misma conexión y credenciales que los demás lectores.

Idea: una Lecap paga un monto fijo al vencimiento (por cada 100 nominales). Con el precio de cada día y los días que faltan,
la tasa efectiva anual (TEA) es (pago / precio)^(365/días) - 1. El pago final y el vencimiento se los pedimos a la calculadora de PPI
(estimate_bonds) una sola vez por letra.

Salidas en estudios/letras/: instrumentos.csv, historico_tea.csv, serie_plazo.csv, DIAGNOSTICO.md
"""
import csv, json, os, re, string, sys, time
from datetime import date, datetime, timedelta
from pathlib import Path

SAL = Path("estudios/letras"); SAL.mkdir(parents=True, exist_ok=True)
DESDE = date(2026, 6, 1)
SEMILLAS = ["S31L6", "S14G6", "S31G6", "S30S6", "S30O6", "S13N6", "S30N6", "S31D6", "S29E7", "S27F7", "S31M7", "T15E7", "T30A7", "T31Y7", "T30J7"]
PAUSA = 0.2
DIAG = []


def diag(t):
    print(t, flush=True)
    DIAG.append(t)


def ingresar():
    from ppi_client.ppi import PPI
    p = PPI(sandbox=False)
    p.account.login_api(os.environ["PPI_API_KEY"].strip(), os.environ["PPI_API_SECRET"].strip())
    return p


def buscar(ppi, tk, nm, mercado, tipo):
    time.sleep(PAUSA)
    for a, b in ((tk, nm), (tk, tk), (tk, "")):
        try:
            r = ppi.marketdata.search_instrument(a, b, mercado, tipo)
            if isinstance(r, list):
                return r
        except Exception:
            continue
    return []


def listar(ppi):
    hallados = {}
    for s in SEMILLAS + list(string.ascii_uppercase):
        for r in buscar(ppi, s, "", "BYMA", "LETRAS"):
            tk = str(r.get("ticker", "")).strip().upper()
            if re.fullmatch(r"[ST]\d{2}[A-Z]\d", tk):          # Lecap (S) y Boncap (T): pesos, tasa fija capitalizable
                hallados[tk] = r
    return hallados


def tipo_cantidad(ppi):
    qt = "PAPELES"
    for t in ppi.configuration.get_quantity_types() or []:
        v = json.dumps(t, ensure_ascii=False).upper()
        if "PAPEL" in v or "NOMINAL" in v:
            qt = t.get("value") if isinstance(t, dict) and t.get("value") else qt
            break
    return qt


def pago_final(ppi, tk, fecha, precio, qt):
    """Pago total al vencimiento por cada 100 nominales, y fecha de vencimiento, según la calculadora de PPI."""
    from ppi_client.models.estimate_bonds import EstimateBonds
    time.sleep(PAUSA)
    r = ppi.marketdata.estimate_bonds(EstimateBonds(ticker=tk, date=datetime.combine(fecha, datetime.min.time()),
                                                    quantityType=qt, price=float(precio), quantity=100))
    flujos = r.get("flows") or []
    total = flujos[-1].get("total") if flujos else r.get("total")
    venc = r.get("expirationDate")
    if venc:
        d, m, a = venc.split("/")
        venc = date(int(a), int(m), int(d))
    return total, venc


def historia(ppi, tk):
    out = []
    for pl in ("A-24HS", "INMEDIATA"):
        time.sleep(PAUSA)
        try:
            r = ppi.marketdata.search(tk, "LETRAS", pl, DESDE.isoformat(), date.today().isoformat()) or []
        except Exception as e:
            diag(f"  - {tk} historia {pl}: {type(e).__name__} {str(e)[:100]}")
            continue
        if r:
            for x in r:
                if x.get("price"):
                    out.append((str(x.get("date", ""))[:10], float(x["price"]), pl, x.get("volume")))
            break
    return out


def main():
    diag(f"# Diagnóstico Lecap — {datetime.now():%Y-%m-%d %H:%M}\n")
    try:
        ppi = ingresar()
    except Exception as e:
        diag(f"No se pudo ingresar: {type(e).__name__} {str(e)[:200]}")
        (SAL / "DIAGNOSTICO.md").write_text("\n".join(DIAG), encoding="utf-8")
        return
    hallados = listar(ppi)
    diag(f"Letras encontradas (S/T, pesos): {len(hallados)} -> {sorted(hallados)}\n")
    qt = tipo_cantidad(ppi)
    filas, info = [], []
    for tk in sorted(hallados):
        h = historia(ppi, tk)
        if not h:
            diag(f"- {tk}: sin historia")
            continue
        f0, p0, _, _ = h[-1]
        try:
            total, venc = pago_final(ppi, tk, date.fromisoformat(f0), p0, qt)
        except Exception as e:
            diag(f"- {tk}: la calculadora falló: {type(e).__name__} {str(e)[:120]}")
            continue
        if not total or not venc:
            diag(f"- {tk}: la calculadora no dio pago final o vencimiento")
            continue
        info.append(dict(ticker=tk, vencimiento=venc.isoformat(), pago_final=total, dias_historia=len(h)))
        for f, p, pl, v in h:
            dias = (venc - date.fromisoformat(f)).days
            if dias <= 0 or p <= 0:
                continue
            tea = ((total / p) ** (365 / dias) - 1) * 100
            filas.append(dict(ticker=tk, fecha=f, precio=p, plazo=pl, volumen=v, dias=dias, tea=round(tea, 2)))
        diag(f"- {tk}: vence {venc}, paga {total} por 100, {len(h)} días de historia")
    if info:
        with open(SAL / "instrumentos.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(info[0])); w.writeheader(); w.writerows(info)
    if filas:
        with open(SAL / "historico_tea.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(filas[0])); w.writeheader(); w.writerows(filas)
        # serie por plazo: promedio de la TEA de las letras que vencen entre 30 y 200 días, por fecha (A-24HS, con volumen alguno)
        por_dia = {}
        for f in filas:
            if f["plazo"] == "A-24HS" and 30 <= f["dias"] <= 200:
                por_dia.setdefault(f["fecha"], []).append(f["tea"])
        with open(SAL / "serie_plazo.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh); w.writerow(["fecha", "tea_prom_30_200d", "letras"])
            for d in sorted(por_dia):
                w.writerow([d, round(sum(por_dia[d]) / len(por_dia[d]), 2), len(por_dia[d])])
    diag(f"\nFilas de tasa: {len(filas)}")
    (SAL / "DIAGNOSTICO.md").write_text("\n".join(DIAG), encoding="utf-8")
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as fh:
            fh.write("\n".join(DIAG) + "\n")


if __name__ == "__main__":
    main()
