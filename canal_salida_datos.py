"""Datos diarios para el estudio del canal de salida (CCL): dólar MEP (bolsa), CCL, oficial y riesgo país (argentinadatos).
Solo consultas. Escribe estudios/historico/dolares_diarios.csv y riesgo_pais.csv."""
import json, urllib.request
import pandas as pd
from pathlib import Path

SAL = Path("estudios/historico"); SAL.mkdir(parents=True, exist_ok=True)


def bajar(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return pd.DataFrame(json.load(urllib.request.urlopen(req, timeout=60)))


partes = []
for casa in ("bolsa", "contadoconliqui", "oficial", "mayorista", "blue"):
    try:
        d = bajar(f"https://api.argentinadatos.com/v1/cotizaciones/dolares/{casa}")
        partes.append(d[["fecha", "venta"]].rename(columns={"venta": casa}).set_index("fecha"))
        print(casa, len(d), d.fecha.min(), d.fecha.max(), flush=True)
    except Exception as e:
        print(casa, "falló", e, flush=True)
pd.concat(partes, axis=1).sort_index().to_csv(SAL / "dolares_diarios.csv")
bajar("https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais").to_csv(SAL / "riesgo_pais.csv", index=False)
print("ok", flush=True)
# FIN canal_salida_datos.py
