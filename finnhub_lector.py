"""Lector de Nueva York por Finnhub: graba cada operación de los ADR argentinos y de fondos que reflejan
Wall Street, petróleo, oro, dólar y tasas. Corre aparte del lector de PPI: si falla, la cinta local no se toca.

Uso: python finnhub_lector.py HH:MM archivo.txt.gz
Cada renglón: <hora de recepción>\t<mensaje de Finnhub tal como llegó>
Al arrancar guarda también el cierre anterior de cada símbolo (renglones con "type":"previo").
"""
import gzip, json, os, sys, threading, time, urllib.request
from datetime import datetime

SIMBOLOS = os.environ.get("FINNHUB_SIMBOLOS",
    "GGAL,BMA,SUPV,BBAR,YPF,PAM,TEO,CEPU,LOMA,EDN,TGS,CRESY,IRS,"
    "SPY,QQQ,DIA,IWM,EWZ,ARGT,XLE,USO,BNO,GLD,UUP,IEF,TLT,VIXY,HYG,EEM").split(",")[:30]
CLAVE = os.environ.get("FINNHUB_API_KEY", "").strip()


def log(t):
    print(f"{datetime.now():%H:%M:%S} {t}", flush=True)


def ahora():
    return datetime.now().isoformat(timespec="milliseconds")


def guardar_previos(out):
    for s in SIMBOLOS:
        try:
            with urllib.request.urlopen(f"https://finnhub.io/api/v1/quote?symbol={s}&token={CLAVE}", timeout=15) as r:
                q = json.loads(r.read())
            out.write(ahora() + "\t" + json.dumps({"type": "previo", "s": s, "pc": q.get("pc"), "c": q.get("c"),
                                                    "t": q.get("t")}) + "\n")
        except Exception as e:
            log(f"sin cierre anterior de {s}: {e}")
        time.sleep(1.1)   # el plan gratuito admite 60 consultas por minuto
    out.flush()


def main(hasta, archivo):
    import websocket
    fin = datetime.strptime(datetime.now().strftime("%Y-%m-%d ") + hasta, "%Y-%m-%d %H:%M")
    if (fin - datetime.now()).total_seconds() <= 0 or not CLAVE:
        log("nada que hacer (hora de fin pasada o falta la clave)")
        return
    out = gzip.open(archivo, "at", encoding="utf-8")
    guardar_previos(out)
    n = {"msjs": 0}
    lock = threading.Lock()

    def al_abrir(ws):
        log(f"conectado a Finnhub; suscribiendo {len(SIMBOLOS)} símbolos")
        for s in SIMBOLOS:
            ws.send(json.dumps({"type": "subscribe", "symbol": s}))

    def al_recibir(ws, msj):
        if '"type":"ping"' in msj:
            return
        with lock:
            out.write(ahora() + "\t" + msj.replace("\n", " ") + "\n")
            n["msjs"] += 1
            if n["msjs"] in (1, 100, 1000) or n["msjs"] % 10000 == 0:
                log(f"{n['msjs']} mensajes")
                out.flush()

    def terminar():
        log(f"fin; {n['msjs']} mensajes")
        with lock:
            out.close()
        os._exit(0)

    threading.Timer((fin - datetime.now()).total_seconds(), terminar).start()
    while True:
        try:
            ws = websocket.WebSocketApp(f"wss://ws.finnhub.io?token={CLAVE}", on_open=al_abrir,
                                        on_message=al_recibir,
                                        on_error=lambda ws, e: log(f"error: {str(e)[:120]}"))
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except Exception as e:
            log(f"se cortó: {str(e)[:120]}")
        log("reconectando en 15 s")
        time.sleep(15)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
