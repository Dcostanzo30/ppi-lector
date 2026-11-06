"""Dólar MEP y CCL implícitos con las puntas reales de los bonos (GD30/AL30 y sus versiones en dólares), leídos de PPI.
Solo consulta. Mismas credenciales (PPI_API_KEY / PPI_API_SECRET) que los demás lectores.

Idea: comprar dólares con pesos por bonos = comprar el bono en pesos a la punta vendedora y vender el bono en dólares a la punta compradora.
  Pagás por dólar:      punta_vendedora(bono $) / punta_compradora(bono D)
  Cobrás por dólar:     punta_compradora(bono $) / punta_vendedora(bono D)
La diferencia entre las dos cifras es el costo de ida y vuelta del cambio, sin comisiones (las de PPI se suman aparte: 0,60% por cada operación).

Se corre varias veces por día (mercado abierto) y se agrega una foto a estudios/mep/puntas.csv y estudios/mep/mep.csv.
"""
import csv, json, os, time
from datetime import datetime
from pathlib import Path

SAL = Path("estudios/mep"); SAL.mkdir(parents=True, exist_ok=True)
PARES = {"GD30": ("GD30", "GD30D", "GD30C"), "AL30": ("AL30", "AL30D", "AL30C")}
PLAZOS = ("INMEDIATA", "A-24HS")
TIPOS = ("BONOS",)
PAUSA = 0.2
DIAG = []


def diag(t):
    print(t, flush=True)
    DIAG.append(t)


def ingresar():
    from ppi_client.ppi import PPI
    p = PPI(sandbox=False)
    p.account.login_api(os.environ["PPI_API_KEY"].strip(), os.environ["PPI_API_SECRET"].strip())
    return p


def mejores(libro):
    """Mejor punta compradora y vendedora de un libro, tolerando distintos nombres de campos."""
    if not isinstance(libro, dict):
        return None, None, None, None
    def lado(*nombres):
        for n in nombres:
            v = libro.get(n)
            if isinstance(v, list) and v:
                return v
        return []
    bids = lado("bids", "bid", "Bids")
    offers = lado("offers", "offer", "asks", "Offers")
    def top(lst, mayor):
        px = [(float(x.get("price")), x.get("quantity")) for x in lst if isinstance(x, dict) and x.get("price")]
        if not px:
            return None, None
        return (max(px) if mayor else min(px))
    b = top(bids, True)
    o = top(offers, False)
    return (b[0] if b else None), (b[1] if b else None), (o[0] if o else None), (o[1] if o else None)


def leer(ppi, tk, plazo):
    err = ""
    for tipo in TIPOS:
        time.sleep(PAUSA)
        try:
            lb = ppi.marketdata.book(tk, tipo, plazo)
            res = mejores(lb)
            if res[0] or res[2]:
                return res, json.dumps(lb, ensure_ascii=False, default=str)[:300]
            err = f"libro vacío ({json.dumps(lb, ensure_ascii=False, default=str)[:120]})"
        except Exception as e:
            err = f"{type(e).__name__} {str(e)[:80]}"
    return (None, None, None, None), err


def main():
    ahora = datetime.now()
    diag(f"# Diagnóstico MEP — {ahora:%Y-%m-%d %H:%M}\n")
    try:
        ppi = ingresar()
    except Exception as e:
        diag(f"No se pudo ingresar: {type(e).__name__} {str(e)[:200]}")
        (SAL / "DIAGNOSTICO.md").write_text("\n".join(DIAG), encoding="utf-8")
        return
    puntas, mep = [], []
    for nombre, (pes, dol, cabl) in PARES.items():
        for plazo in PLAZOS:
            datos = {}
            for etiqueta, tk in (("pesos", pes), ("mep", dol), ("ccl", cabl)):
                (bp, bq, ap, aq), crudo = leer(ppi, tk, plazo)
                datos[etiqueta] = (bp, ap)
                puntas.append(dict(fecha_hora=f"{ahora:%Y-%m-%d %H:%M}", bono=nombre, ticker=tk, plazo=plazo, compradora=bp, cant_compradora=bq,
                                   vendedora=ap, cant_vendedora=aq))
                diag(f"- {tk} {plazo}: compradora {bp} vendedora {ap}" + ("" if bp or ap else f"  ({crudo})"))
            for via, k in (("MEP", "mep"), ("CCL", "ccl")):
                bp, ap = datos["pesos"]
                bd, ad = datos[k]
                if bp and ap and bd and ad:
                    pagas = ap / bd
                    cobras = bp / ad
                    mep.append(dict(fecha_hora=f"{ahora:%Y-%m-%d %H:%M}", bono=nombre, via=via, plazo=plazo, pagas_por_dolar=round(pagas, 2),
                                    cobras_por_dolar=round(cobras, 2), costo_ida_vuelta_pct=round((pagas / cobras - 1) * 100, 3)))
    def agregar(nombre, filas):
        if not filas:
            return
        ruta = SAL / nombre
        nuevo = not ruta.exists()
        with open(ruta, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(filas[0]))
            if nuevo:
                w.writeheader()
            w.writerows(filas)
    agregar("puntas.csv", puntas)
    agregar("mep.csv", mep)
    diag(f"\nFilas de puntas: {len(puntas)}; de MEP/CCL: {len(mep)}")
    for m in mep:
        diag(f"- {m['bono']} {m['via']} {m['plazo']}: pagás {m['pagas_por_dolar']}, cobrás {m['cobras_por_dolar']}, costo ida y vuelta {m['costo_ida_vuelta_pct']}%")
    (SAL / "DIAGNOSTICO.md").write_text("\n".join(DIAG), encoding="utf-8")


if __name__ == "__main__":
    main()
