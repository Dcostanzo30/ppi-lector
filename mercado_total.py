"""Cápsula Mercado Total: ¿qué parte del mercado de BYMA ven nuestras 37 especies?

1. Lista (una sola vez por fecha) todos los instrumentos de PPI por tipo y la guarda en mercado_total/FECHA_instrumentos.csv.
2. Para cada instrumento pide lo operado ese día, en los plazos A-24HS e INMEDIATA (consulta histórica diaria,
   no tiempo real). Es retomable: lo ya consultado queda en mercado_total/FECHA.csv y la corrida siguiente sigue
   desde donde quedó. Usa 3 conexiones en paralelo sin pasar el límite de PPI (3.000 consultas cada 15 minutos).
3. Escribe mercado_total/FECHA_resumen.md con tres capas:
   - activos con libro (acciones, bonos, letras, ONs, CEDEARs): proporción de las 37, en pesos;
   - opciones asignadas a su acción subyacente (monto en primas);
   - cauciones (mercado de dinero) por moneda y plazo, aparte.
"volume" de PPI es el MONTO operado en la moneda del instrumento (verificado contra la cinta del 23/10);
lo que está en dólares se pasa a pesos con el MEP o el CCL implícito del día (AL30/AL30D y AL30/AL30C).
No opera ni toca la cuenta: solo consulta.
Uso: python mercado_total.py [AAAA-MM-DD]   (sin fecha = el último día hábil)
Al terminar imprime QUEDAN=n (instrumentos sin consultar) para que el workflow sepa si debe seguir.
"""
import csv, shutil, json, os, re, string, sys, threading, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
try:
    from ppi_client.ppi import PPI
except ImportError:          # para rehacer el resumen sin el cliente de PPI
    PPI = None

TOPE_MIN = float(os.environ.get("TOPE_MIN", "75"))
MODO = os.environ.get("MODO", "rapido")      # rapido: BYMADATA para todo lo que operó + PPI solo para lo nuestro, letras y cauciones; completo: barrido PPI de todo, por liquidez
BYMA_BASE = "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free/"
BYMA_PANELES = {"leading-equity": "ACCIONES", "general-equity": "ACCIONES", "cedears": "CEDEARS", "public-bonds": "BONOS",
                "negociable-obligations": "ON", "options": "OPCIONES"}
MONEDA_BYMA = {"ARS": "Pesos", "USD": "Dólares MEP", "EXT": "Dólares CCL"}
HILOS = 3
POR_SEGUNDO = 3.0
PLAZOS = ["A-24HS", "INMEDIATA"]
SALTEAR = {"FCI", "FCI-EXTERIOR", "LICITACIONES", "LEBACS"}            # no se operan en el mercado secundario de BYMA
PRIORIDAD = ["ACCIONES", "CAUCIONES", "OPCIONES", "CEDEARS", "LETRAS", "BONOS", "ON", "ACCIONES-USA"]
ACCIONES_37 = "ALUA,BBAR,BMA,BYMA,CEPU,COME,CRES,ECOG,EDN,GGAL,IRSA,LOMA,METR,PAMP,SUPV,TECO2,TGNO4,TGSU2,TRAN,TXAR,VALO,YPFD".split(",")
OTROS_37 = {("AL30", "BONOS"), ("AL30D", "BONOS"), ("AL30C", "BONOS"), ("GD30", "BONOS"), ("GD30D", "BONOS"), ("GD30C", "BONOS"),
            ("GD46", "BONOS"), ("GD46D", "BONOS"), ("SPY", "CEDEARS"), ("QQQ", "CEDEARS"), ("XLE", "CEDEARS"), ("USO", "CEDEARS"),
            ("EWZ", "CEDEARS"), ("GLD", "CEDEARS"), ("GGAL", "ACCIONES-USA")}
NUESTRAS = {(t, "ACCIONES") for t in ACCIONES_37} | OTROS_37
CON_LIBRO = ["ACCIONES", "BONOS", "LETRAS", "ON", "CEDEARS"]
inicio = time.time()
_lock = threading.Lock(); _ultimo = [0.0]; consultas = [0]


def ritmo():
    with _lock:
        espera = _ultimo[0] + 1 / POR_SEGUNDO - time.time()
        if espera > 0: time.sleep(espera)
        _ultimo[0] = time.time(); consultas[0] += 1


def tiempo_ok():
    return (time.time() - inicio) / 60 < TOPE_MIN


def byma_foto():
    """Todo lo que operó hoy en BYMA según BYMADATA (datos abiertos): pocas consultas, segundos. Devuelve filas por especie y plazo."""
    import requests
    H = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0", "Origin": "https://open.bymadata.com.ar", "Referer": "https://open.bymadata.com.ar/"}
    base = {"excludeZeroPxAndQty": True, "T2": True, "T1": False, "T0": False}
    out = []
    for ep, tipo in BYMA_PANELES.items():
        lista = []
        for cuerpo in (base, {**base, "T1": True}, {**base, "T0": True, "T1": True}):
            try:
                r = requests.post(BYMA_BASE + ep, json=cuerpo, headers=H, timeout=60)
                d = r.json() if r.content else {}
                lista = d.get("data", d) if isinstance(d, dict) else d
                if isinstance(lista, list) and lista: break
            except Exception as e:
                print(f"::warning::BYMADATA {ep}: {str(e)[:120]}", flush=True)
        for x in lista or []:
            pl = {"2": "A-24HS", "1": "INMEDIATA"}.get(str(x.get("settlementType")))
            if not pl or not x.get("symbol"): continue
            out.append(dict(ticker=str(x["symbol"]).strip().upper(), tipo=tipo, plazo=pl, moneda=MONEDA_BYMA.get(x.get("denominationCcy"), x.get("denominationCcy")),
                            price=x.get("closingPrice") or x.get("trade") or 0, volume=x.get("volumeAmount") or 0, openingPrice=x.get("openingPrice") or 0,
                            max=x.get("tradingHighPrice") or 0, min=x.get("tradingLowPrice") or 0, operaciones=x.get("numberOfOrders") or 0))
        print(f"BYMADATA {ep}: {len(lista or [])} filas", flush=True)
    return out


def liquidos(fecha, dias=20):
    """Instrumentos que operaron algo en las últimas fotos (PPI o BYMA): van primero en la fila."""
    vivos = set()
    for f in sorted(Path("mercado_total").glob("????-??-??.csv"))[-dias:]:
        if f.stem >= fecha: continue
        for r in csv.DictReader(open(f, encoding="utf-8")):
            try:
                if float(r.get("volume") or 0) > 0: vivos.add((r["ticker"], r["tipo"]))
            except ValueError: pass
    return vivos


def anillo2():
    out = set()
    if Path("universo.csv").exists():
        for r in csv.DictReader(open("universo.csv", encoding="utf-8")):
            if r.get("anillo") in ("nucleo", "2"): out.add((r["ticker"], r["tipo"]))
    return out


def ultimo_habil():
    d = datetime.now().date() - (timedelta(days=0) if datetime.now().hour >= 18 else timedelta(days=1))
    while d.weekday() >= 5: d -= timedelta(days=1)
    return d.isoformat()


def ingresar():
    p = PPI(sandbox=False)
    p.account.login_api(os.environ["PPI_API_KEY"].strip(), os.environ["PPI_API_SECRET"].strip())
    return p


def nombre(t):
    if isinstance(t, dict):
        for k in ("value", "code", "name", "description", "id"):
            if t.get(k): return str(t[k])
    return str(t)


def listar(ppi, ruta):
    tipos = [nombre(t) for t in (ppi.configuration.get_instrument_types() or [])]
    inst = {}
    for tipo in tipos:
        if tipo in SALTEAR: continue
        # Desde el 26/10/2026 PPI exige ticker y nombre no vacíos: si la lista completa falla, se arma por prefijos (letra/dígito en ticker y nombre)
        ritmo()
        try: lista = ppi.marketdata.search_instrument("", "", "BYMA", tipo) or []
        except Exception: lista = []
        if len(lista) < 20:
            for c in string.ascii_uppercase + string.digits:
                for tk_, nm_ in ((c, ""), (c, c)):
                    ritmo()
                    try: r = ppi.marketdata.search_instrument(tk_, nm_, "BYMA", tipo)
                    except Exception: r = None
                    if isinstance(r, list):
                        lista += r
                        break
        for r in lista:
            if isinstance(r, dict) and r.get("ticker"):
                inst.setdefault((str(r["ticker"]).strip().upper(), str(r.get("type") or tipo)), r)
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["ticker", "tipo", "registro"])
        for (tk, tp), r in sorted(inst.items()): w.writerow([tk, tp, json.dumps(r, ensure_ascii=False, default=str)])


def sumar_al_padron(inst, fecha, ruta="universo.csv"):
    """Los instrumentos que PPI lista por primera vez entran al padrón en el anillo 3 (foto diaria)."""
    if not Path(ruta).exists(): return
    with open(ruta, encoding="utf-8") as fh:
        r = csv.DictReader(fh); cols = r.fieldnames; filas = list(r)
    hay = {(f["ticker"], f["tipo"]) for f in filas}
    nuevos = []
    for (tk, tp), reg in inst.items():
        if (tk, tp) in hay: continue
        c = str(reg.get("currency", "Pesos")); d = {k: "" for k in cols}
        d.update(ticker=tk, tipo=tp, plazo="A-24HS", anillo="3", desde=fecha, motivo="Nuevo en el listado de PPI",
                 moneda="MEP" if "MEP" in c else "CCL" if "CCL" in c else "ARS")
        if tp == "OPCIONES":
            m = re.search(r"Opci[oó]n (compra|venta) (\S+) AR\$ ([\d.]+) Vto\. (\d\d/\d\d/\d{4})", reg.get("description", ""))
            if m: d.update(subyacente=m.group(2), opcion="call" if m.group(1) == "compra" else "put", ejercicio=m.group(3), vencimiento=m.group(4))
        nuevos.append(d)
    if nuevos:
        with open(ruta, "a", newline="", encoding="utf-8") as fh: csv.DictWriter(fh, fieldnames=cols).writerows(nuevos)
        print(f"padrón: {len(nuevos)} instrumentos nuevos al anillo 3", flush=True)


def main():
    fecha = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else ultimo_habil()
    Path("mercado_total").mkdir(exist_ok=True)
    r_inst, r_dat, r_hecho = (Path(f"mercado_total/{fecha}{x}") for x in ("_instrumentos.csv", ".csv", "_consultados.txt"))
    ppis = [ingresar() for _ in range(HILOS)]
    if not r_inst.exists():
        try:
            listar(ppis[0], r_inst)
            n = sum(1 for _ in open(r_inst, encoding="utf-8")) - 1
        except Exception as e:
            print(f"::warning::listado de instrumentos falló: {str(e)[:150]}", flush=True); n = 0
        if n < 500:      # listado vacío o recortado: se usa el último listado completo (el catálogo cambia poco de un día a otro)
            prev = sorted(p for p in Path("mercado_total").glob("*_instrumentos.csv") if p != r_inst)
            if prev:
                print(f"::warning::listado de hoy con {n} instrumentos; se usa {prev[-1].name}", flush=True)
                shutil.copy(prev[-1], r_inst)
    inst = {}
    with open(r_inst, encoding="utf-8") as fh:
        for f in csv.DictReader(fh):
            if f["tipo"] not in SALTEAR: inst[(f["ticker"], f["tipo"])] = json.loads(f["registro"])
    sumar_al_padron(inst, fecha)
    hecho = set(r_hecho.read_text(encoding="utf-8").splitlines()) if r_hecho.exists() else set()
    if r_dat.exists() and not hecho:      # corrida vieja sin registro de consultados: cuenta como hecho lo que tiene datos
        with open(r_dat, encoding="utf-8") as fh: hecho = {f"{f['ticker']}|{f['tipo']}" for f in csv.DictReader(fh)}
    # BYMADATA: solo sirve para el día en curso (muestra la última rueda); para fechas viejas no se usa
    byma = byma_foto() if fecha == ultimo_habil() else []
    vivos_hoy = {(b["ticker"], b["tipo"]) for b in byma if float(b["volume"] or 0) > 0}
    vivos = vivos_hoy | liquidos(fecha)
    propias = NUESTRAS | anillo2()
    pend = [k for k in inst if f"{k[0]}|{k[1]}" not in hecho]
    if MODO == "rapido" and byma:
        # rápido: PPI solo para lo nuestro (núcleo y anillo 2), letras y cauciones (BYMADATA no las da); el resto lo da BYMADATA
        pend = [k for k in pend if k in propias or k[1] in ("LETRAS", "CAUCIONES")]
    # la fila por liquidez: lo nuestro, lo que operó hoy o en las últimas fotos, y al final lo que no opera
    pend.sort(key=lambda k: (k not in propias, k not in vivos, PRIORIDAD.index(k[1]) if k[1] in PRIORIDAD else 99, k[0]))
    print(f"{fecha}: modo {MODO}; {len(inst)} instrumentos, {len(hecho)} ya consultados, {len(pend)} pendientes en PPI; BYMADATA {len(byma)} filas", flush=True)
    d0 = datetime.fromisoformat(fecha)
    campos = ["date", "price", "volume", "openingPrice", "max", "min", "previousClose", "marketChange", "marketChangePercent"]
    if r_dat.exists():          # deja el archivo con las columnas en el orden de esta versión
        viejas = list(csv.DictReader(open(r_dat, encoding="utf-8")))
        cab = ["ticker", "tipo", "plazo", "nuestra"] + campos + ["fuente", "moneda"]
        if viejas and list(viejas[0].keys()) != cab:
            with open(r_dat, "w", newline="", encoding="utf-8") as fh:
                ww = csv.writer(fh); ww.writerow(cab)
                for f in viejas: ww.writerow([f.get(c, "") for c in cab])
    nuevo = not r_dat.exists()
    fh_d = open(r_dat, "a", newline="", encoding="utf-8"); w = csv.writer(fh_d)
    if nuevo: w.writerow(["ticker", "tipo", "plazo", "nuestra"] + campos + ["fuente", "moneda"])
    fh_h = open(r_hecho, "a", encoding="utf-8")
    if nuevo is False and not r_hecho.stat().st_size and hecho: fh_h.write("\n".join(sorted(hecho)) + "\n")
    lock_w = threading.Lock()

    def uno(args):
        i, (tk, tp) = args
        if not tiempo_ok(): return
        ppi = ppis[i % HILOS]; filas = []
        for plazo in PLAZOS:
            ritmo()
            try: r = ppi.marketdata.search(tk, tp, plazo, d0, d0 + timedelta(days=1))
            except Exception: r = None
            dia = next((x for x in (r or []) if isinstance(x, dict) and str(x.get("date", ""))[:10] == fecha), None)
            if dia: filas.append([tk, tp, plazo, (tk, tp) in NUESTRAS] + [dia.get(c, "") for c in campos] + ["PPI", ""])
        with lock_w:
            for f in filas: w.writerow(f)
            fh_h.write(f"{tk}|{tp}\n"); fh_d.flush(); fh_h.flush()

    with ThreadPoolExecutor(HILOS) as ex:
        list(ex.map(uno, enumerate(pend)))
    # lo que dio BYMADATA y PPI no consultó se agrega con fuente BYMA; si PPI sí lo consultó, BYMA queda solo como control
    if byma:
        ya = {(r["ticker"], r["tipo"], r["plazo"]) for r in csv.DictReader(open(r_dat, encoding="utf-8"))}
        chk = [(b, next((r for r in csv.DictReader(open(r_dat, encoding="utf-8")) if r["ticker"] == "AL30" and r["plazo"] == "A-24HS" and r.get("fuente") != "BYMA"), None))
               for b in byma if b["ticker"] == "AL30" and b["plazo"] == "A-24HS"]
        if chk and chk[0][1] and abs(float(chk[0][1]["price"] or 0) - float(chk[0][0]["price"] or 0)) > 0.01 * float(chk[0][1]["price"] or 1):
            print("::warning::BYMADATA no coincide con PPI en AL30 (otra fecha?); no se usa", flush=True); byma = []
        n_b = 0
        for b in byma:
            if (b["ticker"], b["tipo"], b["plazo"]) in ya or not float(b["volume"] or 0): continue
            w.writerow([b["ticker"], b["tipo"], b["plazo"], (b["ticker"], b["tipo"]) in NUESTRAS, fecha, b["price"], b["volume"], b["openingPrice"], b["max"], b["min"], "", "", "", "BYMA", b["moneda"]]); n_b += 1
        with open(f"mercado_total/{fecha}_byma.csv", "w", newline="", encoding="utf-8") as fb:
            wb = csv.DictWriter(fb, list(byma[0].keys())) if byma else None
            if wb: wb.writeheader(); wb.writerows(byma)
        print(f"BYMADATA: {n_b} filas agregadas a la foto", flush=True)
    fh_d.close(); fh_h.close()
    hecho = set(r_hecho.read_text(encoding="utf-8").splitlines())
    quedan = sum(1 for k in inst if f"{k[0]}|{k[1]}" not in hecho and (MODO != "rapido" or not byma or k in propias or k[1] in ("LETRAS", "CAUCIONES")))
    resumen(fecha, inst, r_dat, quedan)
    print(f"QUEDAN={quedan}  consultas={consultas[0]}  minutos={(time.time() - inicio) / 60:.1f}", flush=True)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as fh: fh.write(f"quedan={quedan}\nfecha={fecha}\n")


def ar(x, d=0):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def resumen(fecha, inst, r_dat, quedan):
    filas = list(csv.DictReader(open(r_dat, encoding="utf-8")))
    # Si PPI devuelve el mismo registro para los dos plazos (mismo monto y precio), es uno solo: no se cuenta dos veces
    clave = {}
    for f in filas:
        if f["plazo"] == "A-24HS": clave[(f["ticker"], f["tipo"])] = (f["volume"], f["price"])
    filas = [f for f in filas if not (f["plazo"] == "INMEDIATA" and clave.get((f["ticker"], f["tipo"])) == (f["volume"], f["price"]))]
    px = {(f["ticker"], f["plazo"]): float(f["price"] or 0) for f in filas}
    def cot(a, b):
        for pl in ("A-24HS", "INMEDIATA"):
            if px.get((a, pl)) and px.get((b, pl)): return px[(a, pl)] / px[(b, pl)]
        return None
    mep, ccl = cot("AL30", "AL30D"), cot("AL30", "AL30C")
    def en_pesos(f):
        v = float(f["volume"] or 0); mon = f.get("moneda") or (inst.get((f["ticker"], f["tipo"])) or {}).get("currency", "Pesos")
        if "MEP" in mon: return v * mep if mep else None
        if "CCL" in mon: return v * ccl if ccl else None
        return v
    L = [f"# Mercado total — {fecha}", "",
         f"Instrumentos listados en PPI (sin FCI ni licitaciones): {len(inst)}. Sin consultar todavía: {quedan}.",
         f"Monto = \"volume\" de PPI (monto en la moneda del instrumento), pasado a pesos con MEP {ar(mep or 0, 2)} y CCL {ar(ccl or 0, 2)} (AL30).", ""]
    # capa 1
    tot = defaultdict(lambda: [0, 0, 0.0, 0.0])
    bil = defaultdict(lambda: [0, 0.0])
    def bilateral(f):      # especies X (pesos), Y (MEP), Z (cable) de renta fija: operaciones pactadas entre partes y registradas en BYMA (SISTACO/SENEBI)
        return f.get("fuente") == "BYMA" and f["tipo"] in ("BONOS", "ON", "LETRAS") and f["ticker"][-1:] in ("X", "Y", "Z")
    for f in filas:
        if f["tipo"] not in CON_LIBRO: continue
        if bilateral(f):
            m = en_pesos(f)
            if m: b = bil[f["tipo"]]; b[0] += 1; b[1] += m
            continue
        m = en_pesos(f)
        if not m: continue
        t = tot[f["tipo"]]; t[0] += 1; t[2] += m
        if f["nuestra"] == "True": t[1] += 1; t[3] += m
    L += ["## 1. Activos con libro: qué parte ven las 37", "", "| Tipo | Instrumentos operados (por plazo) | De las 37 | Monto total ($) | Monto de las 37 ($) | Proporción |", "|---|---|---|---|---|---|"]
    for tp in CON_LIBRO:
        n, nn, v, vn = tot[tp]
        L.append(f"| {tp} | {n} | {nn} | {ar(v)} | {ar(vn)} | {vn / v:.1%} |" if v else f"| {tp} | {n} | {nn} | 0 | 0 | — |")
    V = sum(t[2] for t in tot.values()); VN = sum(t[3] for t in tot.values())
    if V: L += ["", f"**Total con libro: ${ar(V)}; las 37: ${ar(VN)} ({VN / V:.1%}).**"]
    if bil:
        B = sum(b[1] for b in bil.values())
        L += ["", "Aparte, fuera de la pantalla: operaciones bilaterales registradas en BYMA (especies X, Y, Z de bonos y ONs; dato de BYMADATA, PPI no las lista): "
              + "; ".join(f"{tp} {b[0]} especies por ${ar(b[1])}" for tp, b in bil.items()) + f". Total ${ar(B)} ({B / (V + B):.1%} de todo lo registrado)." ]
    # capa 2: opciones por subyacente
    sub = defaultdict(lambda: [0, 0.0, 0.0, 0.0])        # subyacente -> [series operadas, primas call, primas put, total]
    for f in filas:
        if f["tipo"] != "OPCIONES": continue
        d = (inst.get((f["ticker"], "OPCIONES")) or {}).get("description", "")
        mt = re.search(r"Opci[oó]n (compra|venta) (\S+)", d)
        u = mt.group(2) if mt else f["ticker"][:3]; v = float(f["volume"] or 0)
        s = sub[u]; s[0] += 1; s[3] += v
        if mt and mt.group(1) == "compra": s[1] += v
        else: s[2] += v
    if sub:
        accion = {f["ticker"]: en_pesos(f) or 0 for f in filas if f["tipo"] == "ACCIONES" and f["plazo"] == "A-24HS"}
        L += ["", "## 2. Opciones por acción subyacente (monto en primas)", "",
              "| Subyacente | Series operadas | Primas calls ($) | Primas puts ($) | Total primas ($) | Contado A-24HS ($) |", "|---|---|---|---|---|---|"]
        for u, (n, c, p, t) in sorted(sub.items(), key=lambda x: -x[1][3]):
            L.append(f"| {u} | {n} | {ar(c)} | {ar(p)} | {ar(t)} | {ar(accion.get(u, 0))} |")
        L += ["", "Las primas no son exposición: la exposición sobre la acción es contratos × 100 acciones × precio, y PPI no informa la cantidad de contratos por esta vía."]
    # capa 3: cauciones
    cau = [f for f in filas if f["tipo"] == "CAUCIONES"]
    if cau:
        L += ["", "## 3. Cauciones (mercado de dinero, fuera de la proporción)", "", "| Caución | Plazo de liquidación | Monto | Precio informado |", "|---|---|---|---|"]
        for f in sorted(cau, key=lambda f: (f["ticker"][:5], int(re.sub(r"\D", "", f["ticker"]) or 0))):
            L.append(f"| {f['ticker']} | {f['plazo']} | {ar(float(f['volume'] or 0))} | {f['price']} |")
    otros = defaultdict(float)
    for f in filas:
        if f["tipo"] == "ACCIONES-USA": otros["ACCIONES-USA"] += en_pesos(f) or 0
    if otros: L += ["", f"Acciones del exterior listadas por PPI (fuera de BYMA): ${ar(otros['ACCIONES-USA'])}."]
    Path(f"mercado_total/{fecha}_resumen.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh: fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "--solo-resumen":      # rehace el resumen sin consultar a PPI
        f = sys.argv[1]; inst = {}
        with open(f"mercado_total/{f}_instrumentos.csv", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["tipo"] not in SALTEAR: inst[(r["ticker"], r["tipo"])] = json.loads(r["registro"])
        resumen(f, inst, Path(f"mercado_total/{f}.csv"), 0)
    else:
        main()
# FIN mercado_total.py
