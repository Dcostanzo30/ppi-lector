"""Precios diarios para el semáforo de riesgo político: panel líder en pesos y Globales/Bonares en MEP, desde 2019 (PPI, solo REST).
Escribe estudios/historico/semaforo_precios.csv (ticker, fecha, cierre)."""
import os, time
from datetime import date
from pathlib import Path
import pandas as pd
from ppi_client.ppi import PPI

PANEL = ["ALUA", "BBAR", "BMA", "BYMA", "CEPU", "COME", "CRES", "ECOG", "EDN", "GGAL", "IRSA", "LOMA", "METR", "PAMP",
         "SUPV", "TECO2", "TGNO4", "TGSU2", "TRAN", "TXAR", "VALO", "YPFD"]
BONOS = ["AL30D", "GD30D", "AL35D", "GD35D", "GD38D", "AE38D", "AL41D", "GD41D", "GD46D"]
SAL = Path("estudios/historico/semaforo_precios.csv")

ppi = PPI(sandbox=False)
ppi.account.login_api(os.environ["PPI_API_KEY"].strip(), os.environ["PPI_API_SECRET"].strip())
filas = []
for lista, tipo in ((PANEL, "ACCIONES"), (BONOS, "BONOS")):
    for tk in lista:
        n = 0
        for y in range(2019, date.today().year + 1):
            try:
                r = ppi.marketdata.search(tk, tipo, "A-24HS", f"{y}-01-01", f"{y + 1}-01-01") or []
            except Exception as e:
                print(tk, y, "falló", str(e)[:80], flush=True); r = []
            for f in r:
                if f.get("price"): filas.append(dict(ticker=tk, fecha=str(f.get("date"))[:10], cierre=f.get("price"))); n += 1
            time.sleep(0.2)
        print(tk, n, flush=True)
pd.DataFrame(filas).drop_duplicates(["ticker", "fecha"]).sort_values(["ticker", "fecha"]).to_csv(SAL, index=False)
print("ok", len(filas), flush=True)
# FIN semaforo_datos.py
