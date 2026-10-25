"""Operaciones en papel (sin dinero real): registro en papel/operaciones.csv y seguimiento diario con la foto del mercado total.
Regla anti mirar el futuro: la entrada se fija con el cierre de la fecha indicada, decidida antes de conocerlo.
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
                    out.setdefault(r["ticker"], {})[d] = (float(r["price"]), float(r["max"] or r["price"]), float(r["min"] or r["price"]))
    return out


def ar(x, d=2):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    ops = list(csv.DictReader(open(REG, encoding="utf-8")))
    px = fotos()
    l = ["# Operaciones en papel", "", "Sin dinero real. Entrada al cierre de la fecha fijada de antemano; objetivo y corte con el máximo y mínimo de cada día. Resultado neto de costos de ida y vuelta.", "",
         "| Id | Especie | Entrada | Último | Objetivo | Corte | Resultado neto | Estado |", "|---|---|---|---|---|---|---|---|"]
    for o in ops:
        serie = px.get(o["especie"], {})
        ent = float(o["entrada_precio"]) if o["entrada_precio"] else (serie.get(o["entrada_fecha"], (None,))[0])
        estado, ultimo, salida = "esperando entrada", None, None
        if ent:
            estado = "abierta"
            for d in sorted(k for k in serie if k > o["entrada_fecha"]):
                c, hi, lo = serie[d]; ultimo = c
                if lo <= float(o["corte"]): estado, salida = f"cerrada por corte el {d}", float(o["corte"]); break
                if hi >= float(o["objetivo"]): estado, salida = f"cerrada por objetivo el {d}", float(o["objetivo"]); break
                if d >= o["vence"]: estado, salida = f"vencida el {d}", c; break
            ultimo = ultimo or ent
        ref = salida or ultimo
        res = f"{ar(((ref / ent) * (1 - float(o['costo_ida_vuelta_pct']) / 100) - 1) * 100)}%" if ent and ref else "—"
        l.append(f"| {o['id']} | {o['especie']} | {ar(ent) if ent else o['entrada_regla']} | {ar(ultimo) if ultimo else '—'} | {ar(float(o['objetivo']))} | {ar(float(o['corte']))} | {res} | {estado} (vence {o['vence']}) |")
    l += ["", "## Motivos", ""] + [f"- **{o['id']} {o['especie']}**: {o['motivo']}" for o in ops] + [""]
    Path("papel/ESTADO.md").write_text("\n".join(l), encoding="utf-8")
    print("\n".join(l[:6 + len(ops)]))


if __name__ == "__main__":
    main()
# FIN papel.py
