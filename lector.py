"""Lector de tiempo real de PPI: escucha y guarda cada mensaje de mercado, sin procesar."""
import gzip, os, sys, threading, time
from datetime import datetime
from ppi_client.ppi import PPI
from ppi_client.models.instrument import Instrument
from ppi_client.api.constants import MIME_JSON, ACCOUNT_LOGIN_API
try:
    import relevo   # manda cada operación a Supabase para la mesa en vivo (si no hay claves, no hace nada)
except Exception as e:
    relevo = None
    print("relevo: no se pudo cargar:", e, flush=True)

TICKERS = [t.strip() for t in os.environ.get("TICKERS", "GGAL,BMA").split(",") if t.strip()]
# EXTRAS: otros instrumentos con su tipo y plazo, "TICKER|TIPO|PLAZO" separados por coma
# (por ejemplo AL30|BONOS|A-24HS,SPY|CEDEARS|A-24HS,GGAL|ACCIONES-USA|A-24HS)
EXTRAS = [e.strip() for e in os.environ.get("EXTRAS", "").split(",") if e.strip()]
TIPO, PLAZO = "ACCIONES", "A-24HS"


UNIVERSO = os.environ.get("UNIVERSO", "universo.csv")


def desde_universo(hoy=None):
    """Padrón único (universo.csv): se escuchan en vivo el núcleo y el anillo 2 vigentes hoy
    (desde <= hoy y, si tiene, hoy < hasta). El anillo 3 solo va a la foto diaria del mercado total."""
    import csv
    hoy = hoy or datetime.now().strftime("%Y-%m-%d")
    try:
        with open(UNIVERSO, encoding="utf-8") as fh:
            filas = list(csv.DictReader(fh))
    except OSError:
        return None
    lista = []
    for f in filas:
        if f.get("anillo") in ("nucleo", "2") and f.get("desde", "") <= hoy and (not f.get("hasta") or hoy < f["hasta"]):
            x = (f["ticker"], f["tipo"], f.get("plazo") or PLAZO)
            if x not in lista: lista.append(x)
    return lista or None


def instrumentos():
    lista = desde_universo()
    if lista:
        return lista
    lista = [(t, TIPO, PLAZO) for t in TICKERS]          # respaldo si falta el padrón
    for e in EXTRAS:
        partes = [p.strip() for p in e.split("|")]
        if len(partes) == 3:
            lista.append(tuple(partes))
    return lista

def log(t):
    print(f"{datetime.now():%H:%M:%S} {t}", flush=True)

def preparar_login_tiempo_real(ppi):
    """Unico ingreso a PPI, el del tiempo real; si PPI lo rechaza, reintenta con calma y muestra el motivo."""
    rest = ppi._PPI__apiClient.get_rest_client()
    rest.api_key = os.environ["PPI_API_KEY"].strip()
    rest.api_secret = os.environ["PPI_API_SECRET"].strip()

    def login_ws():
        for intento in range(1, 7):
            h = {"AuthorizedClient": rest.authorized_client, "ClientKey": rest.client_key,
                 "ApiKey": rest.api_key, "ApiSecret": rest.api_secret}
            res = rest.post(ACCOUNT_LOGIN_API, None, None, h, MIME_JSON)
            if res.httpStatus == 200:
                rest.token_ws = res.response["accessToken"]
                rest.refresh_token_ws = res.response["refreshToken"]
                log("ingreso al tiempo real correcto")
                return rest.token_ws
            log(f"PPI rechazó el ingreso al tiempo real (intento {intento}, código {res.httpStatus}): {str(res.response)[:150]}")
            time.sleep(15 * intento)
        return None

    rest.login_ws = login_ws

def main(hasta, archivo):
    fin = datetime.strptime(datetime.now().strftime("%Y-%m-%d ") + hasta, "%Y-%m-%d %H:%M")
    segundos = (fin - datetime.now()).total_seconds()
    if segundos <= 0:
        log("Ya pasó la hora de fin")
        return
    ppi = PPI(sandbox=False)
    preparar_login_tiempo_real(ppi)
    out = gzip.open(archivo, "at", encoding="utf-8")
    n = {"msjs": 0}

    def al_conectar():
        lista = instrumentos()
        log(f"conectado; suscribiendo {len(lista)} instrumentos")
        for t, tipo, plazo in lista:
            try:
                ppi.realtime.subscribe_to_element(Instrument(t, tipo, plazo))
            except Exception as e:
                log(f"no se pudo suscribir {t} {tipo} {plazo}: {e}")

    def al_desconectar():
        log(f"desconectado tras {n['msjs']} mensajes; se reinicia")
        out.close()
        os._exit(1)

    def al_recibir(msj):
        out.write(datetime.now().isoformat(timespec="milliseconds") + "\t" + str(msj).replace("\n", " ") + "\n")
        n["msjs"] += 1
        if relevo:
            relevo.recibir(msj)
        if n["msjs"] in (1, 100, 1000) or n["msjs"] % 10000 == 0:
            log(f"{n['msjs']} mensajes")

    def terminar():
        log(f"fin; {n['msjs']} mensajes")
        out.close()
        os._exit(0)

    threading.Timer(segundos, terminar).start()
    try:
        ppi.realtime.connect_to_market_data(al_conectar, al_desconectar, al_recibir)
        ppi.realtime.start_connections()
    except Exception as e:
        log(f"no se pudo conectar al tiempo real: {e}")
        out.close()
        os._exit(2)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
# FIN lector.py
