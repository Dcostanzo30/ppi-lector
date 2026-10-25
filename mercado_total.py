"""Cápsula Mercado Total: ¿qué parte del mercado de BYMA ven nuestras 37 especies?

1. Pide a PPI la lista de todos los instrumentos de cada tipo (acciones, bonos, letras, ONs, CEDEARs, cauciones, opciones...).
2. Para cada uno pide lo operado en el día indicado (consulta histórica diaria, no tiempo real).
3. Escribe mercado_total/FECHA.csv (una fila por instrumento y plazo) y un resumen por tipo con la proporción
   de las 37 que escucha el lector.
No opera ni toca la cuenta: solo consulta. Respeta el límite de PPI de 3.000 consultas cada 15 minutos.
Uso: python mercado_total.py [AAAA-MM-DD]   (sin fecha = el último día hábil)
"""
import csv, json, os, string, sys, time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from ppi_client.ppi import PPI

SALIDA_MD = os.environ.get("GITHUB_STEP_SUMMARY", "mercado_total.md")
PAUSA = 0.32                  # ~3 consultas por segundo: queda debajo de 3.000 cada 15 minutos
TOPE_MIN = float(os.environ.get("TOPE_MIN", "75"))   # minutos máximos de trabajo; si se pasa, guarda lo que tiene
PLAZOS = ["A-24HS", "INMEDIATA"]

# Lo que escucha el lector (mismo listado que lector.yml)
ACCIONES_37 = "ALUA,BBAR,BMA,BYMA,CEPU,COME,CRES,ECOG,EDN,GGAL,IRSA,LOMA,METR,PAMP,SUPV,TECO2,TGNO4,TGSU2,TRAN,TXAR,VALO,YPFD".split(",")
OTROS_37 = {("AL30", "BONOS"), ("AL30D", "BONOS"), ("AL30C", "BONOS"), ("GD30", "BONOS"), ("GD30D", "BONOS"), ("GD30C", "BONOS"),
            ("GD46", "BONOS"), ("GD46D", "BONOS"), ("SPY", "CEDEARS"), ("QQQ", "CEDEARS"), ("XLE", "CEDEARS"), ("USO", "CEDEARS"),
            ("EWZ", "CEDEARS"), ("GLD", "CEDEARS"), ("GGAL", "ACCIONES-USA")}
NUESTRAS = {(t, "ACCIONES") for t in ACCIONES_37} | OTROS_37

inicio = time.time()
consultas = 0


def escribir(t):
    print(t, flush=True)
    with open(SALIDA_MD, "a", encoding="utf-8") as fh:
        fh.write(t + "\n")


def pedir(fn, *a):
    global consultas
    time.sleep(PAUSA); consultas += 1
    try:
        return fn(*a)
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {str(e)[:120]}"}


def ultimo_habil():
    d = datetime.now().date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def tiempo_ok():
    return (time.time() - inicio) / 60 < TOPE_MIN


def nombre_tipo(t):
    if isinstance(t, dict):
        for k in ("value", "code", "name", "description", "id"):
            if t.get(k): return str(t[k])
    return str(t)


def main():
    fecha = sys.argv[1] if len(sys.argv) > 1 else ultimo_habil()
    ppi = PPI(sandbox=False)
    try:
        ppi.account.login_api(os.environ["PPI_API_KEY"].strip(), os.environ["PPI_API_SECRET"].strip())
    except Exception as e:
        escribir(f"# Mercado total\n\nNo se pudo ingresar a PPI: {type(e).__name__} {str(e)[:200]}"); return
    escribir(f"# Mercado total — {fecha}\n")

    # ---- 1. tipos y mercados
    tipos_raw = pedir(ppi.configuration.get_instrument_types)
    mercados_raw = pedir(ppi.configuration.get_markets)
    tipos = [nombre_tipo(t) for t in (tipos_raw if isinstance(tipos_raw, list) else [])]
    mercados = [nombre_tipo(m) for m in (mercados_raw if isinstance(mercados_raw, list) else [])]
    escribir(f"Tipos que informa PPI: {', '.join(tipos) or json.dumps(tipos_raw)[:300]}")
    escribir(f"Mercados: {', '.join(mercados) or json.dumps(mercados_raw)[:300]}\n")

    # ---- 2. listado de instrumentos por tipo
    instrumentos = {}            # (ticker, tipo) -> registro de PPI
    muestra = {}
    for tipo in tipos:
        if not tiempo_ok(): break
        res = pedir(ppi.marketdata.search_instrument, "", "", "BYMA", tipo)
        lista = res if isinstance(res, list) else []
        modo = "todo de una vez"
        if len(lista) < 20:                      # si la búsqueda vacía no lista todo, se busca por la primera letra
            modo = "por letra"
            for c in string.ascii_uppercase + string.digits:
                if not tiempo_ok(): break
                r = pedir(ppi.marketdata.search_instrument, c, "", "BYMA", tipo)
                if isinstance(r, list): lista += r
        n0 = len(instrumentos)
        for r in lista:
            if not isinstance(r, dict): continue
            tk = str(r.get("ticker", "")).strip().upper()
            tp = str(r.get("type") or tipo)
            if tk and (tk, tp) not in instrumentos:
                instrumentos[(tk, tp)] = r
                muestra.setdefault(tp, r)
        escribir(f"- {tipo}: {len(instrumentos) - n0} instrumentos ({modo})")
    escribir(f"\nTotal de instrumentos listados: {len(instrumentos)}\n")
    for tp, r in muestra.items():
        escribir(f"  ejemplo {tp}: {json.dumps(r, ensure_ascii=False, default=str)[:300]}")

    # ---- 3. lo operado en el día por instrumento (primero las nuestras, para tenerlas seguro)
    orden = sorted(instrumentos, key=lambda k: (k not in NUESTRAS, k[1], k[0]))
    d0 = datetime.fromisoformat(fecha)
    filas, campos = [], Counter()
    for tk, tp in orden:
        if not tiempo_ok():
            escribir(f"\n**Se cortó por tiempo** después de {len(filas)} instrumentos; el resto queda para la próxima corrida."); break
        for plazo in PLAZOS:
            r = pedir(ppi.marketdata.search, tk, tp, plazo, d0, d0 + timedelta(days=1))
            dias = r if isinstance(r, list) else []
            dia = next((x for x in dias if isinstance(x, dict) and str(x.get("date", ""))[:10] == fecha), None)
            if dia is None and dias and isinstance(dias[-1], dict): dia = dias[-1] if str(dias[-1].get("date", ""))[:10] == fecha else None
            if dia:
                campos.update(dia.keys())
                filas.append(dict(ticker=tk, tipo=tp, plazo=plazo, nuestra=(tk, tp) in NUESTRAS,
                                  datos=json.dumps(dia, ensure_ascii=False, default=str)))
        if len(filas) and len(filas) % 200 == 0:
            print(f"  {len(filas)} filas, {consultas} consultas, {(time.time()-inicio)/60:.1f} min", flush=True)

    # ---- 4. guardar
    Path("mercado_total").mkdir(exist_ok=True)
    claves = sorted(campos)
    with open(f"mercado_total/{fecha}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["ticker", "tipo", "plazo", "nuestra"] + claves)
        for f in filas:
            d = json.loads(f["datos"])
            w.writerow([f["ticker"], f["tipo"], f["plazo"], f["nuestra"]] + [d.get(k, "") for k in claves])
    with open(f"mercado_total/{fecha}_instrumentos.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["ticker", "tipo", "registro"])
        for (tk, tp), r in sorted(instrumentos.items()):
            w.writerow([tk, tp, json.dumps(r, ensure_ascii=False, default=str)])

    # ---- 5. resumen por tipo (monto = volume si PPI lo informa en pesos; se muestran los campos para revisarlo)
    escribir(f"\nCampos diarios que devuelve PPI: {', '.join(claves)}\n")
    def num(x):
        try: return float(x)
        except (TypeError, ValueError): return 0.0
    POR_100 = ("BONO", "LETRA", "OBLIGACION", "ON", "TITULO")       # cotizan por cada 100 de valor nominal
    tot = defaultdict(lambda: [0, 0, 0.0, 0.0])      # tipo -> [instrumentos con datos, nuestros, monto estimado total, monto de las 37]
    for f in filas:
        d = json.loads(f["datos"]); v = num(d.get("volume")); p = num(d.get("price"))
        monto = v * p / (100 if any(x in f["tipo"].upper() for x in POR_100) else 1)   # estimado: nominales × precio
        t = tot[f["tipo"]]; t[0] += 1; t[2] += monto
        if f["nuestra"]: t[1] += 1; t[3] += monto
    escribir("Monto estimado = volumen × precio (÷100 en bonos, letras y ONs). Es una primera aproximación: hay que confirmar qué informa PPI en \"volume\".\n")
    escribir("| Tipo | Instrumentos con datos | De las 37 | Monto estimado total | Monto de las 37 | Proporción |")
    escribir("|---|---|---|---|---|---|")
    for tp, (n, nn, v, vn) in sorted(tot.items(), key=lambda x: -x[1][2]):
        escribir(f"| {tp} | {n} | {nn} | {v:,.0f} | {vn:,.0f} | {vn / v:.1%} |" if v else f"| {tp} | {n} | {nn} | 0 | 0 | — |")
    V = sum(t[2] for t in tot.values()); VN = sum(t[3] for t in tot.values())
    sin_c = sum(t[2] for tp, t in tot.items() if "CAUC" not in tp.upper()); sin_cn = sum(t[3] for tp, t in tot.items() if "CAUC" not in tp.upper())
    if V:
        escribir(f"\nTotal: {V:,.0f}; de las 37: {VN:,.0f} ({VN / V:.1%}).")
        if sin_c: escribir(f"Sin cauciones: {sin_c:,.0f}; de las 37: {sin_cn:,.0f} ({sin_cn / sin_c:.1%}).")
    escribir(f"Consultas a PPI: {consultas}; minutos: {(time.time()-inicio)/60:.1f}.")

if __name__ == "__main__":
    main()
# FIN mercado_total.py
