"""¿Qué acciones del panel líder tienen línea en dólares MEP (D) y CCL (C) en PPI, y cuánto operan?
Solo consultas REST (no abre tiempo real ni toca la cuenta). Escribe estudios/lineas_dc.csv y un resumen en el log."""
import csv, os, time
from datetime import date, timedelta
from pathlib import Path
from ppi_client.ppi import PPI

PANEL = ["ALUA", "BBAR", "BMA", "BYMA", "CEPU", "COME", "CRES", "ECOG", "EDN", "GGAL", "IRSA", "LOMA", "METR", "PAMP",
         "SUPV", "TECO2", "TGNO4", "TGSU2", "TRAN", "TXAR", "VALO", "YPFD"]


def main():
    ppi = PPI(sandbox=False)
    ppi.account.login_api(os.environ["PPI_API_KEY"].strip(), os.environ["PPI_API_SECRET"].strip())
    hasta = date.today() + timedelta(days=1); desde = hasta - timedelta(days=30)
    filas = []
    for tk in PANEL:
        for suf, moneda in (("D", "MEP"), ("C", "CCL")):
            t = tk + suf
            f = dict(base=tk, ticker=t, moneda=moneda, existe=False, tipo="", ultimo="", ruedas_con_operaciones=0, volumen_medio="", ultima_fecha="")
            try:
                res = ppi.marketdata.search_instrument(t, "", "BYMA", "") or []
                ex = [r for r in res if str(r.get("ticker", "")).upper() == t]
                if ex:
                    f["existe"] = True; f["tipo"] = ex[0].get("type", "")
            except Exception as e:
                f["error"] = str(e)[:100]
            tipo = f["tipo"] or "ACCIONES"
            try:
                c = ppi.marketdata.current(t, tipo, "A-24HS") or {}
                f["ultimo"] = c.get("price", "")
                if c: f["existe"] = True
            except Exception:
                pass
            try:
                h = ppi.marketdata.search(t, tipo, "A-24HS", desde.isoformat(), hasta.isoformat()) or []
                vols = [float(x.get("volume") or 0) for x in h]
                f["ruedas_con_operaciones"] = sum(v > 0 for v in vols)
                f["volumen_medio"] = round(sum(vols) / len(vols), 1) if vols else ""
                f["ultima_fecha"] = max((str(x.get("date", ""))[:10] for x in h), default="")
                if h: f["existe"] = True
            except Exception:
                pass
            filas.append(f); print(f, flush=True); time.sleep(0.3)
    Path("estudios").mkdir(exist_ok=True)
    campos = ["base", "ticker", "moneda", "existe", "tipo", "ultimo", "ruedas_con_operaciones", "volumen_medio", "ultima_fecha", "error"]
    with open("estudios/lineas_dc.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, extrasaction="ignore"); w.writeheader(); w.writerows(filas)
    ok = [f for f in filas if f["existe"]]
    print(f"RESUMEN: {len(ok)} de {len(filas)} líneas existen; con operaciones en los últimos 30 días: "
          f"{sum(f['ruedas_con_operaciones'] > 0 for f in filas)}", flush=True)


if __name__ == "__main__":
    main()
# FIN lineas_dc.py
