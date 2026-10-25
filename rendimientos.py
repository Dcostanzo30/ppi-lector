"""Rendimientos: TIR, paridad y duración de bonos, letras y ONs operados en un día, con la calculadora de PPI.
Lee mercado_total/FECHA.csv (precios del día) y FECHA_instrumentos.csv, y escribe mercado_total/FECHA_rendimientos.csv
con la respuesta completa de PPI para cada especie (una fila por especie y moneda, al precio de cierre A-24HS).
No opera ni toca la cuenta: solo consulta la calculadora. Uso: python rendimientos.py AAAA-MM-DD
"""
import csv, json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from ppi_client.ppi import PPI
from ppi_client.models.estimate_bonds import EstimateBonds

TIPOS = {"BONOS", "LETRAS", "ON"}
HILOS, POR_SEGUNDO = 3, 3.0
_lock = threading.Lock(); _ult = [0.0]


def ritmo():
    with _lock:
        e = _ult[0] + 1 / POR_SEGUNDO - time.time()
        if e > 0: time.sleep(e)
        _ult[0] = time.time()


def main():
    fecha = sys.argv[1]
    inst = {}
    with open(f"mercado_total/{fecha}_instrumentos.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh): inst[(r["ticker"], r["tipo"])] = json.loads(r["registro"])
    pedidos = {}
    with open(f"mercado_total/{fecha}.csv", encoding="utf-8") as fh:
        for f in csv.DictReader(fh):
            if f["tipo"] in TIPOS and f["price"] and float(f["price"]) > 0 and float(f["volume"] or 0) > 0:
                k = (f["ticker"], f["tipo"])
                if k not in pedidos or f["plazo"] == "A-24HS": pedidos[k] = (float(f["price"]), float(f["volume"]), f["plazo"])
    ppis = []
    for _ in range(HILOS):
        p = PPI(sandbox=False); p.account.login_api(os.environ["PPI_API_KEY"].strip(), os.environ["PPI_API_SECRET"].strip()); ppis.append(p)
    tipos_cant = ppis[0].configuration.get_quantity_types()
    print("Tipos de cantidad:", json.dumps(tipos_cant, ensure_ascii=False)[:300], flush=True)
    qt = "PAPELES"
    for t in tipos_cant or []:
        v = json.dumps(t, ensure_ascii=False).upper()
        if "PAPEL" in v or "NOMINAL" in v:
            qt = t.get("value") if isinstance(t, dict) and t.get("value") else qt
            break
    d = datetime.fromisoformat(fecha)
    filas, lock = [], threading.Lock()

    def uno(args):
        i, (k, (precio, monto, plazo)) = args
        ritmo()
        try:
            r = ppis[i % HILOS].marketdata.estimate_bonds(EstimateBonds(ticker=k[0], date=d, quantityType=qt, price=precio, quantity=100))
            err = ""
        except Exception as e:
            r, err = None, f"{type(e).__name__}: {str(e)[:150]}"
        reg = inst.get(k, {})
        with lock:
            filas.append([k[0], k[1], reg.get("currency", ""), reg.get("description", ""), reg.get("isin", ""), plazo, precio, monto,
                          json.dumps(r, ensure_ascii=False, default=str) if r is not None else "", err])

    with ThreadPoolExecutor(HILOS) as ex: list(ex.map(uno, enumerate(sorted(pedidos.items()))))
    with open(f"mercado_total/{fecha}_rendimientos.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["ticker", "tipo", "moneda", "descripcion", "isin", "plazo", "precio", "monto", "calculadora", "error"])
        for f in sorted(filas): w.writerow(f)
    ok = sum(1 for f in filas if f[8])
    print(f"Rendimientos: {ok} de {len(filas)} especies con respuesta de la calculadora", flush=True)
    ej = next((f for f in filas if f[8]), None)
    if ej: print("Ejemplo:", ej[0], ej[8][:600], flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(f"# Rendimientos {fecha}\n\n{ok} de {len(filas)} especies con respuesta.\n\nEjemplo: `{(ej or ['', '', '', '', '', '', '', '', ''])[8][:800]}`\n")


if __name__ == "__main__":
    main()
# FIN rendimientos.py
