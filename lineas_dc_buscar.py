"""Busca en PPI todas las variantes de ticker de las especies cuyas líneas D/C no aparecieron (solo REST)."""
import os
from ppi_client.ppi import PPI
ppi = PPI(sandbox=False); ppi.account.login_api(os.environ["PPI_API_KEY"].strip(), os.environ["PPI_API_SECRET"].strip())
for b in ["BMA", "TECO", "TGNO", "TGSU", "TGS", "LOMA", "SUPV", "TRAN", "TXAR"]:
    try:
        r = ppi.marketdata.search_instrument(b, "", "", "") or []
    except Exception as e:
        print(b, "error", str(e)[:100]); continue
    print(b, sorted({(x.get("ticker"), x.get("type"), x.get("market"), x.get("currency")) for x in r if str(x.get("ticker", "")).upper().startswith(b)}), flush=True)
# FIN lineas_dc_buscar.py
