"""Relevo en tiempo real: cada operación que llega al lector se manda a Supabase (tabla ops + aviso al instante).
Si faltan SUPABASE_URL o SUPABASE_SECRET no hace nada. Nunca frena al lector: si Supabase falla, sigue grabando igual."""
import json, os, queue, threading, time
from datetime import datetime
import requests
from pantalla import parsear, num, mejor

URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
CLAVE = os.environ.get("SUPABASE_SECRET", "").strip()
ACTIVO = bool(URL and CLAVE)
_cola = queue.Queue()
_puntas, _libro, _vistas = {}, {}, set()
_n = {"enviadas": 0, "errores": 0}
# Solo las acciones del panel líder van a la mesa (aunque el lector escuche más instrumentos)
PANEL = {t.strip() for t in os.environ.get("TICKERS", "").split(",") if t.strip()}
# Especies extra para la mesa (bonos en D y CEDEARs de seguimiento): van con todas sus operaciones, igual que el panel
MESA_EXTRA = {t.strip() for t in os.environ.get("MESA_EXTRA", "AE38D,AL41D,GD38D,VIST").split(",") if t.strip()}
# Franja del dólar: no se mandan las operaciones de AL30/GD30 (son decenas de miles), solo cada 30 s el valor implícito
# calculado con los medios del libro. Claves (ticker, tipo) para no confundir GGAL local con el ADR (ACCIONES-USA).
DOLAR = {("AL30", "BONOS"), ("AL30D", "BONOS"), ("AL30C", "BONOS"), ("GD30", "BONOS"), ("GD30D", "BONOS"), ("GD30C", "BONOS"),
         ("GGAL", "ACCIONES-USA"), ("GGAL", "ACCIONES")}
_medios = {}   # (ticker, tipo) -> (medio del libro, hora)
# Preapertura: hasta la primera operación de cada especie de la mesa, cada 20 s se guarda su libro (si cambió) como una
# fila del ticker sintético "PRE:TICKER" en la tabla ops. Campos: precio = apertura teórica si el libro está cruzado
# (si no, el medio); nom = cantidad que se ejecutaría a ese precio; acum / var = profundidad de 5 niveles compra / venta;
# mind / maxd = mejor compra / mejor venta; lado = "X" libro cruzado, "P" sin cruzar.
_pre, _pre_cambio, _abrio = {}, set(), set()


def apertura_teorica(bids, offers):
    """Precio que maximiza lo ejecutable con los 5 niveles visibles de cada lado (empate: menor desbalance, luego más cerca del medio)."""
    if not bids or not offers or bids[0][0] < offers[0][0]:
        return None, 0.0
    precios = sorted({p for p, _ in bids + offers if p})
    medio = (bids[0][0] + offers[0][0]) / 2
    mejor_ = None
    for p in precios:
        dem = sum(q for b, q in bids if b >= p); ofe = sum(q for a, q in offers if a <= p)
        clave = (min(dem, ofe), -abs(dem - ofe), -abs(p - medio))
        if mejor_ is None or clave > mejor_[0]: mejor_ = (clave, p)
    return mejor_[1], mejor_[0][0]


def _cab(extra=None):
    h = {"apikey": CLAVE, "Content-Type": "application/json"}
    if CLAVE.startswith("eyJ"):
        h["Authorization"] = "Bearer " + CLAVE
    h.update(extra or {})
    return h


def recibir(crudo):
    """Se llama con cada mensaje crudo de PPI. Rápido: solo clasifica y encola."""
    if not ACTIVO:
        return
    try:
        m = parsear(str(crudo))
        if not isinstance(m, dict):
            return
        tk = str(m.get("Ticker", "?"))
        tipo = str(m.get("Type", "ACCIONES")).upper()
        if (tk, tipo) in DOLAR and m.get("Trade") not in (True, "true", "True"):
            bc, bv = mejor(m.get("Bids")), mejor(m.get("Offers"))
            if bc and bv and bc < bv:
                _medios[(tk, tipo)] = ((bc + bv) / 2, time.time())
        if tipo == "ACCIONES":
            if PANEL and tk not in PANEL and tk not in MESA_EXTRA:
                return
        elif tipo in ("BONOS", "CEDEARS"):
            if tk not in MESA_EXTRA:
                return
        else:
            return
        if m.get("Trade") not in (True, "true", "True"):
            bc, bv = mejor(m.get("Bids")), mejor(m.get("Offers"))
            _puntas[tk] = (bc, bv)
            _libro[tk] = {"bids": [[num(n.get("Price")), num(n.get("Quantity"))] for n in (m.get("Bids") or [])[:5] if isinstance(n, dict)],
                          "offers": [[num(n.get("Price")), num(n.get("Quantity"))] for n in (m.get("Offers") or [])[:5] if isinstance(n, dict)]}
            if tk not in _abrio:
                _pre[tk] = _libro[tk]; _pre_cambio.add(tk)
            return
        fecha = str(m.get("Date", ""))
        p, nom = num(m.get("Price")), num(m.get("VolumeAmount")) or 0.0
        acum = num(m.get("VolumeTotalAmount"))
        clave = f"{tk}|{fecha}|{p}|{nom}|{acum}"
        if clave in _vistas:
            return
        _vistas.add(clave)
        if p: _abrio.add(tk)
        try:
            ts = datetime.fromisoformat(fecha).replace(tzinfo=None)
        except ValueError:
            ts = datetime.now()
        bc, bv = _puntas.get(tk, (None, None))
        lado = "C" if bv and p and p >= bv else "V" if bc and p and p <= bc else "M"
        _cola.put({"clave": clave, "fecha": ts.strftime("%Y-%m-%d"), "ts": ts.isoformat(timespec="milliseconds"), "tk": tk,
                   "precio": p, "nom": nom, "monto": num(m.get("VolumeCurrency")) or 0.0, "acum": acum, "lado": lado,
                   "var": num(m.get("VarDay")), "maxd": num(m.get("MaxDay")), "mind": num(m.get("MinDay"))})
    except Exception:
        pass


def _dolar():
    """Cada 30 s: MEP y CCL implícitos (AL30 y GD30, con medios del libro de hace menos de 2 minutos) y el ADR de GGAL en US$.
    Se guardan como operaciones de tickers sintéticos ($MEP, $CCL, $MEPGD, $CCLGD, $ADR) con monto 0."""
    ahora, ts = time.time(), datetime.now()
    def md(k):
        v = _medios.get(k)
        return v[0] if v and ahora - v[1] < 120 else None
    out = {}
    for nom, a, b in (("$MEP", "AL30", "AL30D"), ("$CCL", "AL30", "AL30C"), ("$MEPGD", "GD30", "GD30D"), ("$CCLGD", "GD30", "GD30C")):
        pa, pb = md((a, "BONOS")), md((b, "BONOS"))
        if pa and pb: out[nom] = round(pa / pb, 2)
    adr = md(("GGAL", "ACCIONES-USA"))
    if adr: out["$ADR"] = round(adr, 3)
    for tk, v in out.items():
        _cola.put({"clave": f"{tk}|{ts:%Y-%m-%dT%H:%M:%S}", "fecha": ts.strftime("%Y-%m-%d"), "ts": ts.isoformat(timespec="milliseconds"),
                   "tk": tk, "precio": v, "nom": 0.0, "monto": 0.0, "acum": None, "lado": "M", "var": None, "maxd": None, "mind": None})


def _preapertura():
    """Libros de preapertura que cambiaron, de especies que todavía no operaron (hasta las 11:30 como máximo)."""
    ahora = datetime.now()
    if ahora.hour * 60 + ahora.minute > 11 * 60 + 30: return
    for tk in list(_pre_cambio - _abrio):
        _pre_cambio.discard(tk)
        lb = _pre.get(tk) or {}
        bids = [x for x in lb.get("bids", []) if x[0] and x[1]]; offers = [x for x in lb.get("offers", []) if x[0] and x[1]]
        if not bids and not offers: continue
        teo, ejec = apertura_teorica(bids, offers)
        b1 = bids[0][0] if bids else None; a1 = offers[0][0] if offers else None
        precio = teo if teo else ((b1 + a1) / 2 if b1 and a1 else (b1 or a1))
        _cola.put({"clave": f"PRE:{tk}|{ahora:%Y-%m-%dT%H:%M:%S}", "fecha": ahora.strftime("%Y-%m-%d"), "ts": ahora.isoformat(timespec="milliseconds"),
                   "tk": f"PRE:{tk}", "precio": precio, "nom": float(ejec), "monto": 0.0, "acum": float(sum(q for _, q in bids)),
                   "lado": "X" if teo else "P", "var": float(sum(q for _, q in offers)), "maxd": a1, "mind": b1})


def _enviar():
    s = requests.Session()
    ultimo_dolar = ultimo_pre = 0.0
    while True:
        time.sleep(1.5)
        if time.time() - ultimo_dolar >= 30:
            ultimo_dolar = time.time()
            try:
                _dolar()
            except Exception:
                pass
        if time.time() - ultimo_pre >= 20:
            ultimo_pre = time.time()
            try:
                _preapertura()
            except Exception:
                pass
        lote = []
        while not _cola.empty() and len(lote) < 400:
            lote.append(_cola.get())
        libro = dict(_libro)
        if not lote and not libro:
            continue
        try:
            if lote:
                r = s.post(f"{URL}/rest/v1/ops?on_conflict=clave", data=json.dumps(lote), timeout=10,
                           headers=_cab({"Prefer": "resolution=ignore-duplicates,return=minimal"}))
                if r.status_code >= 300:
                    raise RuntimeError(f"tabla {r.status_code} {r.text[:120]}")
            r = s.post(f"{URL}/realtime/v1/api/broadcast", timeout=10, headers=_cab(),
                       data=json.dumps({"messages": [{"topic": "cinta", "event": "ops", "payload": {"ops": lote, "libro": libro}}]}))
            if r.status_code >= 300:
                raise RuntimeError(f"aviso {r.status_code} {r.text[:120]}")
            _n["enviadas"] += len(lote)
            if _n["enviadas"] and (_n["enviadas"] < 500 or _n["enviadas"] % 5000 < len(lote)):
                print(f"{datetime.now():%H:%M:%S} relevo: {_n['enviadas']} operaciones enviadas a Supabase", flush=True)
        except Exception as e:
            _n["errores"] += 1
            for x in lote:            # no se pierden: vuelven a la cola
                _cola.put(x)
            if _n["errores"] in (1, 10, 100) or _n["errores"] % 1000 == 0:
                print(f"{datetime.now():%H:%M:%S} relevo: error {_n['errores']}: {str(e)[:150]}", flush=True)
            time.sleep(5)


if ACTIVO:
    threading.Thread(target=_enviar, daemon=True).start()
    print("relevo: activo (Supabase)", flush=True)
else:
    print("relevo: apagado (faltan SUPABASE_URL o SUPABASE_SECRET)", flush=True)
# FIN relevo.py
