"""Explorador de PPI: averigua qué instrumentos y mercados ofrece la API (¿hay EE.UU.? ¿CEDEARs? ¿bonos?)
y prueba durante 90 segundos si llegan precios en tiempo real. No opera ni toca la cuenta: solo consulta."""
import os, sys, threading, time, json
from collections import Counter
from ppi_client.ppi import PPI
from ppi_client.models.instrument import Instrument

SALIDA = os.environ.get("GITHUB_STEP_SUMMARY", "explorar.md")
BUSCAR = ["SPY", "QQQ", "EWZ", "XLE", "GLD", "USO", "TLT", "AAPL", "NVDA", "GGAL", "YPF", "VIX",
          "GD30", "GD30D", "GD30C", "AL30", "AL30D", "AL30C", "GD46", "GD46D"]


def escribir(t):
    print(t, flush=True)
    with open(SALIDA, "a", encoding="utf-8") as fh:
        fh.write(t + "\n")


def corto(x, n=400):
    s = json.dumps(x, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[:n] + "…"


def main():
    ppi = PPI(sandbox=False)
    try:
        ppi.account.login_api(os.environ["PPI_API_KEY"].strip(), os.environ["PPI_API_SECRET"].strip())
        escribir("# Explorador de PPI\n\nIngreso correcto.\n")
    except Exception as e:
        escribir(f"# Explorador de PPI\n\nNo se pudo ingresar: {type(e).__name__} {str(e)[:200]}")
        return

    escribir("## 1. Qué ofrece la API\n")
    for nombre, fn in [("Tipos de instrumento", ppi.configuration.get_instrument_types),
                       ("Mercados", ppi.configuration.get_markets),
                       ("Plazos de liquidación", ppi.configuration.get_settlements)]:
        try:
            escribir(f"- **{nombre}**: {corto(fn(), 1500)}")
        except Exception as e:
            escribir(f"- **{nombre}**: error {type(e).__name__} {str(e)[:150]}")

    escribir("\n## 2. Búsqueda de símbolos\n")
    encontrados = []
    for tk in BUSCAR:
        try:
            res = ppi.marketdata.search_instrument(tk, "", "", "") or []
        except Exception as e:
            escribir(f"- {tk}: error {type(e).__name__} {str(e)[:120]}")
            continue
        exactos = [r for r in res if str(r.get("ticker", "")).upper() == tk]
        escribir(f"- **{tk}**: {len(res)} resultados; exactos: {corto(exactos[:4], 600)}")
        for r in exactos[:3]:
            encontrados.append((tk, r.get("type"), r.get("market")))

    escribir("\n## 3. Precio actual de lo encontrado\n")
    candidatos = []
    for tk, tipo, mercado in encontrados:
        for plazo in ("A-24HS", "INMEDIATA"):
            try:
                c = ppi.marketdata.current(tk, tipo, plazo)
                escribir(f"- {tk} / {tipo} / {mercado} / {plazo}: {corto(c, 300)}")
                if c:
                    candidatos.append((tk, tipo, plazo))
                break
            except Exception as e:
                escribir(f"- {tk} / {tipo} / {plazo}: error {str(e)[:100]}")

    escribir("\n## 4. Tiempo real durante 90 segundos\n")
    if not candidatos:
        escribir("Nada para suscribir.")
        return
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from lector import preparar_login_tiempo_real
    preparar_login_tiempo_real(ppi)
    cuenta = Counter()
    ejemplo = {}

    def al_conectar():
        for tk, tipo, plazo in candidatos:
            try:
                ppi.realtime.subscribe_to_element(Instrument(tk, tipo, plazo))
            except Exception as e:
                escribir(f"- no se pudo suscribir {tk} {tipo} {plazo}: {e}")

    def al_recibir(m):
        try:
            d = json.loads(m) if isinstance(m, str) else m
            if isinstance(d, str):
                d = json.loads(d)
            tk = d.get("Ticker", "?")
        except Exception:
            tk = "?"
            d = m
        cuenta[tk] += 1
        ejemplo.setdefault(tk, d)

    def terminar():
        escribir("| Símbolo | Mensajes en 90 s |\n|---|---|")
        for tk, tipo, plazo in candidatos:
            escribir(f"| {tk} ({tipo}, {plazo}) | {cuenta.get(tk, 0)} |")
        for tk, d in list(ejemplo.items())[:6]:
            escribir(f"\nEjemplo {tk}: {corto(d, 500)}")
        os._exit(0)

    threading.Timer(90, terminar).start()
    try:
        ppi.realtime.connect_to_market_data(al_conectar, lambda: None, al_recibir)
        ppi.realtime.start_connections()
    except Exception as e:
        escribir(f"No se pudo conectar al tiempo real: {e}")
        os._exit(0)


if __name__ == "__main__":
    main()
