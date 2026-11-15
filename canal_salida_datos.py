"""Datos diarios para el estudio del canal de salida (CCL) y el semáforo: dólar MEP (bolsa), CCL, oficial, mayorista, blue y
riesgo país. Desde el 15/11/2026 se leen de la capa de fuentes de ppi--datos (fuentes/*.csv), que es el único lugar que
consulta datos externos: MEP y CCL salen primero de nuestra cinta (AL30/AL30D y AL30C), mayorista del BCRA, riesgo país del
EMBI. Si la capa no está (corrida suelta sin clonar ppi--datos), se usa argentinadatos como antes.
Escribe estudios/historico/dolares_diarios.csv y riesgo_pais.csv, con el mismo formato de siempre."""
import json, urllib.request
import pandas as pd
from pathlib import Path

import fuentes_datos

SAL = Path("estudios/historico"); SAL.mkdir(parents=True, exist_ok=True)
CASAS = {"bolsa": "mep", "contadoconliqui": "ccl", "oficial": "oficial", "mayorista": "mayorista", "blue": "blue"}


def bajar(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return pd.DataFrame(json.load(urllib.request.urlopen(req, timeout=60)))


partes = []
for casa, dato in CASAS.items():
    s_ = fuentes_datos.serie(dato)
    if s_:
        partes.append(pd.Series(s_, name=casa)); print(casa, "fuentes", len(s_), max(s_), flush=True); continue
    try:                                                           # respaldo: solo si la capa de fuentes no está
        d = bajar(f"https://api.argentinadatos.com/v1/cotizaciones/dolares/{casa}")
        partes.append(d[["fecha", "venta"]].rename(columns={"venta": casa}).set_index("fecha")[casa])
        print(casa, "argentinadatos (respaldo)", len(d), flush=True)
    except Exception as e:
        print(casa, "falló", e, flush=True)
D = pd.concat(partes, axis=1).sort_index(); D.index.name = "fecha"
D.to_csv(SAL / "dolares_diarios.csv")
rp = fuentes_datos.serie("riesgo_pais")
if rp:
    pd.DataFrame({"fecha": list(rp), "valor": list(rp.values())}).sort_values("fecha").to_csv(SAL / "riesgo_pais.csv", index=False)
    print("riesgo país: fuentes", len(rp), max(rp), flush=True)
else:
    bajar("https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais").to_csv(SAL / "riesgo_pais.csv", index=False)
    print("riesgo país: argentinadatos (respaldo)", flush=True)
print("ok", flush=True)
# FIN canal_salida_datos.py
