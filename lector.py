"""Lector de tiempo real de PPI: escucha y guarda cada mensaje de mercado, sin procesar."""
import gzip, os, sys, threading, time
from datetime import datetime
from ppi_client.ppi import PPI
from ppi_client.models.instrument import Instrument

TICKERS = os.environ.get("TICKERS", "GGAL,BMA").split(",")
TIPO, PLAZO = "ACCIONES", "A-24HS"

def main(hasta, archivo):
    fin = datetime.strptime(datetime.now().strftime("%Y-%m-%d ") + hasta, "%Y-%m-%d %H:%M")
    segundos = (fin - datetime.now()).total_seconds()
    if segundos <= 0:
        print("Ya pasó la hora de fin")
        return
    ppi = PPI(sandbox=False)
    ppi.account.login_api(os.environ["PPI_API_KEY"], os.environ["PPI_API_SECRET"])
    out = gzip.open(archivo, "at", encoding="utf-8")
    n = {"msjs": 0}

    def al_conectar():
        print(f"{datetime.now():%H:%M:%S} conectado; suscribiendo {len(TICKERS)} especies")
        for t in TICKERS:
            ppi.realtime.subscribe_to_element(Instrument(t.strip(), TIPO, PLAZO))

    def al_desconectar():
        print(f"{datetime.now():%H:%M:%S} desconectado; se reinicia")
        out.close()
        os._exit(1)

    def al_recibir(msj):
        out.write(datetime.now().isoformat(timespec="milliseconds") + "\t" + str(msj).replace("\n", " ") + "\n")
        n["msjs"] += 1

    def terminar():
        print(f"{datetime.now():%H:%M:%S} fin; {n['msjs']} mensajes")
        out.close()
        os._exit(0)

    threading.Timer(segundos, terminar).start()
    ppi.realtime.connect_to_market_data(al_conectar, al_desconectar, al_recibir)
    ppi.realtime.start_connections()

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
