"""Exploración (24/11/2026): busca en la API de series de datos.gob.ar las series mensuales de recaudación (ARCA / recursos
tributarios) y de gasto base caja del Sector Público Nacional (jubilaciones, remuneraciones, prestaciones sociales).
Solo imprime; no guarda nada."""
import requests
B = "https://apis.datos.gob.ar/series/api"
for q in ["recursos tributarios total", "recaudacion tributaria", "IVA neto de reintegros", "ganancias recaudacion",
          "seguridad social aportes contribuciones recaudacion", "derechos de exportacion",
          "base caja prestaciones sociales", "base caja jubilaciones y pensiones", "base caja remuneraciones",
          "base caja sector publico nacional gasto primario", "ahorro inversion financiamiento sector publico nacional"]:
    try:
        r = requests.get(f"{B}/search/", params={"q": q, "limit": 12}, timeout=30).json()
        print(f"\n### {q}  ({r.get('count')})")
        for x in r.get("data", []):
            f = x.get("field", {}); d = x.get("dataset", {})
            print(f"{f.get('id')} | {f.get('frequency')} | {f.get('time_index_start')}..{f.get('time_index_end')} | {f.get('description')} | {d.get('title')}")
    except Exception as e:
        print(q, "falló", e)
for u in ["https://www.arca.gob.ar/institucional/estudios/recaudacion-mensual/", "https://www.afip.gob.ar/institucional/estudios/serie-anual/"]:
    try:
        r = requests.get(u, timeout=30); print(u, r.status_code, len(r.text))
        import re; print(sorted(set(re.findall(r'href="([^"]+\.(?:xlsx?|csv|zip|pdf))"', r.text)))[:40])
    except Exception as e:
        print(u, "falló", e)
