"""Pantalla en vivo: resume lo grabado por el lector hasta este momento, una fila por especie.

Uso: python pantalla.py archivo1.txt.gz [archivo2.txt.gz ...] > pantalla.md
Junta las partes del día (turno mañana y tarde), descarta las operaciones repetidas por el cruce
de turnos y clasifica cada operación por el lado que la inició (comprador o vendedor).
"""
import json, re, sys, zlib
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

VENTANA_MIN = 10
_SIN_COMILLAS = re.compile(r'"(\w+)":([^,\[\]{}"]+)')


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


def leer(partes):
    incluidas = defaultdict(int)
    ops = []   # (ticker, ts, precio, nominales, monto, acumulado_previo, lado, var_dia, max_dia, min_dia)
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
                        num(m.get("MaxDay")), num(m.get("MinDay"))))
        for clave, n in en_parte.items():
            incluidas[clave] = max(incluidas[clave], n)
    ops.sort(key=lambda r: (r[0], r[1]))
    return ops


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


def pantalla(ops):
    if not ops:
        return "# Pantalla en vivo\n\nTodavía no hay operaciones grabadas hoy.\n"
    ahora = max(r[1] for r in ops)
    desde = ahora - timedelta(minutes=VENTANA_MIN)
    inicio = min(r[1] for r in ops)
    tramos = max(((ahora - inicio).total_seconds() / 60) / VENTANA_MIN, 1)
    por_tk = defaultdict(list)
    for r in ops:
        por_tk[r[0]].append(r)
    filas = []
    for tk, g in por_tk.items():
        u = g[-1]
        rec = [r for r in g if r[1] > desde]
        nom = sum(r[3] for r in g)
        monto_oficial = (u[5] or 0) + u[4] if u[5] is not None else sum(r[4] for r in g)
        filas.append((tk, u[2], u[7] * 100 if u[7] is not None else None, u[9], u[8], len(g), monto_oficial,
                      sum(r[4] for r in g) / nom if nom else None, presion(g), len(rec), presion(rec),
                      len(rec) / (len(g) / tramos) if g else None, u[1]))
    filas.sort(key=lambda f: -f[6])
    lin = [f"# Pantalla en vivo — {ahora:%d/%m/%Y}", "",
           f"Último dato: **{ahora:%H:%M:%S}**. Se actualiza cada {VENTANA_MIN} minutos; recargá la página para ver la última.", "",
           "| Especie | Último | Var. día | Mín – Máx | Ops | Monto $M | VWAP | Presión día | Ops 10' | Presión 10' | Ritmo |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for tk, ult, var, mn, mx, n, monto, vwap, pd_, n10, p10, ritmo, ts in filas:
        dec = 2 if ult and ult < 100 else 1 if ult and ult < 1000 else 0
        lin.append(f"| {tk} | {ar(ult, dec)} | {sig(var, 2)} | {ar(mn, dec)} – {ar(mx, dec)} | {ar(n)} | {ar(monto / 1e6, 1)} | "
                   f"{ar(vwap, dec)} | {sig(pd_, 0)} | {ar(n10)} | {sig(p10, 0) if n10 >= 10 else '—'} | {ar(ritmo, 1) + 'x' if ritmo is not None else '—'} |")
    lin += ["", "**Cómo leerla**", "",
            "- **Ops**: operaciones acumuladas en el día. **Monto**: monto oficial del día en millones de pesos.",
            "- **Presión**: (compras agresivas − ventas agresivas) / total, en monto. +100% = solo compradores golpeando la punta vendedora; −100% = solo vendedores.",
            f"- **Ops 10'** y **Presión 10'**: lo mismo en los últimos {VENTANA_MIN} minutos (la presión se muestra solo con 10 operaciones o más).",
            f"- **Ritmo**: operaciones de los últimos {VENTANA_MIN} minutos contra el promedio de cada {VENTANA_MIN} minutos del día. 1,0x = normal; 2x = el doble.",
            "- Ordenada por monto operado. Plazo 24 hs."]
    return "\n".join(lin) + "\n"


if __name__ == "__main__":
    sys.stdout.write(pantalla(leer(sys.argv[1:])))
