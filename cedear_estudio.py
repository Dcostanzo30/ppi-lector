"""Estudio CEDEAR contra acción directa: baja el historial diario de PPI y de Nueva York y lo guarda para analizarlo.
- PPI (consulta histórica, no tiempo real): CEDEARs en pesos y en dólares, YPFD y los bonos AL30/AL30D/AL30C (MEP y CCL).
- Nueva York (Yahoo Finance): OXY, SPY, VIST, YPF.
Escribe estudios/cedear/historial_ppi.csv y estudios/cedear/historial_ny.csv. No opera: solo consulta.
Uso: python cedear_estudio.py [DESDE] [HASTA]   (por defecto los últimos 2 años)
"""
import csv, os, sys, time
from datetime import datetime, timedelta
from pathlib import Path

PPI_ESPECIES = [("OXY", "CEDEARS"), ("OXYD", "CEDEARS"), ("SPY", "CEDEARS"), ("SPYD", "CEDEARS"), ("SPYC", "CEDEARS"),
                ("VIST", "CEDEARS"), ("VISTD", "CEDEARS"), ("VISTC", "CEDEARS"), ("YPFD", "ACCIONES"), ("YPFDD", "ACCIONES"),
                ("AL30", "BONOS"), ("AL30D", "BONOS"), ("AL30C", "BONOS")]
NY = ["OXY", "SPY", "VIST", "YPF"]


def main():
    hasta = datetime.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else datetime.now()
    desde = datetime.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else hasta - timedelta(days=730)
    sal = Path("estudios/cedear"); sal.mkdir(parents=True, exist_ok=True)
    from ppi_client.ppi import PPI
    ppi = PPI(sandbox=False)
    ppi.account.login_api(os.environ["PPI_API_KEY"].strip(), os.environ["PPI_API_SECRET"].strip())
    filas = []
    for tk, tp in PPI_ESPECIES:
        for plazo in ("A-24HS", "INMEDIATA"):
            # de a tramos de 6 meses, por si PPI limita el rango
            d = desde
            while d < hasta:
                h = min(d + timedelta(days=180), hasta)
                time.sleep(0.4)
                try:
                    r = ppi.marketdata.search(tk, tp, plazo, d, h) or []
                except Exception as e:
                    print(f"{tk} {plazo} {d:%Y-%m-%d}: error {str(e)[:100]}", flush=True); r = []
                for x in r:
                    if isinstance(x, dict):
                        filas.append([tk, tp, plazo, str(x.get("date", ""))[:10], x.get("price"), x.get("openingPrice"), x.get("max"), x.get("min"), x.get("volume")])
                d = h
        print(f"{tk}: {sum(1 for f in filas if f[0] == tk)} filas", flush=True)
    with open(sal / "historial_ppi.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["ticker", "tipo", "plazo", "fecha", "cierre", "apertura", "maximo", "minimo", "monto"])
        w.writerows(sorted(set(tuple(map(str, f)) for f in filas)))
    import yfinance as yf
    ny = yf.download(NY, start=desde.strftime("%Y-%m-%d"), end=(hasta + timedelta(days=1)).strftime("%Y-%m-%d"), auto_adjust=False, progress=False)
    with open(sal / "historial_ny.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["ticker", "fecha", "cierre", "cierre_ajustado", "volumen"])
        for tk in NY:
            for fecha, fila in ny.xs(tk, axis=1, level=1).iterrows():
                if fila.get("Close") == fila.get("Close"):
                    w.writerow([tk, fecha.strftime("%Y-%m-%d"), fila.get("Close"), fila.get("Adj Close"), fila.get("Volume")])
    print("listo", flush=True)


if __name__ == "__main__":
    main()
# FIN cedear_estudio.py
