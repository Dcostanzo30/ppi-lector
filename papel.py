"""Operaciones en papel (sin dinero real): registro en papel/operaciones.csv y seguimiento diario con la foto del mercado total.
Regla anti mirar el futuro: la entrada es una orden límite fijada de antemano, válida entre entrada_desde y entrada_hasta.
Si el día abre por debajo del límite, entra a la apertura; si no, entra al límite cuando el mínimo del día lo toca.
Cada noche, con el máximo y mínimo del día (A-24HS), marca si tocó objetivo o corte; si tocan los dos el mismo día, cuenta el corte.
Escribe papel/ESTADO.md. Uso: python papel.py
"""
import csv, glob
from pathlib import Path

REG = Path("papel/operaciones.csv")


def fotos():
    out = {}
    for f in sorted(glob.glob("mercado_total/????-??-??.csv")):
        d = Path(f).stem
        with open(f, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["plazo"] == "A-24HS" and r["price"]:
                    out.setdefault(r["ticker"], {})[d] = (float(r["price"]), float(r["max"] or r["price"]), float(r["min"] or r["price"]), float(r["openingPrice"] or r["price"]))
    return out


def ar(x, d=2):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    ops = list(csv.DictReader(open(REG, encoding="utf-8")))
    px = fotos()
    l = ["# Operaciones en papel", "", "Sin dinero real. Entrada con orden límite fijada de antemano (si abre por debajo, a la apertura); objetivo y corte con el máximo y mínimo de cada día (si toca los dos el mismo día, cuenta el corte). Resultado neto de costos de ida y vuelta.", "",
         "| Id | Especie | Entrada | Último | Objetivo | Corte | Resultado neto | Estado |", "|---|---|---|---|---|---|---|---|"]
    for o in ops:
        serie = px.get(o["especie"], {})
        ent, f_ent = None, None
        lim = float(o["entrada_limite"])
        for d in sorted(k for k in serie if o["entrada_desde"] <= k <= o["entrada_hasta"]):
            c, hi, lo, ap = serie[d]
            if ap <= lim: ent, f_ent = ap, d; break
            if lo <= lim: ent, f_ent = lim, d; break
        estado, ultimo, salida = ("esperando entrada" if not serie or max(serie) < o["entrada_hasta"] else "sin entrada (venció la orden)"), None, None
        if ent:
            estado = f"abierta desde el {f_ent}"
            c0 = serie[f_ent]
            if c0[2] <= float(o["corte"]): estado, salida = f"cerrada por corte el {f_ent}", float(o["corte"])
            ultimo = c0[0]
            for d in sorted(k for k in serie if k > f_ent) if not salida else []:
                c, hi, lo, ap = serie[d]; ultimo = c
                if lo <= float(o["corte"]): estado, salida = f"cerrada por corte el {d}", min(float(o["corte"]), ap); break
                if hi >= float(o["objetivo"]): estado, salida = f"cerrada por objetivo el {d}", max(float(o["objetivo"]), ap) if ap >= float(o["objetivo"]) else float(o["objetivo"]); break
                if d >= o["vence"]: estado, salida = f"vencida el {d}", c; break
        ref = salida or ultimo
        res = f"{ar(((ref / ent) * (1 - float(o['costo_ida_vuelta_pct']) / 100) - 1) * 100)}%" if ent and ref else "—"
        l.append(f"| {o['id']} | {o['especie']} | {ar(ent) if ent else 'límite ' + ar(lim)} | {ar(ultimo) if ultimo else '—'} | {ar(float(o['objetivo']))} | {ar(float(o['corte']))} | {res} | {estado} (vence {o['vence']}) |")
    l += ["", "## Motivos", ""] + [f"- **{o['id']} {o['especie']}**: {o['entrada_regla']}, válida del {o['entrada_desde']} al {o['entrada_hasta']}. {o['motivo']}" for o in ops] + [""]
    Path("papel/ESTADO.md").write_text("\n".join(l), encoding="utf-8")
    print("\n".join(l[:6 + len(ops)]))


if __name__ == "__main__":
    main()
# FIN papel.py
