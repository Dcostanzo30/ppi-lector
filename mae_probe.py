"""Exploración del sitio público de datos de A3 (marketdata.mae.com.ar). Solo lectura de páginas públicas.

La página se arma con JavaScript, así que no se puede leer como texto. Este script abre el sitio con un navegador sin pantalla,
recorre las secciones que encuentra en el menú y anota qué direcciones de datos (JSON) consulta cada una, con una muestra de lo que devuelven.
Con eso se arma después el lector definitivo (cauciones por plazo, futuros y, si existen, opciones sobre dólar).

Salida: estudios/mae/PROBE.md
"""
import json, re, sys
from datetime import datetime
from pathlib import Path

BASE = "https://marketdata.mae.com.ar"
SEMILLAS = ["/", "/cauciones/historico", "/futuros", "/futuros/historico", "/opciones", "/derivados", "/forex", "/renta-fija", "/estadisticas"]
SAL = Path("estudios/mae"); SAL.mkdir(parents=True, exist_ok=True)
OUT = [f"# Exploración marketdata.mae.com.ar — {datetime.now():%Y-%m-%d %H:%M}\n"]


def w(t):
    print(t, flush=True)
    OUT.append(t)


def visitar(ctx, ruta, vistos):
    page = ctx.new_page()
    llamadas = []

    def on_resp(r):
        try:
            ct = r.headers.get("content-type", "")
            if r.request.resource_type in ("xhr", "fetch") or "json" in ct:
                cuerpo = ""
                try:
                    cuerpo = r.text()[:400].replace("\n", " ")
                except Exception:
                    pass
                llamadas.append((r.request.method, r.url, r.status, cuerpo))
        except Exception:
            pass

    page.on("response", on_resp)
    url = BASE + ruta
    w(f"\n## {url}")
    try:
        page.goto(url, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(4000)
    except Exception as e:
        w(f"- No cargó del todo: {type(e).__name__} {str(e)[:120]}")
    try:
        w(f"- Título: {page.title()}")
        texto = page.inner_text("body")[:1500].replace("\n", " | ")
        w(f"- Texto visible (inicio): {texto}")
        enlaces = page.eval_on_selector_all("a[href]", "els => els.map(e => [e.innerText.trim(), e.getAttribute('href')])")
        internos = [(t, h) for t, h in enlaces if h and h.startswith("/")]
        w(f"- Enlaces internos: {internos[:40]}")
        for t, h in internos:
            vistos.add(h)
    except Exception as e:
        w(f"- Error leyendo la página: {type(e).__name__} {str(e)[:120]}")
    w(f"- Llamadas de datos ({len(llamadas)}):")
    for m, u, s, c in llamadas[:25]:
        w(f"  - {m} {u} -> {s} :: {c[:300]}")
    page.close()


def main():
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        w(f"Playwright no disponible: {e}")
        (SAL / "PROBE.md").write_text("\n".join(OUT), encoding="utf-8")
        return
    vistos = set()
    with sync_playwright() as p:
        nav = p.chromium.launch()
        ctx = nav.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) Chrome/120 Safari/537.36", locale="es-AR")
        hechos = set()
        for ruta in SEMILLAS:
            visitar(ctx, ruta, vistos)
            hechos.add(ruta)
        extra = [h for h in sorted(vistos) if h not in hechos and not re.search(r"\.(png|jpg|svg|css|js|ico)$", h)][:15]
        for ruta in extra:
            visitar(ctx, ruta, vistos)
        nav.close()
    (SAL / "PROBE.md").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
