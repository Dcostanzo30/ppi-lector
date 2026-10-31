"""Historial largo (desde 2022) de algunas acciones, para ubicarlas contra sus máximos y mínimos en moneda comparable.
Baja: precios diarios de BYMA (Yahoo .BA y PPI, para cruzarlos), los ADR en Nueva York (dólares), la inflación mensual
(INDEC vía argentinadatos) y el dólar contado con liquidación diario (argentinadatos). Solo consultas.
Escribe estudios/historico/*.csv
"""
import json, os, urllib.request
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

SAL = Path("estudios/historico"); SAL.mkdir(parents=True, exist_ok=True)
LOCALES = {"GGAL": "ACCIONES", "BMA": "ACCIONES", "TGSU2": "ACCIONES", "YPFD": "ACCIONES", "VIST": "CEDEARS"}
ADR = ["GGAL", "BMA", "TGS", "YPF", "VIST"]
DESDE = "2022-01-01"


def api(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def main():
    # inflación mensual y CCL
    for nombre, url in (("inflacion_mensual", "https://api.argentinadatos.com/v1/finanzas/indices/inflacion"),
                        ("ccl", "https://api.argentinadatos.com/v1/cotizaciones/dolares/contadoconliqui")):
        try:
            pd.DataFrame(api(url)).to_csv(SAL / f"{nombre}.csv", index=False); print(nombre, "ok", flush=True)
        except Exception as e:
            print(nombre, "falló", e, flush=True)
    # Yahoo: locales .BA y ADR
    import yfinance as yf
    tick = [f"{t}.BA" for t in LOCALES] + ADR
    d = yf.download(tick, start=DESDE, auto_adjust=False, progress=False, actions=True)
    filas = []
    for t in tick:
        try:
            x = pd.DataFrame({"cierre": d["Close"][t], "ajustado": d["Adj Close"][t], "maximo": d["High"][t], "minimo": d["Low"][t],
                              "volumen": d["Volume"][t], "dividendos": d["Dividends"][t] if "Dividends" in d else 0,
                              "splits": d["Stock Splits"][t] if "Stock Splits" in d else 0}).dropna(subset=["cierre"])
            x["ticker"] = t; x.index.name = "fecha"; filas.append(x.reset_index())
            print(t, len(x), flush=True)
        except Exception as e:
            print(t, "falló", e, flush=True)
    pd.concat(filas).to_csv(SAL / "yahoo.csv", index=False)
    # PPI (diario oficial de BYMA, 24 hs), por años
    try:
        from ppi_client.ppi import PPI
        ppi = PPI(sandbox=False); ppi.account.login_api(os.environ["PPI_API_KEY"], os.environ["PPI_API_SECRET"])
        filas = []
        for tk, tipo in LOCALES.items():
            a = date(2022, 1, 1)
            while a <= date.today():
                b = min(date(a.year, 12, 31), date.today())
                try:
                    r = ppi.marketdata.search(tk, tipo, "A-24HS", a.isoformat(), b.isoformat()) or []
                    for f in r:
                        filas.append(dict(ticker=tk, fecha=str(f.get("date"))[:10], cierre=f.get("price"), apertura=f.get("openingPrice"),
                                          maximo=f.get("max"), minimo=f.get("min"), volumen=f.get("volume")))
                except Exception as e:
                    print(tk, a.year, "PPI falló", e, flush=True)
                a = date(a.year + 1, 1, 1)
            print(tk, "PPI", sum(1 for f in filas if f["ticker"] == tk), flush=True)
        pd.DataFrame(filas).to_csv(SAL / "ppi.csv", index=False)
    except Exception as e:
        print("PPI no disponible", e, flush=True)


if __name__ == "__main__":
    main()
# FIN historial_largo.py
