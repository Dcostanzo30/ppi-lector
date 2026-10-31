"""Series para comparar reacciones del mercado a elecciones (PASO 2019, PASO 2023, legislativas 2025):
ADR en Nueva York desde 2018 (Yahoo), Merval en dólares (^MERV / CCL no se usa: se toman los ADR) y riesgo país diario
(argentinadatos, índice EMBI de JP Morgan). Solo consultas. Escribe estudios/historico/elecciones_*.csv"""
import json, urllib.request
from pathlib import Path
import pandas as pd
import yfinance as yf

SAL = Path("estudios/historico"); SAL.mkdir(parents=True, exist_ok=True)
ADR = ["GGAL", "BMA", "TGS", "YPF", "VIST", "TEO", "PAM", "SUPV", "EDN", "CRESY", "ARGT"]
d = yf.download(ADR, start="2018-06-01", auto_adjust=False, progress=False)
filas = []
for t in ADR:
    try:
        x = pd.DataFrame({"cierre": d["Close"][t], "ajustado": d["Adj Close"][t]}).dropna(subset=["cierre"])
        x["ticker"] = t; x.index.name = "fecha"; filas.append(x.reset_index()); print(t, len(x), flush=True)
    except Exception as e:
        print(t, "falló", e, flush=True)
pd.concat(filas).to_csv(SAL / "elecciones_adr.csv", index=False)
req = urllib.request.Request("https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais", headers={"User-Agent": "Mozilla/5.0"})
pd.DataFrame(json.load(urllib.request.urlopen(req, timeout=60))).to_csv(SAL / "riesgo_pais.csv", index=False)
print("riesgo país ok", flush=True)
# FIN elecciones.py
