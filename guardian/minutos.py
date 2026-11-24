"""Guardián de minutos de ppi--datos (pedido de Domingo, 24/11/2026: "que no nos vuelva a pasar de superar los 2000 minutos").
Corre en ppi-lector (público, sin consumo). Suma los minutos facturables del mes de cada corrida de ppi--datos (endpoint
timing de GitHub; si no responde, la duración de la corrida redondeada hacia arriba) y actúa por umbral:
  50%: aviso.   70%: pausa lo no esencial.   85%: queda solo lo esencial.
El 1° de cada mes reactiva lo que haya pausado este guardián (anotado en control/guardian_pausados.txt de ppi--datos).
Escribe control/MINUTOS.md y control/minutos.csv en ppi--datos. Uso: python guardian/minutos.py <carpeta de ppi--datos>
Variables: DATOS_TOKEN (lectura y escritura en ppi--datos y en sus workflows), CUPO (por defecto 2000).
"""
import datetime as dt, json, math, os, sys
from pathlib import Path
import requests

REPO = "Dcostanzo30/ppi--datos"
CUPO = int(os.environ.get("CUPO", "2000"))
ESENCIALES = {"procesar.yml", "bateria.yml"}                 # lo último que se apaga (Domingo, 24/11)
NO_ESENCIALES = ["graficos.yml", "semanal.yml", "rutas.yml", "diario.yml", "radar_noche.yml", "balances.yml",
                 "novedades.yml", "novedades_bcra.yml", "fuentes.yml"]   # en este orden se pausan al 70%
H = {"Authorization": f"Bearer {os.environ['DATOS_TOKEN']}", "Accept": "application/vnd.github+json"}
API = f"https://api.github.com/repos/{REPO}"


def get(url, **p):
    r = requests.get(url, headers=H, params=p, timeout=60); r.raise_for_status(); return r.json()


def minutos_del_mes(desde):
    corridas, pagina = [], 1
    while True:
        j = get(f"{API}/actions/runs", created=f">={desde}", per_page=100, page=pagina)
        corridas += j.get("workflow_runs", [])
        if len(j.get("workflow_runs", [])) < 100: break
        pagina += 1
    por, total = {}, 0
    for c in corridas:
        if c.get("status") != "completed": continue
        m = None
        try:
            t = get(f"{API}/actions/runs/{c['id']}/timing")
            ms = sum(v.get("total_ms", 0) for v in (t.get("billable") or {}).values())
            m = math.ceil(ms / 60000) if ms else None
            if m is None and t.get("run_duration_ms"): m = math.ceil(t["run_duration_ms"] / 60000)
        except Exception:
            pass
        if m is None:
            a = dt.datetime.fromisoformat(c["run_started_at"].replace("Z", "+00:00")); b = dt.datetime.fromisoformat(c["updated_at"].replace("Z", "+00:00"))
            m = math.ceil((b - a).total_seconds() / 60)
        arch = c.get("path", "").split("/")[-1] or c.get("name")
        por[arch] = por.get(arch, 0) + m; total += m
    return total, por, len(corridas)


def estado(arch):
    try: return get(f"{API}/actions/workflows/{arch}").get("state")
    except Exception: return "s/d"


def cambiar(arch, accion):
    r = requests.put(f"{API}/actions/workflows/{arch}/{accion}", headers=H, timeout=30)
    return r.status_code < 300


def main():
    raiz = Path(sys.argv[1]); ctl = raiz / "control"; ctl.mkdir(exist_ok=True)
    hoy = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).date()
    desde = hoy.replace(day=1).isoformat()
    pausados_f = ctl / "guardian_pausados.txt"
    pausados = [x for x in pausados_f.read_text().split() if x] if pausados_f.exists() else []
    acciones = []
    # 1° del mes: devolver lo que pausó el guardián
    if hoy.day == 1 and pausados:
        for a in pausados:
            if cambiar(a, "enable"): acciones.append(f"reactivado {a} (mes nuevo)")
        pausados = []
    total, por, n = minutos_del_mes(desde)
    pct = total / CUPO * 100
    dias_mes = (hoy.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    proyeccion = total / hoy.day * dias_mes.day if hoy.day else total
    nivel = "normal"
    if pct >= 85:
        nivel = "crítico (85%): solo lo esencial"
        objetivo = [a for a in NO_ESENCIALES]
    elif pct >= 70:
        nivel = "alto (70%): pausa de lo no esencial"
        objetivo = ["graficos.yml", "semanal.yml", "rutas.yml", "balances.yml"]
    else:
        objetivo = []
        if pct >= 50: nivel = "aviso (50%)"
    for a in objetivo:
        if estado(a) == "active" and cambiar(a, "disable"):
            pausados.append(a); acciones.append(f"pausado {a}")
    pausados_f.write_text("\n".join(sorted(set(pausados))) + ("\n" if pausados else ""))
    # registro
    csv = ctl / "minutos.csv"
    if not csv.exists(): csv.write_text("fecha,minutos_mes,cupo,pct,proyeccion_mes,nivel\n")
    with csv.open("a") as f: f.write(f"{hoy},{total},{CUPO},{pct:.1f},{proyeccion:.0f},{nivel}\n")
    md = [f"# Minutos de GitHub Actions de ppi--datos\n\nAl {hoy:%d/%m/%Y}: **{total} de {CUPO} minutos ({pct:.0f}%)**, en {n} corridas desde el 1°. "
          f"Proyección a fin de mes al ritmo actual: {proyeccion:.0f}. Nivel: **{nivel}**.\n",
          "Umbrales (Domingo, 24/11/2026): 50% aviso; 70% pausa gráficos, semanal, rutas y balances; 85% queda solo procesar y batería. "
          "El 1° de cada mes se reactiva lo que pausó el guardián. Los trabajos que leen fuentes públicas corren en ppi-lector y no cuentan.\n",
          "| Workflow | Minutos del mes |\n|---|---|"] + [f"| {a} | {m} |" for a, m in sorted(por.items(), key=lambda x: -x[1])]
    if acciones: md += ["", "**Acciones de hoy:** " + "; ".join(acciones)]
    if pausados: md += ["", "**Pausados por el guardián:** " + ", ".join(sorted(set(pausados)))]
    (ctl / "MINUTOS.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"guardian: {total}/{CUPO} min ({pct:.0f}%), proyección {proyeccion:.0f}, {nivel}; {'; '.join(acciones) or 'sin acciones'}", flush=True)
    # para el aviso: nivel en la salida del paso
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f: f.write(f"pct={pct:.0f}\nnivel={nivel}\n")


if __name__ == "__main__":
    main()
# FIN minutos.py
