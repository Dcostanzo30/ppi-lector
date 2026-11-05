"""Cauciones y opciones (dólar y otras) leídas desde la API de PPI. Solo consulta.
Mismas credenciales (PPI_API_KEY / PPI_API_SECRET) que los demás lectores.

Primera etapa exploratoria: averigua qué instrumentos de tipo CAUCIONES y OPCIONES ofrece PPI, baja precio actual y la
historia diaria desde HISTORIA_DESDE, y deja un DIAGNOSTICO.md con los registros crudos para ajustar la lectura
(cuál campo es la tasa de la caución, cómo se nombran las opciones sobre dólar, etc.).

Salidas: estudios/cauciones/{instrumentos,precios_hoy,historico}.csv + DIAGNOSTICO.md
         estudios/opciones/{instrumentos,precios_hoy,historico_dlr}.csv + DIAGNOSTICO.md
"""
import csv, json, os, re, string, time
from datetime import date, datetime
from pathlib import Path

HISTORIA_DESDE = date(2026, 6, 1)
PLAZOS = ("INMEDIATA", "A-24HS")
PAUSA = 0.15
MAX_OPC = 400
SEM = list(string.ascii_uppercase) + list(string.digits) + ["DLR", "DLR/", "DOLAR", "GGAL", "YPF", "PAMP", "CAUC", "CAUCION"]
DIAG = {"cauciones": [], "opciones": []}
ACT = "cauciones"


def diag(t):
    print(t, flush=True)
    DIAG[ACT].append(t)


def ingresar():
    from ppi_client.ppi import PPI
    p = PPI(sandbox=False)
    p.account.login_api(os.environ["PPI_API_KEY"].strip(), os.environ["PPI_API_SECRET"].strip())
    return p


def buscar(ppi, tk, mercado, tipo):
    time.sleep(PAUSA)
    for a, b in ((tk, ""), (tk, tk)):
        try:
            r = ppi.marketdata.search_instrument(a, b, mercado, tipo)
            if isinstance(r, list):
                return r
        except Exception:
            continue
    return []


def listar(ppi, tipo):
    hallados = {}
    for mer in ("", "BYMA", "ROFEX"):
        n0 = len(hallados)
        for s in SEM:
            for r in buscar(ppi, s, mer, tipo):
                if isinstance(r, dict) and r.get("ticker"):
                    hallados.setdefault(str(r["ticker"]).strip().upper(), r)
        diag(f"- {tipo} mercado='{mer}': {len(hallados) - n0} nuevos")
    return hallados


def precio_hoy(ppi, tk, tipo):
    err = ""
    for pl in PLAZOS:
        time.sleep(PAUSA)
        try:
            c = ppi.marketdata.current(tk, tipo, pl)
            if c:
                return pl, c, ""
        except Exception as e:
            err = f"{type(e).__name__} {str(e)[:60]}"
    return None, None, err


def historia(ppi, tk, tipo, plazo):
    for pl in ([plazo] if plazo else []) + [p for p in PLAZOS if p != plazo]:
        time.sleep(PAUSA)
        try:
            r = ppi.marketdata.search(tk, tipo, pl, HISTORIA_DESDE.isoformat(), date.today().isoformat()) or []
        except Exception:
            continue
        if r:
            return [dict(ticker=tk, tipo=tipo, plazo=pl, fecha=str(x.get("date", ""))[:10], precio=x.get("price"),
                         apertura=x.get("openingPrice"), maximo=x.get("max"), minimo=x.get("min"), volumen=x.get("volume"))
                    for x in r]
    return []


def csv_dic(ruta, filas):
    if not filas:
        return
    cols = []
    for f in filas:
        for k in f:
            if k not in cols:
                cols.append(k)
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(filas)


def procesar(ppi, tipo, carpeta, filtro_hist, elegir=None):
    global ACT
    ACT = carpeta
    sal = Path("estudios") / carpeta
    sal.mkdir(parents=True, exist_ok=True)
    diag(f"# Diagnóstico {tipo.lower()} — {datetime.now():%Y-%m-%d %H:%M}\n")
    hallados = listar(ppi, tipo)
    diag(f"\n**{tipo} encontrados: {len(hallados)}**")
    diag("Muestra de registros crudos (para ajustar la lectura):")
    for tk, r in list(sorted(hallados.items()))[:8]:
        diag(f"- {tk}: {json.dumps(r, ensure_ascii=False, default=str)[:300]}")
    csv_dic(sal / "instrumentos.csv", [dict(ticker=k, registro=json.dumps(r, ensure_ascii=False, default=str))
                                       for k, r in sorted(hallados.items())])
    hoy, hist, sin = [], [], []
    elegidos = [tk for tk in sorted(hallados) if elegir is None or elegir(hallados[tk])]
    if elegir is not None:
        diag(f"- De {len(hallados)} instrumentos, se consultan precios de {len(elegidos)} que cumplen el filtro (opciones sobre dólar).")
        if not elegidos:
            diag("- **No hay opciones sobre dólar en PPI (esto se revisa todos los días: si PPI las suma, aparecen acá solas).**")
    resumen = {}
    for r in hallados.values():
        m = re.search(r'(?:compra|venta)\s+(\S+)', str(r.get('description', '')))
        resumen[m.group(1) if m else '?'] = resumen.get(m.group(1) if m else '?', 0) + 1
    diag(f"- Subyacentes de los instrumentos encontrados: {dict(sorted(resumen.items(), key=lambda x: -x[1])[:15])}")
    for tk in elegidos:
        pl, c, err = precio_hoy(ppi, tk, tipo)
        if not c:
            sin.append(f"{tk}({err})" if err else tk)
            continue
        hoy.append(dict(ticker=tk, plazo=pl, fecha=str(c.get("date", ""))[:19], precio=c.get("price"), volumen=c.get("volume"),
                        apertura=c.get("openingPrice"), maximo=c.get("max"), minimo=c.get("min"),
                        registro=json.dumps(c, ensure_ascii=False, default=str)))
        if filtro_hist(tk):
            hist += historia(ppi, tk, tipo, pl)
    diag(f"- Con precio actual: {len(hoy)}; sin precio: {len(sin)} {sin[:10]}")
    diag(f"- Filas de historia diaria: {len(hist)}")
    if hoy:
        diag("Muestra de precios actuales crudos:")
        for h in hoy[:5]:
            diag(f"- {h['ticker']}: {h['registro'][:300]}")
    csv_dic(sal / "precios_hoy.csv", hoy)
    csv_dic(sal / ("historico_dlr.csv" if tipo == "OPCIONES" else "historico.csv"), hist)
    (sal / "DIAGNOSTICO.md").write_text("\n".join(DIAG[carpeta]), encoding="utf-8")


def main():
    try:
        ppi = ingresar()
    except Exception as e:
        print(f"No se pudo ingresar: {type(e).__name__} {str(e)[:200]}")
        return
    procesar(ppi, "CAUCIONES", "cauciones", lambda tk: True)
    procesar(ppi, "OPCIONES", "opciones", lambda tk: True,
             elegir=lambda r: bool(re.search(r"DLR|D[ÓO]LAR", str(r.get("description", "")) + " " + str(r.get("ticker", "")), re.I)))
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as fh:
            for k in DIAG:
                fh.write("\n".join(DIAG[k]) + "\n\n")


if __name__ == "__main__":
    main()
