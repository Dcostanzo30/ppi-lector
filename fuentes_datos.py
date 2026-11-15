"""Lectura de la capa de fuentes de ppi--datos (fuentes/*.csv), para que los estudios de ppi-lector no consulten afuera
lo que el sistema ya baja en un solo lugar. El workflow clona ppi--datos (solo fuentes/) en la carpeta "datos".
serie(dato) -> {fecha 'AAAA-MM-DD': valor}; None si la capa no está (el que llama decide qué hacer).
"""
import csv
from pathlib import Path

RAIZ = Path("datos/fuentes")


def serie(dato):
    p = RAIZ / f"{dato}.csv"
    if not p.exists(): return None
    out = {}
    with open(p, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try: out[r["fecha"][:10]] = float(r["valor"])
            except (TypeError, ValueError): continue
    return out
# FIN fuentes_datos.py
