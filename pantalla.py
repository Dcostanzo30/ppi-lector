"""Pantalla en vivo: resume lo grabado hasta este momento.

Uso: python pantalla.py parte1.txt.gz [parte2.txt.gz ...] [--afuera finnhub1.txt.gz ...] > pantalla.md
- Partes de PPI: acciones del panel, y si están, bonos, CEDEARs y ADR por PPI.
- Partes de Finnhub (después de --afuera): ADR y fondos de Nueva York en tiempo real.
Junta los turnos, descarta repetidas por el cruce y clasifica cada operación por el lado que la inició.
"""
import json, re, statistics, sys, zlib
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

VENTANA_MIN = 10
_SIN_COMILLAS = re.compile(r'"(\w+)":([^,\[\]{}"]+)')
BANCOS = ["GGAL", "BMA", "SUPV", "BBAR", "VALO", "BYMA"]
# ADR en Nueva York -> (especie local, acciones locales por ADR)
ADR = {"GGAL": ("GGAL", 10), "BMA": ("BMA", 10), "SUPV": ("SUPV", 5), "BBAR": ("BBAR", 3),
       "YPF": ("YPFD", 10), "PAM": ("PAMP", 25), "TEO": ("TECO2", 5), "CEPU": ("CEPU", 10),
       "LOMA": ("LOMA", 5), "EDN": ("EDN", 20), "TGS": ("TGSU2", 5), "CRESY": ("CRES", 10),
       "IRS": ("IRSA", 10)}
ADR_DE = {loc: (adr, r) for adr, (loc, r) in ADR.items()}
GRUPOS_AFUERA = [("ADR bancos", ["GGAL", "BMA", "SUPV", "BBAR"]),
                 ("Otros ADR", ["YPF", "PAM", "TEO", "CEPU", "LOMA", "EDN", "TGS", "CRESY", "IRS"]),
                 ("Wall Street", ["SPY", "QQQ", "DIA", "IWM"]),
                 ("Argentina y Brasil", ["ARGT", "EWZ", "EEM"]),
                 ("Energía", ["XLE", "USO", "BNO"]),
                 ("Refugios, dólar y tasas", ["GLD", "UUP", "IEF", "TLT", "HYG"]),
                 ("Miedo (VIX)", ["VIXY"])]


def _arreglar(v):
    v = v.strip()
    if v in ("true", "false", "null"):
        return v
    try:
        float(v)
        return v
    except ValueError:
        return json.dumps(v)


def parsear(texto):
    texto = texto.strip()
    if len(texto) > 1 and texto[0] == '"' and texto[-1] == '"':
        texto = texto[1:-1]
    try:
        m = json.loads(texto)
    except ValueError:
        m = json.loads(_SIN_COMILLAS.sub(lambda x: f'"{x.group(1)}":{_arreglar(x.group(2))}', texto))
    return parsear(m) if isinstance(m, str) else m


def leer_gz(path):
    """Lee un .gz aunque tenga varios tramos o esté a medio escribir."""
    datos = Path(path).read_bytes()
    salida = bytearray()
    while datos:
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            salida += d.decompress(datos)
        except zlib.error:
            break
        datos = d.unused_data
    return salida.decode("utf-8", errors="replace").splitlines()


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def mejor(niveles):
    for n in niveles or []:
        if isinstance(n, dict) and num(n.get("Price")):
            return num(n.get("Price"))
    return None


# ---------- lectura ----------

def leer(partes):
    """Operaciones de PPI: (ticker, ts, precio, nominales, monto, acum_previo, lado, var_dia, max, min, tipo)."""
    incluidas = defaultdict(int)
    ops = []
    for parte in sorted(partes):
        en_parte = defaultdict(int)
        puntas = {}
        for renglon in leer_gz(parte):
            if "\t" not in renglon:
                continue
            recibido, crudo = renglon.split("\t", 1)
            try:
                m = parsear(crudo)
            except Exception:
                continue
            if not isinstance(m, dict):
                continue
            tk = str(m.get("Ticker", "?"))
            fecha = str(m.get("Date", ""))
            try:
                ts = datetime.fromisoformat(fecha).replace(tzinfo=None)
            except ValueError:
                ts = datetime.fromisoformat(recibido)
            es_op = m.get("Trade") in (True, "true", "True")
            if es_op:
                clave = ("op", tk, fecha, m.get("Price"), m.get("VolumeAmount"), m.get("VolumeTotalAmount"))
            else:
                clave = ("lib", tk, fecha, json.dumps(m.get("Bids"), default=str), json.dumps(m.get("Offers"), default=str))
            j = en_parte[clave]
            en_parte[clave] += 1
            if not es_op:
                puntas[tk] = (mejor(m.get("Bids")), mejor(m.get("Offers")))
                continue
            if j < incluidas[clave]:
                continue
            p = num(m.get("Price"))
            bc, bv = puntas.get(tk, (None, None))
            lado = "C" if bv and p and p >= bv else "V" if bc and p and p <= bc else "M"
            ops.append((tk, ts, p, num(m.get("VolumeAmount")) or 0.0, num(m.get("VolumeCurrency")) or 0.0,
                        num(m.get("VolumeTotalAmount")), lado, num(m.get("VarDay")),
                        num(m.get("MaxDay")), num(m.get("MinDay")), str(m.get("Type", "ACCIONES"))))
        for clave, n in en_parte.items():
            incluidas[clave] = max(incluidas[clave], n)
    ops.sort(key=lambda r: (r[0], r[1]))
    return ops


def leer_afuera(partes):
    """Finnhub: operaciones (símbolo, ts, precio, volumen) y cierres anteriores."""
    trades, previos, vistos = [], {}, set()
    for parte in sorted(partes):
        for renglon in leer_gz(parte):
            if "\t" not in renglon:
                continue
            _, crudo = renglon.split("\t", 1)
            try:
                m = json.loads(crudo)
            except ValueError:
                continue
            if m.get("type") == "previo" and m.get("pc"):
                previos[m["s"]] = float(m["pc"])
            elif m.get("type") == "trade":
                for d in m.get("data") or []:
                    clave = (d.get("s"), d.get("t"), d.get("p"), d.get("v"))
                    if clave in vistos:
                        continue
                    vistos.add(clave)
                    try:
                        trades.append((d["s"], datetime.fromtimestamp(d["t"] / 1000), float(d["p"]), float(d.get("v") or 0)))
                    except (KeyError, TypeError, ValueError):
                        pass
    trades.sort(key=lambda r: (r[0], r[1]))
    return trades, previos


# ---------- cálculos ----------

def presion(g):
    c = sum(r[4] for r in g if r[6] == "C")
    v = sum(r[4] for r in g if r[6] == "V")
    return (c - v) / (c + v) * 100 if c + v else None


def ar(v, dec=0):
    if v is None:
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def sig(v, dec=1, suf="%"):
    return "—" if v is None else ("+" if v > 0 else "") + ar(v, dec) + suf


def ultimo(ops, tk):
    g = [r for r in ops if r[0] == tk]
    return g[-1] if g else None


def pantalla(ops, afuera=([], {})):
    trades, previos = afuera
    locales = [r for r in ops if r[10] == "ACCIONES"]
    if not locales and not trades:
        return "# Pantalla en vivo\n\nTodavía no hay operaciones grabadas hoy.\n"
    tiempos = [r[1] for r in locales] + [t[1] for t in trades]
    ahora = max(tiempos)
    desde = ahora - timedelta(minutes=VENTANA_MIN)
    inicio = min(r[1] for r in locales) if locales else ahora
    tramos = max(((ahora - inicio).total_seconds() / 60) / VENTANA_MIN, 1)

    # --- Nueva York (Finnhub) ---
    ny = {}
    por_sim = defaultdict(list)
    for t in trades:
        por_sim[t[0]].append(t)
    for s, g in por_sim.items():
        pc = previos.get(s)
        u = g[-1]
        ny[s] = {"p": u[2], "hora": u[1], "var": (u[2] / pc - 1) * 100 if pc else None,
                 "n10": sum(1 for x in g if x[1] > desde)}

    # --- dólar por bonos (PPI) ---
    def precio(tk):
        u = ultimo(ops, tk)
        return u[2] if u else None
    dolar = {}
    for b in ("AL30", "GD30"):
        p, d, c = precio(b), precio(b + "D"), precio(b + "C")
        dolar[b] = {"MEP": p / d if p and d else None, "CCL": p / c if p and c else None}
    ccls = [v["CCL"] for v in dolar.values() if v["CCL"]]
    ccl = statistics.median(ccls) if ccls else None

    # --- panel local ---
    por_tk = defaultdict(list)
    for r in locales:
        por_tk[r[0]].append(r)
    filas = []
    for tk, g in por_tk.items():
        u = g[-1]
        rec = [r for r in g if r[1] > desde]
        nom = sum(r[3] for r in g)
        monto = (u[5] or 0) + u[4] if u[5] is not None else sum(r[4] for r in g)
        var = u[7] * 100 if u[7] is not None else None
        p10 = presion(rec) if len(rec) >= 10 else None
        ritmo = len(rec) / (len(g) / tramos) if g else None
        brecha = None
        adr = ADR_DE.get(tk)
        if adr and adr[0] in ny and ccl:
            paridad = ny[adr[0]]["p"] * ccl / adr[1]
            brecha = (u[2] / paridad - 1) * 100
        filas.append({"tk": tk, "p": u[2], "var": var, "min": u[9], "max": u[8], "n": len(g), "monto": monto,
                      "vwap": sum(r[4] for r in g) / nom if nom else None, "pd": presion(g), "n10": len(rec),
                      "p10": p10, "ritmo": ritmo, "brecha": brecha, "adr_var": ny.get(adr[0], {}).get("var") if adr else None})
    filas.sort(key=lambda f: -f["monto"])
    en_rojo = [f for f in filas if f["var"] is not None and f["var"] < 0]
    pct_rojo = 100 * len(en_rojo) / len(filas) if filas else None
    p10_panel = presion([r for r in locales if r[1] > desde])
    var_bancos = [f["var"] for f in filas if f["tk"] in BANCOS and f["var"] is not None]
    var_adr_bancos = [ny[s]["var"] for s in ("GGAL", "BMA", "SUPV", "BBAR") if s in ny and ny[s]["var"] is not None]

    # --- semáforo general ---
    senales = []
    if pct_rojo is not None and pct_rojo >= 60:
        senales.append(f"panel en rojo ({ar(pct_rojo)}% de las especies)")
    if p10_panel is not None and p10_panel <= -30:
        senales.append(f"presión vendedora del panel en 10' ({sig(p10_panel, 0)})")
    if var_bancos and var_adr_bancos and statistics.mean(var_bancos) < -1 and statistics.mean(var_adr_bancos) < -1:
        senales.append("bancos locales y sus ADR caen juntos")
    spy, vixy = ny.get("SPY", {}).get("var"), ny.get("VIXY", {}).get("var")
    if (spy is not None and spy < -1) or (vixy is not None and vixy > 5):
        senales.append("Wall Street en baja o miedo en suba")
    luz = "🟢 verde" if not senales else "🟡 amarillo" if len(senales) == 1 else "🔴 rojo"

    lin = [f"# Pantalla en vivo — {ahora:%d/%m/%Y}", "",
           f"Último dato: **{ahora:%H:%M:%S}**. Se actualiza cada {VENTANA_MIN} minutos; recargá la página para ver la última.", "",
           f"## Semáforo: {luz} ({len(senales)} de 4 señales)", ""]
    lin += [f"- {s}" for s in senales] or ["- sin señales rojas"]
    lin += ["", f"Panel: {len(filas) - len(en_rojo)} de {len(filas)} en verde o sin cambio; "
                f"presión 10' del panel {sig(p10_panel, 0)}.", ""]

    # --- afuera ---
    if ny:
        lin += ["## Afuera ahora (Nueva York, Finnhub en tiempo real)", "",
                "| Grupo | Símbolo | Último US$ | Var. | Ops 10' | Hora |", "|---|---|---|---|---|---|"]
        for grupo, sims in GRUPOS_AFUERA:
            for s in sims:
                if s in ny:
                    x = ny[s]
                    lin.append(f"| {grupo} | {s} | {ar(x['p'], 2)} | {sig(x['var'], 2)} | {x['n10']} | {x['hora']:%H:%M:%S} |")
        lin.append("")
    if any(v["MEP"] or v["CCL"] for v in dolar.values()):
        lin += ["## Dólar en vivo (bonos por PPI)", "", "| Bono | MEP | CCL | Diferencia CCL/MEP |", "|---|---|---|---|"]
        for b, v in dolar.items():
            dif = (v["CCL"] / v["MEP"] - 1) * 100 if v["MEP"] and v["CCL"] else None
            lin.append(f"| {b} | {ar(v['MEP'], 2)} | {ar(v['CCL'], 2)} | {sig(dif, 2)} |")
        lin.append("")
    cedears = [r for r in ops if r[10] == "CEDEARS"]
    if cedears:
        lin += ["## CEDEARs (BYMA, tiempo real)", "", "| CEDEAR | Último $ | Var. | Ops |", "|---|---|---|---|"]
        for tk in sorted({r[0] for r in cedears}):
            g = [r for r in cedears if r[0] == tk]
            lin.append(f"| {tk} | {ar(g[-1][2], 0)} | {sig(g[-1][7] * 100 if g[-1][7] is not None else None, 2)} | {len(g)} |")
        lin.append("")
    usa_ppi = ultimo(ops, "GGAL.O")
    if usa_ppi and "GGAL" in ny:
        lin += [f"Control de demora de PPI para Nueva York: GGAL por PPI {ar(usa_ppi[2], 2)} a las {usa_ppi[1]:%H:%M:%S}; "
                f"por Finnhub {ar(ny['GGAL']['p'], 2)} a las {ny['GGAL']['hora']:%H:%M:%S}.", ""]

    # --- panel ---
    lin += ["## Panel local", "",
            "| Especie | Último | Var. día | Mín – Máx | Ops | Monto $M | VWAP | Presión día | Ops 10' | Presión 10' | Ritmo | Brecha ADR | Señales salida |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for f in filas:
        n_sal = sum([f["p10"] is not None and f["p10"] <= -40,
                     pct_rojo is not None and pct_rojo >= 60,
                     f["var"] is not None and f["var"] < 0 and f["adr_var"] is not None and f["adr_var"] < -1,
                     f["ritmo"] is not None and f["ritmo"] >= 1.5 and f["p10"] is not None and f["p10"] < 0])
        dec = 2 if f["p"] and f["p"] < 100 else 1 if f["p"] and f["p"] < 1000 else 0
        lin.append(f"| {f['tk']} | {ar(f['p'], dec)} | {sig(f['var'], 2)} | {ar(f['min'], dec)} – {ar(f['max'], dec)} | "
                   f"{ar(f['n'])} | {ar(f['monto'] / 1e6, 1)} | {ar(f['vwap'], dec)} | {sig(f['pd'], 0)} | {ar(f['n10'])} | "
                   f"{sig(f['p10'], 0)} | {ar(f['ritmo'], 1) + 'x' if f['ritmo'] is not None else '—'} | "
                   f"{sig(f['brecha'], 2)} | {n_sal} de 4 |")
    lin += ["", "**Cómo leerla**", "",
            "- **Semáforo**: cuenta 4 señales rojas (panel en rojo, presión vendedora del panel, bancos y ADR cayendo juntos, "
            "Wall Street en baja o miedo en suba). Con 2 o más: día para caución o para salir.",
            "- **Ops**: operaciones acumuladas en el día. **Monto**: monto oficial del día en millones de pesos.",
            "- **Presión**: (compras agresivas − ventas agresivas) / total, en monto. La de 10' se muestra solo con 10 operaciones o más.",
            f"- **Ritmo**: operaciones de los últimos {VENTANA_MIN} minutos contra el promedio del día. 1,0x = normal.",
            "- **Brecha ADR**: precio local contra la paridad del ADR al CCL de los bonos. Positiva = la local está más cara que el ADR.",
            "- **Señales salida**: presión 10' ≤ −40%; panel en rojo; la especie y su ADR caen (ADR < −1%); ritmo alto con ventas. "
            "Con 2 o más: no hay recuperación a la vista.",
            "- Plazo 24 hs. Ordenada por monto operado."]
    return "\n".join(lin) + "\n"


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--afuera" in args:
        i = args.index("--afuera")
        ppi_partes, fh_partes = args[:i], args[i + 1:]
    else:
        ppi_partes, fh_partes = args, []
    sys.stdout.write(pantalla(leer(ppi_partes), leer_afuera(fh_partes)))
