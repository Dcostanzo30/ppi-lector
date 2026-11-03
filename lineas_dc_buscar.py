"""Liquidez de las líneas D/C con nombre distinto (BMA.D, BMA.C, TGSUD, TGSUC, TECOC). Solo REST."""
import os
from datetime import date, timedelta
from ppi_client.ppi import PPI
ppi = PPI(sandbox=False); ppi.account.login_api(os.environ["PPI_API_KEY"].strip(), os.environ["PPI_API_SECRET"].strip())
h1 = date.today() + timedelta(days=1); h0 = h1 - timedelta(days=30)
for t in ["BMA.D", "BMA.C", "TGSUD", "TGSUC", "TECOC", "TECOD", "TGNOD", "TGNOC"]:
    try:
        h = ppi.marketdata.search(t, "ACCIONES", "A-24HS", h0.isoformat(), h1.isoformat()) or []
        v = [float(x.get("volume") or 0) for x in h]
        print("LIQ", t, len(h), sum(x > 0 for x in v), round(sum(v) / len(v), 1) if v else None, h[-1].get("price") if h else None, flush=True)
    except Exception as e:
        print("LIQ", t, "error", str(e)[:100], flush=True)
# FIN lineas_dc_buscar.py
