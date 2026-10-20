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
        if str(m.get("Type", "ACCIONES")).upper() != "ACCIONES":
            return
        if m.get("Trade") not in (True, "true", "True"):
            bc, bv = mejor(m.get("Bids")), mejor(m.get("Offers"))
            _puntas[tk] = (bc, bv)
            _libro[tk] = {"bids": [[num(n.get("Price")), num(n.get("Quantity"))] for n in (m.get("Bids") or [])[:5] if isinstance(n, dict)],
                          "offers": [[num(n.get("Price")), num(n.get("Quantity"))] for n in (m.get("Offers") or [])[:5] if isinstance(n, dict)]}
            return
        fecha = str(m.get("Date", ""))
        p, nom = num(m.get("Price")), num(m.get("VolumeAmount")) or 0.0
        acum = num(m.get("VolumeTotalAmount"))
        clave = f"{tk}|{fecha}|{p}|{nom}|{acum}"
        if clave in _vistas:
            return
        _vistas.add(clave)
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


def _enviar():
    s = requests.Session()
    while True:
        time.sleep(1.5)
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
