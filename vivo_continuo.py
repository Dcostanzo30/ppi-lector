# Continuo en vivo: las ruedas anteriores enganchadas con la de hoy mientras ocurre, y la comparacion
# de hoy contra cada dia anterior A LA MISMA HORA (1a operacion, operaciones, nominales, monto).
# Uso (dentro del repositorio de datos): python vivo_continuo.py SALIDA parte1.txt.gz [parte2 ...]
# Escribe SALIDA/vivo.md y SALIDA/continuo/<ESPECIE>.png
import csv, gzip, os, sys
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pantalla import leer, ar

print("vivo_continuo: arranca", flush=True)
PROC = Path("procesado")
DIAS_ATRAS = 5
RELATO = ["GGAL", "YPFD", "PAMP", "BMA", "SUPV", "BBAR"]   # especies con comparacion en palabras
DIA_SEM = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
AZUL, NARANJA, GRIS = "#2a78d6", "#eb6834", "#a3a29b"
TINTA, SEC, GRILLA, FONDO, HOY = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb", "#eef4fc"


def etiqueta(fecha):
    d = datetime.strptime(fecha, "%Y-%m-%d")
    return f"{DIA_SEM[d.weekday()]} {d:%d/%m}"


def leer_dia(fecha):
    """Operaciones de una rueda procesada: por especie, lista de (ts, precio, nominales, monto, monto_oficial_acum, lado)."""
    ops = {}
    with gzip.open(PROC / fecha / "operaciones.csv.gz", "rt") as h:
        for r in csv.DictReader(h):
            try:
                ts = datetime.fromisoformat(r["hora"])
                monto = float(r["monto"])
                previo = float(r["monto_acumulado_previo"]) if r.get("monto_acumulado_previo") else None
            except ValueError:
                continue
            ops.setdefault(r["ticker"], []).append((ts, float(r["precio"]), float(r["nominales"]), monto,
                                                    previo + monto if previo is not None else None, r["lado_agresor"]))
    for L in ops.values():
        L.sort()
    arranque = min(L[0][0] for L in ops.values()) if ops else None
    completa = arranque is not None and arranque.time() <= datetime.strptime("10:31", "%H:%M").time()
    return ops, completa, arranque


def hasta_hora(L, hhmmss):
    return [x for x in L if x[0].time() <= hhmmss]


def medidas(L, completa):
    if not L:
        return None
    oficial = next((x[4] for x in reversed(L) if x[4] is not None), None)
    return {"primera": L[0][0].time() if completa else None, "ops": len(L) if completa else None,
            "nom": sum(x[2] for x in L) if completa else None,
            "monto": oficial if oficial is not None else (sum(x[3] for x in L) if completa else None)}


def comparar(hoy, otro, clave):
    if not hoy or not otro or hoy.get(clave) is None or otro.get(clave) is None:
        return None
    if clave == "primera":
        a = datetime.combine(datetime.today(), hoy[clave]); b = datetime.combine(datetime.today(), otro[clave])
        return (a - b).total_seconds()
    return (hoy[clave] / otro[clave] - 1) * 100 if otro[clave] else None


def celda(hoy, otro):
    if otro is None:
        return "sin operaciones"
    partes = []
    s = comparar(hoy, otro, "primera")
    if s is not None:
        partes.append("1ª " + ("igual" if abs(s) < 1 else ("+" if s > 0 else "−") + (f"{abs(s):.0f}s" if abs(s) < 120 else f"{abs(s) / 60:.0f}'")))
    for k, nom in (("ops", "ops"), ("nom", "nom"), ("monto", "$")):
        v = comparar(hoy, otro, k)
        if v is not None:
            partes.append(f"{nom} {'+' if v > 0 else ''}{v:.0f}%".replace(".", ","))
    return " · ".join(partes) or "sin dato"


def relato(tk, hoy, previos):
    """previos: lista de (fecha, medidas) del más reciente al más viejo."""
    if not hoy:
        return f"- **{tk}**: todavía sin operaciones hoy."
    frases = []
    for clave, nom, mas, menos in (("primera", "La 1ª operación", "más tarde que", "más temprano que"),
                                   ("ops", "Operaciones", "más que", "menos que"),
                                   ("nom", "Volumen nominal", "más que", "menos que"),
                                   ("monto", "Monto negociado", "más que", "menos que")):
        arriba, abajo = [], []
        for f, m in previos:
            v = comparar(hoy, m, clave)
            if v is None or (clave == "primera" and abs(v) < 1):
                continue
            txt = etiqueta(f) + (f" ({'+' if v > 0 else '−'}{abs(v):.0f}s)" if clave == "primera" and abs(v) < 120 else
                                 f" ({'+' if v > 0 else '−'}{abs(v) / 60:.0f}')" if clave == "primera" else
                                 f" ({'+' if v > 0 else ''}{v:.0f}%)".replace(".", ","))
            (arriba if v > 0 else abajo).append(txt)
        if not arriba and not abajo:
            continue
        valor = hoy[clave].strftime("%H:%M:%S") if clave == "primera" else (ar(hoy[clave] / 1e6, 1) + " M$" if clave == "monto" else ar(hoy[clave]))
        t = f"{nom} ({valor}): "
        t += "; ".join(x for x in ([f"{mas} {', '.join(arriba)}"] if arriba else []) + ([f"{menos} {', '.join(abajo)}"] if abajo else []))
        frases.append(t)
    return f"- **{tk}**: " + ". ".join(frases) + "."


def leer_tablero(ruta=Path("vivo/pantalla.md")):
    """Toma la pantalla recién escrita: el semáforo general y, por especie, las señales de salida (0 a 4)."""
    try:
        texto = ruta.read_text(encoding="utf-8")
    except Exception:
        return "", {}, ""
    lineas = texto.splitlines()
    semaforo = []
    for i, l in enumerate(lineas):
        if l.startswith("## Semáforo"):
            semaforo = [l.replace("## ", "**") + "**"]
            for m in lineas[i + 1:]:
                if m.startswith("## "):
                    break
                if m.strip():
                    semaforo.append(m)
            break
    luces = {}
    cab = None
    for l in lineas:
        if l.startswith("| Especie | Último"):
            cab = [c.strip() for c in l.strip("|").split("|")]
            continue
        if cab and l.startswith("| ") and not l.startswith("|---"):
            c = [x.strip() for x in l.strip("|").split("|")]
            if len(c) != len(cab):
                continue
            fila = dict(zip(cab, c))
            try:
                n = int(fila.get("Señales salida", "0 de 4").split()[0])
            except ValueError:
                n = 0
            luces[fila["Especie"]] = {"luz": "🔴" if n >= 2 else "🟡" if n == 1 else "🟢", "n": n,
                                      "var": fila.get("Var. día", "—"), "p10": fila.get("Presión 10'", "—"),
                                      "brecha": fila.get("Brecha ADR", "—")}
        elif cab and not l.startswith("|"):
            cab = None
    return "\n".join(semaforo), luces, texto


def dibujar(tk, tramos, titulo, salida):
    fig, ax = plt.subplots(3, 1, figsize=(11, 8), sharex=True, gridspec_kw={"height_ratios": [2, 1.1, 1.1], "hspace": 0.08})
    fig.patch.set_facecolor(FONDO)
    x0, marcas, etiq, cortes = 0, [], [], []
    tot = sum(len(L) for _, L, _ in tramos)
    for fecha, L, es_hoy in tramos:
        x = list(range(x0, x0 + len(L)))
        col = [AZUL if r[5] == "C" else NARANJA if r[5] == "V" else GRIS for r in L]
        if es_hoy:
            for a in ax:
                a.axvspan(x0 - 0.5, x0 + max(len(L), 1) - 0.5, color=HOY, zorder=0)
        ax[0].plot(x, [r[1] for r in L], color=TINTA, lw=1.4 if es_hoy else 1.0)
        an = 0.6 if tot > 3000 else 1.0
        ax[1].vlines(x, 0, [r[3] / 1e6 for r in L], colors=col, linewidth=an)
        ax[2].vlines(x, 0, [r[2] for r in L], colors=col, linewidth=an)
        marcas.append(x0 + len(L) / 2)
        etiq.append(("HOY " if es_hoy else "") + etiqueta(fecha))
        if x0:
            cortes.append(x0 - 0.5)
        x0 += len(L)
    ax[1].set_ylim(bottom=0); ax[2].set_ylim(bottom=0)
    for a in ax:
        a.set_facecolor(FONDO); a.grid(axis="y", color=GRILLA, lw=0.8); a.set_axisbelow(True)
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
        a.tick_params(colors=SEC, labelsize=9)
        for c in cortes:
            a.axvline(c, color="#c3c2b7", lw=0.8, ls="--")
    ax[0].set_ylabel("Precio ($)", color=SEC); ax[1].set_ylabel("Monto (M$)", color=SEC); ax[2].set_ylabel("Nominales", color=SEC)
    ax[2].yaxis.set_major_formatter(FuncFormatter(lambda v, _: ar(v)))
    ax[2].set_xticks(marcas); ax[2].set_xticklabels(etiq)
    ax[2].set_xlabel(f"Operaciones en el orden de la cinta ({ar(tot)}); el tramo sombreado es hoy", color=SEC)
    ax[1].legend(handles=[Patch(color=AZUL, label="Compra agresiva"), Patch(color=NARANJA, label="Venta agresiva")],
                 loc="upper left", bbox_to_anchor=(0, 1.2), ncol=2, fontsize=8.5, frameon=False)
    fig.suptitle(titulo, x=0.06, ha="left", color=TINTA, fontsize=12)
    salida.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(salida, dpi=85, bbox_inches="tight", facecolor=FONDO)
    plt.close(fig)


def main():
    salida = Path(sys.argv[1])
    crudo = [r for r in leer(sys.argv[2:]) if r[10] == "ACCIONES"]
    if not crudo:
        print("sin operaciones hoy"); return
    hoy_tk = {}
    for r in crudo:   # (ts, precio, nominales, monto, monto_oficial_acum, lado)
        hoy_tk.setdefault(r[0], []).append((r[1], r[2], r[3], r[4], (r[5] + r[4]) if r[5] is not None else None, r[6]))
    ahora = max(r[1] for r in crudo)
    fecha_hoy = ahora.strftime("%Y-%m-%d")
    hhmmss = ahora.time()
    previas = sorted(p.name for p in PROC.iterdir() if (p / "operaciones.csv.gz").exists() and p.name < fecha_hoy)[-DIAS_ATRAS:] if PROC.exists() else []
    dias = {f: leer_dia(f) for f in previas}
    m_hoy = {tk: medidas(L, True) for tk, L in hoy_tk.items()}
    semaforo, luces, tablero = leer_tablero()
    lin = [f"# En vivo: hoy contra las ruedas anteriores — {etiqueta(fecha_hoy)}, {hhmmss:%H:%M:%S}", ""]
    if semaforo:
        lin += [semaforo, "", "Luz por especie: 🟢 ninguna señal de salida · 🟡 una · 🔴 dos o más (no hay recuperación a la vista). "
                "El tablero completo está al final de esta página.", ""]
    lin += [
           f"Cada día anterior se corta a la misma hora de hoy ({hhmmss:%H:%M:%S}). "
           "1ª = cuánto después (+) o antes (−) llegó hoy la primera operación; ops, nom y $ = hoy contra ese día, en %.", ""]
    notas = [f"{etiqueta(f)}: cinta desde {d[2]:%H:%M} (sin 1ª operación, ops ni nominales; el monto sale del acumulado oficial)"
             for f, d in dias.items() if not d[1] and d[2]]
    if notas:
        lin += ["Cintas incompletas: " + "; ".join(notas) + ".", ""]
    previos_por_tk = {tk: [(f, medidas(hasta_hora(dias[f][0].get(tk, []), hhmmss), dias[f][1])) for f in reversed(previas)]
                      for tk in hoy_tk}
    lin += ["## En palabras", ""]
    lin += [relato(tk, m_hoy.get(tk), previos_por_tk.get(tk, [])).replace(f"- **{tk}**", f"- {luces[tk]['luz']} **{tk}** "
                   f"({luces[tk]['var']}, presión 10' {luces[tk]['p10']})" if tk in luces else f"- **{tk}**", 1)
            for tk in RELATO if tk in hoy_tk]
    orden = sorted(hoy_tk, key=lambda tk: -(m_hoy[tk]["monto"] or 0))
    cab = " | ".join(etiqueta(f) for f in reversed(previas))
    lin += ["", "## Todo el panel", "", f"| Luz | Especie | Var. | Hoy: 1ª op · ops · M$ | {cab} |", "|---|---|---|---|" + "---|" * len(previas)]
    for tk in orden:
        m = m_hoy[tk]
        celdas = " | ".join(celda(m, mp) for _, mp in previos_por_tk[tk])
        lz = luces.get(tk, {})
        lin.append(f"| {lz.get('luz', '·')} | {tk} | {lz.get('var', '—')} | {m['primera']:%H:%M:%S} · {ar(m['ops'])} · {ar((m['monto'] or 0) / 1e6, 1)} | {celdas} |")
    lin += ["", "## Gráficos continuos", ""]
    for tk in orden:
        tramos = [(f, dias[f][0].get(tk, []), False) for f in previas if dias[f][0].get(tk)] + [(fecha_hoy, hoy_tk[tk], True)]
        dibujar(tk, tramos, f"{tk}: {len(tramos) - 1} ruedas anteriores + hoy hasta las {hhmmss:%H:%M}",
                salida / "continuo" / f"{tk}.png")
        lin += [f"### {tk}", "", f"

![{tk}](continuo/{tk}.png)

", ""]
    if tablero:
        lin += ["---", "", "# Tablero completo (la pantalla en vivo)", ""] + [l.replace("# Pantalla en vivo", "## Pantalla en vivo", 1) if l.startswith("# Pantalla") else l
                                                                          for l in tablero.splitlines()]
    previo = Path("tablero/hoy.md")
    if previo.exists():
        lin += ["", "---", "", "# Tablero previo (ayer, la noche y lo esperado para hoy)", ""] + \
               [("#" + l) if l.startswith("#") else l for l in previo.read_text(encoding="utf-8").splitlines()]
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "vivo.md").write_text("\n".join(lin) + "\n", encoding="utf-8")
    print("vivo_continuo: FIN", len(orden), "especies,", len(previas), "ruedas anteriores", flush=True)


if __name__ == "__main__":
    main()
# FIN vivo_continuo.py
