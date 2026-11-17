# Licitaciones, segundas vueltas, conversiones y canjes del Tesoro Nacional (Secretaría de Finanzas).
#
# Por qué: es el nodo central de la conducta monetaria. Cada operación del Tesoro con efecto sobre los pesos
# (licitación en efectivo, pago de vencimientos, canje, conversión con el BCRA) es un factor de expansión o de
# contracción. Las reglas de clasificación están en docs/FACTORES_TESORO.md.
#
# Cómo encuentra los comunicados: los de Finanzas no tienen un índice estable, pero cada uno es un nodo de
# argentina.gob.ar (argentina.gob.ar/node/N) y los números son correlativos para todo el sitio. Se recorre
# cada nodo nuevo leyendo solo el encabezado (título y descripción) y se guardan los de Finanzas.
# Las conversiones con el BCRA no tienen comunicado: salen por Resolución Conjunta SF/SH, que se buscan
# del mismo modo en argentina.gob.ar/normativa/nacional/norma-N.
#
# Qué guarda (política de datos: se archiva lo que puede desaparecer, se regenera lo que se puede recalcular):
#   fuentes/finanzas/comunicados/AAAA/<tipo><N>.html.gz   página original (se conserva: el sitio borra y mueve)
#   fuentes/finanzas/indice.csv                            un renglón por documento encontrado
#   fuentes/finanzas/cursor.json                           hasta dónde se recorrió cada numeración
#   fuentes/finanzas/tablas.csv.gz                         todas las tablas de todos los documentos, en largo (se regenera)
#   fuentes/finanzas/operaciones.csv                       una fila por documento con totales, rollover y clase (se regenera)
#   fuentes/finanzas/instrumentos.csv                      una fila por instrumento por operación (se regenera)
#
# Corre en ppi-lector (repositorio público, sin consumo de minutos de Actions) y escribe en ppi--datos/fuentes/finanzas,
# como tasas_bcra.py. Se ejecuta parado en la copia de ppi--datos (las rutas son relativas a ese repositorio).
# Uso:  cd ppi--datos && python ../ppi-lector/finanzas_tesoro.py [--hasta AAAA-MM-DD] [--minutos N]
#       python finanzas_tesoro.py --solo-procesar
import argparse, csv, gzip, io, json, re, sys, time, unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import requests

BASE = Path("fuentes/finanzas")
DOCS = BASE / "comunicados"
INDICE = BASE / "indice.csv"
CURSOR = BASE / "cursor.json"

# Criterio (Domingo, 17/11/2026): se arranca de lo más nuevo y se va hacia atrás, licitación por licitación, hasta que
# la cuenta cierre contra la oficial del BCRA. La historia larga (desde dic-2023, nodo 412687) queda para una segunda etapa.
# SEMILLA: números conocidos de junio de 2026 (resultado del 26/06 = nodo 505971; RC 33/2026 = norma 426756).
# Desde ahí se avanza hasta el último publicado (frente) y se retrocede hasta la fecha HASTA (atrás).
SEMILLA = {"nodo": 505000, "norma": 426000}
HASTA = "2025-11-01"   # un año hacia atrás desde la licitación de noviembre de 2026 (Domingo, 17/11/2026)
URL = {"nodo": "https://www.argentina.gob.ar/node/{}",
       "norma": "https://www.argentina.gob.ar/normativa/nacional/norma-{}"}
TEXTO_NORMA = "https://www.argentina.gob.ar/normativa/nacional/norma-{}/texto"
FRONTERA = 250        # números seguidos sin página = se llegó al último publicado
HILOS = 6
PRESUPUESTO_SEG = 50 * 60   # tiempo máximo de recorrido por corrida; la historia se completa en varias corridas

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (ppi--datos; seguimiento de licitaciones del Tesoro)"

CAMPOS_INDICE = ["origen", "numero", "fecha", "fecha_metodo", "tipo", "titulo", "url", "archivo", "encontrado"]


def normal(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().upper()


# ----------------------------------------------------------------------------------------------- recorrido
def encabezado(url, tope=160_000):
    """Baja la página hasta cerrar el <head> (o hasta `tope` bytes). Devuelve (status, html_parcial)."""
    try:
        r = S.get(url, timeout=30, stream=True, allow_redirects=True)
    except Exception as e:
        return -1, str(e)[:100]
    if r.status_code != 200:
        r.close(); return r.status_code, ""
    buf = b""
    for trozo in r.iter_content(16384):
        buf += trozo
        if b"</head>" in buf or len(buf) >= tope:
            break
    r.close()
    return 200, buf.decode("utf-8", "ignore")


def meta(html, *nombres):
    for n in nombres:
        m = re.search(r'<meta[^>]+(?:name|property)=["\']%s["\'][^>]*content=["\']([^"\']*)' % re.escape(n), html, re.I) \
            or re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:name|property)=["\']%s["\']' % re.escape(n), html, re.I)
        if m:
            return m.group(1)
    return ""


def titulo(html):
    t = meta(html, "og:title", "twitter:title")
    if not t:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        t = m.group(1) if m else ""
    t = re.sub(r"\s*\|\s*Argentina\.gob\.ar\s*$", "", re.sub(r"\s+", " ", t)).strip()
    import html as h
    return h.unescape(t)


PALABRAS_NODO = ["LICITACION", "CONVERSION", "CANJE", "SEGUNDA VUELTA", "LECAP", "BONCAP", "BONCER", "LELINK",
                 "LETAMAR", "BONTE", "BONAR", "LEDES", "LEFI", "DUAL", "DOLAR LINKED", "TITULOS ELEGIBLES",
                 "RECOMPRA", "TESORO NACIONAL"]


def es_finanzas_nodo(tit, desc):
    t, d = normal(tit), normal(desc)
    if not any(p in t for p in PALABRAS_NODO):
        return False
    # Descarta licitaciones de obra pública / compras: las de Finanzas hablan de instrumentos o de la Secretaría
    return ("SECRETARIA DE FINANZAS" in d or "MINISTERIO DE ECONOMIA INFORMA" in d or "TESORO NACIONAL" in d
            or any(p in t for p in PALABRAS_NODO[4:]) or "TITULOS" in t or "INSTRUMENTOS" in t
            or ("LICITACION" in t and ("RESULTADO" in t or "LLAMADO" in t) and "OBRA" not in t))


def es_finanzas_norma(tit, desc, cuerpo):
    c = normal(desc + " " + cuerpo)
    return ("SECRETARIA DE FINANZAS" in c and "DEUDA PUBLICA" in c) or \
           ("RESOLUCION CONJUNTA" in normal(tit) and "SECRETARIA DE FINANZAS" in c)


def tipo_doc(origen, tit):
    t = normal(tit)
    if origen == "norma":
        return "resolucion_conjunta"
    if "SEGUNDA VUELTA" in t:
        return "resultado_segunda_vuelta" if "RESULTADO" in t else "segunda_vuelta"
    if t.startswith("LLAMADO") or "LLAMADO A LICITACION" in t:
        return "llamado"
    if "PRECIO" in t and ("CONVERSION" in t or "CANJE" in t):
        return "precio_conversion"
    if "RESULTADO" in t:
        if ("CONVERSION" in t or "CANJE" in t) and "EFECTIVO" not in t:
            return "resultado_conversion"
        return "resultado"
    if "CONVERSION" in t or "CANJE" in t:
        return "conversion"
    if "RECOMPRA" in t:
        return "recompra"
    return "otro"


MESES = {m: i + 1 for i, m in enumerate(["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO",
                                          "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"])}
MESES["SETIEMBRE"] = 9


def fecha_de(html):
    for n in ("article:published_time", "dcterms.date", "dcterms.created", "date", "og:updated_time"):
        v = meta(html, n)
        m = re.match(r"(20\d\d)-(\d\d)-(\d\d)", v or "")
        if m:
            return m.group(0), "meta:" + n
    m = re.search(r'<time[^>]+datetime=["\'](20\d\d-\d\d-\d\d)', html)
    if m:
        return m.group(1), "time"
    txt = normal(re.sub(r"<[^>]+>", " ", html))
    # en los llamados la fecha de la licitación es la marcada (T)
    m = re.search(r"(\d{1,2}) DE ([A-Z]+) DE (20\d\d) \(T\)", txt)
    if m and m.group(2) in MESES:
        return f"{m.group(3)}-{MESES[m.group(2)]:02d}-{int(m.group(1)):02d}", "texto:(T)"
    m = re.search(r"(\d{1,2}) DE ([A-Z]+) DE (20\d\d)", txt)
    if m and m.group(2) in MESES:
        return f"{m.group(3)}-{MESES[m.group(2)]:02d}-{int(m.group(1)):02d}", "texto:primera"
    return "", ""


def leer_indice():
    if not INDICE.exists():
        return []
    with open(INDICE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def guardar_indice(filas):
    filas.sort(key=lambda r: (r["origen"], int(r["numero"])))
    with open(INDICE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, CAMPOS_INDICE); w.writeheader(); w.writerows(filas)


def bajar_completo(url):
    for intento in range(3):
        try:
            r = S.get(url, timeout=60)
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
        time.sleep(3 * (intento + 1))
    return None


def revisar(origen, n):
    """Mira el número n. Devuelve None si no existe, False si existe y no interesa, o el renglón del índice."""
    st, cab = encabezado(URL[origen].format(n))
    if st != 200:
        return None
    tit = titulo(cab); desc = meta(cab, "description", "og:description")
    if origen == "nodo":
        if not es_finanzas_nodo(tit, desc):
            return False
        url = URL[origen].format(n)
    else:
        if "RESOLUCION CONJUNTA" not in normal(tit) and "DEUDA PUBLICA" not in normal(cab):
            return False
        url = TEXTO_NORMA.format(n)
    html = bajar_completo(url)
    if html is None:
        print(f"  {origen} {n}: interesa pero no bajó el texto completo", flush=True)
        return False
    if origen == "norma" and not es_finanzas_norma(tit, desc, re.sub(r"<[^>]+>", " ", html)[:20000]):
        return False
    fecha, metodo = fecha_de(cab + html)
    anio = fecha[:4] or "sin_fecha"
    arch = DOCS / anio / f"{origen}{n}.html.gz"
    arch.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(arch, "wt", encoding="utf-8") as f:
        f.write(html)
    return {"origen": origen, "numero": str(n), "fecha": fecha, "fecha_metodo": metodo, "tipo": tipo_doc(origen, tit),
            "titulo": tit, "url": URL[origen].format(n), "archivo": str(arch), "encontrado": date.today().isoformat()}


def recorrer(origen, sentido, cursor, indice, fin_tiempo, hasta):
    """sentido "frente": desde la semilla hacia lo más nuevo, hasta la frontera.
       sentido "atras": desde la semilla hacia atrás, hasta encontrar un documento de Finanzas anterior a `hasta`."""
    vistos = {(r["origen"], r["numero"]) for r in indice}
    clave = f"{origen}_{sentido}"
    if sentido == "atras" and cursor.get(clave + "_listo") and cursor.get(clave + "_hasta", "9") <= hasta:
        print(f"{clave}: listo hasta {cursor.get(clave + '_hasta')}", flush=True); return
    n = cursor.get(clave, SEMILLA[origen] if sentido == "frente" else SEMILLA[origen] - 1)
    paso = 1 if sentido == "frente" else -1
    seguidos_sin = 0; ultimo_existente = n - paso; revisados = encontrados = 0; listo = False
    with ThreadPoolExecutor(HILOS) as ex:
        while time.time() < fin_tiempo and not listo:
            lote = [n + paso * i for i in range(HILOS * 4)]
            for k, res in zip(lote, ex.map(lambda k: revisar(origen, k), lote)):
                revisados += 1
                if res is None:
                    seguidos_sin += 1; continue
                seguidos_sin = 0; ultimo_existente = k
                if res and (origen, str(k)) not in vistos:
                    indice.append(res); vistos.add((origen, str(k))); encontrados += 1
                    print(f"  + {origen} {k} {res['fecha']} [{res['tipo']}] {res['titulo'][:90]}", flush=True)
                if res and sentido == "atras" and res["fecha"] and res["fecha"] < hasta:
                    listo = True
            n = lote[-1] + paso
            if sentido == "frente" and seguidos_sin >= FRONTERA:
                listo = True
    if sentido == "frente":
        cursor[clave] = ultimo_existente + 1 if listo else n
        cursor[clave + "_listo"] = listo     # al día; la próxima corrida mira solo lo nuevo
    else:
        cursor[clave] = n
        cursor[clave + "_listo"] = listo
        if listo:
            cursor[clave + "_hasta"] = hasta
    print(f"{clave}: {revisados} revisados, {encontrados} nuevos, cursor {cursor[clave]}"
          f"{' (listo)' if listo else ' (sigue en la próxima corrida)'}", flush=True)


# ----------------------------------------------------------------------------------------------- lectura de tablas
def numero(txt):
    """'$ 1.624.039' -> 1624039.0 ; 'USD 988,33' -> 988.33 ; '2,10%' -> 2.10 ; vacío o texto -> None"""
    t = str(txt or "").strip()
    if not t or normal(t) in ("DESIERTO", "-", "NAN", "S/D"):
        return None
    t = re.sub(r"\(.*?\)", "", t)
    t = re.sub(r"[^\d,.\-]", "", t)
    if not re.search(r"\d", t):
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1 or re.search(r"\.\d{3}$", t):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


def moneda(txt):
    t = normal(txt)
    return "USD" if ("USD" in t or "U$S" in t or "DOLARES" in t and "VINCULAD" not in t) else "ARS"


def tablas_de(html):
    """Tablas como listas de filas de texto (sin convertir números: eso lo hace numero())."""
    from lxml import html as lh
    try:
        raiz = lh.fromstring(html)
    except Exception:
        return []
    out = []
    for t in raiz.iter("table"):
        filas = []
        for tr in t.iter("tr"):
            celdas = []
            for c in tr:
                if c.tag not in ("td", "th"):
                    continue
                txt = re.sub(r"\s+", " ", c.text_content()).strip()
                celdas += [txt] * max(1, int(c.get("colspan", "1") or 1))
            if any(celdas):
                filas.append(celdas)
        if filas:
            out.append(filas)
    return out


TICKER = re.compile(r"\(\s*([A-Z]{1,3}\d[A-Z0-9]{1,4})\s*(?:[-–—]\s*(?:NUEV[OA]|REAPERTURA|T[IÍ]TULO ELEGIBLE)[^)]*)?\)")
VTO = re.compile(r"VENCIMIENTO (?:EL )?(\d{1,2}) DE ([A-Z]+) (?:DE |DEL )?(20\d\d)")


def describir_instrumento(texto):
    t = normal(texto)
    m = TICKER.search(t)
    ticker = m.group(1) if m else ""
    if not ticker:   # "Opción 1: BONO DUAL TXMD8 (15/12/2028)"
        m = re.search(r"\b(?=[A-Z0-9]{4,6}\b)([A-Z]{1,4}\d[A-Z0-9]{0,3})\b", t)
        ticker = m.group(1) if m else ""
    m = VTO.search(t)
    vto = f"{m.group(3)}-{MESES.get(m.group(2), 0):02d}-{int(m.group(1)):02d}" if m and m.group(2) in MESES else ""
    if not vto:
        m = re.search(r"\b(\d{2})/(\d{2})/(20\d\d)\b", t)
        vto = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""
    if "DUAL" in t and "TAMAR" in t: clase = "dual_cer_tamar"
    elif "DUAL" in t: clase = "dual"
    elif "VINCULAD" in t and "DOLAR" in t: clase = "dolar_linked"
    elif "CER" in t: clase = "cer"
    elif "TAMAR" in t: clase = "tamar"
    elif "CAPITALIZABLE" in t: clase = "tasa_fija_capitalizable"
    elif "DESCUENTO" in t: clase = "tasa_fija_descuento"
    elif "DOLARES ESTADOUNIDENSES" in t: clase = "hard_dollar"
    elif "LIQUIDEZ" in t: clase = "lefi"
    else: clase = "otro"
    return ticker, vto, clase


ROLES = [  # (rol, palabras que tiene que tener el encabezado normalizado, palabras que no)
    ("vno_ofertado", ["VNO", "OFERTAD"], []),
    ("vno_adjudicado", ["VNO", "ADJUDICAD"], []),
    ("ve_ofertado", ["EFECTIVO", "OFERTAD"], []),
    ("ve_adjudicado", ["EFECTIVO", "ADJUDICAD"], []),
    ("ve_adjudicado", ["VE ", "ADJUDICAD"], []),
    ("ve_equivalente", ["EFECTIVO", "EQUIVALENTE"], []),
    ("precio_corte", ["PRECIO"], ["TASA"]),
    ("tem", ["TEM"], []),
    ("tirea", ["TIREA"], ["TAMAR"]),
    ("tirea_tamar", ["TIREA", "TAMAR"], []),
    ("tna", ["TNA"], []),
    ("margen", ["MARGEN"], []),
    ("vno_circulacion", ["CIRCULACION"], []),
    ("vno_rescatado", ["RESCAT"], []),
    ("vno_rescatado", ["A INTEGRAR"], []),
    ("prorrateo", ["PRORRATEO"], []),
]


def rol_de(encab):
    e = normal(encab) + " "
    for rol, si, no in ROLES:
        if all(p in e for p in si) and not any(p in e for p in no):
            return rol
    return ""


ES_INSTR = re.compile(r"\b(LETRA|LETRAS|BONO|BONOS|LECAP|BONCAP|BONCER|LELINK|BONTE|BONAR|LEDES|LECER|LETAMAR|OPCION)\b")


def leer_documento(fila):
    """Devuelve (tablas_en_largo, operacion, instrumentos) de un documento guardado."""
    with gzip.open(fila["archivo"], "rt", encoding="utf-8") as f:
        html = f.read()
    plano = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", html)))
    import html as h
    plano = h.unescape(plano)
    P = normal(plano)
    clave = f"{fila['origen']}{fila['numero']}"
    largo, instrumentos = [], []
    tot = {}
    for ti, tabla in enumerate(tablas_de(html)):
        cols, filas = tabla[0], tabla[1:]
        # si la primera fila no es encabezado (no nombra ninguna magnitud), la tabla es de etiqueta / valor
        if not any(rol_de(c) for c in cols) and not any(k in normal(" ".join(cols)) for k in ("RESULTADO", "TOTAL")):
            cols, filas = [""] * len(tabla[0]), tabla
        for fi, fl in enumerate(filas):
            for ci, v in enumerate(fl):
                largo.append([clave, ti, fi, ci, cols[ci] if ci < len(cols) else "", v])
        roles = [rol_de(c) for c in cols]
        # tabla de totales: etiqueta en la primera columna ("Total VE Ofertado (*)") y valores a la derecha
        for fl in filas:
            et = normal(fl[0]) if fl else ""
            if not et or ES_INSTR.search(et):
                continue
            for etiqueta, k in (("CANTIDAD DE OFERTAS", "ofertas"), ("TOTAL VNO OFERTADO", "vno_ofertado"),
                                ("TOTAL VE OFERTADO", "ve_ofertado"), ("TOTAL VALOR EFECTIVO OFERTADO", "ve_ofertado"),
                                ("TOTAL VNO ADJUDICADO", "vno_adjudicado"), ("TOTAL VALOR EFECTIVO ADJUDICADO", "ve_adjudicado"),
                                ("TOTAL VE ADJUDICADO", "ve_adjudicado")):
                if et.startswith(etiqueta):
                    for ci in range(1, len(fl)):
                        cab = normal(cols[ci]) if ci < len(cols) else ""
                        seg = "total" if cab.startswith("TOTAL") else \
                              "usd" if ("DOLARES" in cab or "USD" in cab) else "pesos"
                        val = numero(fl[ci])
                        if val is not None:
                            tot[f"{k}_{seg}"] = val
        # tabla de instrumentos
        if sum(1 for r in roles if r) >= 2:
            for fl in filas:
                desc = fl[0]
                if not ES_INSTR.search(normal(desc)):
                    continue
                ticker, vto, clase = describir_instrumento(desc)
                reg = {"doc": clave, "fecha": fila["fecha"], "tipo_doc": fila["tipo"], "tabla": ti, "ticker": ticker,
                       "clase": clase, "vencimiento": vto, "descripcion": re.sub(r"\s+", " ", desc)[:200],
                       "moneda": "", "tramo": ""}
                enc_tabla = normal(" ".join(cols))
                reg["tramo"] = "conversion" if ("CONVERSION" in enc_tabla or "A INTEGRAR" in enc_tabla or "RESCAT" in enc_tabla) else ""
                for ci, r in enumerate(roles):
                    if r and ci < len(fl) and r not in reg:
                        if r == "precio_corte" and "%" in fl[ci]:
                            reg["tem"] = numero(fl[ci]); continue   # columna "Precio / TEM de corte": en LECAP es tasa
                        reg[r] = numero(fl[ci])
                        if r in ("vno_adjudicado", "ve_adjudicado", "precio_corte") and not reg["moneda"]:
                            reg["moneda"] = moneda(fl[ci] + " " + cols[ci])
                instrumentos.append(reg)
    # textos sueltos
    op = {"doc": clave, "fecha": fila["fecha"], "tipo_doc": fila["tipo"], "titulo": fila["titulo"], "url": fila["url"]}
    op.update(tot)
    m = re.search(r"ROLL[- ]?OVER[^0-9%]{0,60}?(\d{1,3}(?:[.,]\d+)?)\s*%", P)
    if m: op["rollover_pct"] = numero(m.group(1))
    m = re.search(r"VENCIMIENTOS? (?:DE|POR) (?:ALREDEDOR DE |APROXIMADAMENTE )?\$\s*([\d.,]+)\s*(BILLONES|MILLONES)", P)
    if m:
        v = numero(m.group(1)); op["vencimientos_pesos_mill"] = v * (1e6 if m.group(2) == "BILLONES" else 1) if v else None
    m = re.search(r"PESOS\s*/\s*USD\s*([\d.,]+)", P)
    if m: op["tc_a3500"] = numero(m.group(1))
    m = re.search(r"(\d{1,3}(?:[.,]\d+)?)\s*% DEL (?:VNO|VALOR NOMINAL)", P)
    if m: op["adhesion_pct"] = numero(m.group(1))
    m = re.search(r"LIQUIDACION[^.]{0,120}?(\d{1,2}) DE ([A-Z]+) DE (20\d\d)", P)
    if m and m.group(2) in MESES: op["liquidacion"] = f"{m.group(3)}-{MESES[m.group(2)]:02d}-{int(m.group(1)):02d}"
    op["con_bcra"] = bool(re.search(r"BANCO CENTRAL[^.]{0,80}(CONVERSION|CANJE|RECOMPRA|CARTERA|TENENCIA)|"
                                     r"(CONVERSION|CANJE|RECOMPRA|CARTERA|TENENCIA)[^.]{0,120}(BANCO CENTRAL|BCRA)", P)) \
        and fila["tipo"] in ("resolucion_conjunta", "recompra")
    op["clase_monetaria"], op["sentido"] = clasificar(fila["tipo"], op, instrumentos)
    return largo, op, instrumentos


def clasificar(tipo, op, instrumentos):
    """Clase de factor monetario de la operación (docs/FACTORES_TESORO.md). Devuelve (clase, sentido)."""
    if tipo in ("llamado", "precio_conversion", "segunda_vuelta", "conversion", "otro"):
        return "anuncio", "sin_efecto"
    if tipo == "resolucion_conjunta":
        if op.get("con_bcra"):
            return "conversion_con_bcra", "sin_efecto_directo"
        return "norma_emision", "sin_efecto"
    if tipo == "recompra":
        return "recompra_al_bcra", "sin_efecto_directo"
    if tipo == "resultado_conversion":
        return "canje_con_privados", "sin_efecto_directo"
    if tipo == "resultado_segunda_vuelta":
        monedas = {i.get("moneda") for i in instrumentos}
        return ("colocacion_en_dolares", "sin_efecto_en_pesos") if monedas == {"USD"} else ("colocacion_en_pesos", "contractivo")
    # resultado de licitación por efectivo: el neto contra vencimientos decide el sentido
    r = op.get("rollover_pct")
    if r is None:
        return "licitacion_efectivo", "a_determinar"
    return "licitacion_efectivo", ("contractivo" if r > 100 else "expansivo" if r < 100 else "neutro")


CAMPOS_OP = ["doc", "fecha", "liquidacion", "tipo_doc", "clase_monetaria", "sentido", "rollover_pct", "vencimientos_pesos_mill",
             "ofertas_pesos", "ofertas_usd", "ofertas_total", "ve_ofertado_pesos", "ve_ofertado_usd", "ve_ofertado_total",
             "ve_adjudicado_pesos", "ve_adjudicado_usd", "ve_adjudicado_total", "vno_adjudicado_pesos", "vno_adjudicado_usd",
             "vno_adjudicado_total", "adhesion_pct", "tc_a3500", "con_bcra", "titulo", "url"]
CAMPOS_IN = ["doc", "fecha", "tipo_doc", "tramo", "tabla", "ticker", "clase", "vencimiento", "moneda", "vno_ofertado",
             "vno_adjudicado", "ve_ofertado", "ve_adjudicado", "ve_equivalente", "precio_corte", "tem", "tirea", "tirea_tamar",
             "tna", "margen", "vno_circulacion", "vno_rescatado", "prorrateo", "descripcion"]


def procesar(indice):
    largo, ops, ins = [], [], []
    for fila in sorted(indice, key=lambda r: (r["fecha"], r["origen"], int(r["numero"]))):
        if not Path(fila["archivo"]).exists():
            continue
        try:
            l, o, i = leer_documento(fila)
        except Exception as e:
            print(f"  no se pudo leer {fila['archivo']}: {e}", flush=True); continue
        largo += l; ops.append(o); ins += i
    with gzip.open(BASE / "tablas.csv.gz", "wt", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["doc", "tabla", "fila", "columna", "encabezado", "valor"]); w.writerows(largo)
    for nombre, campos, datos in (("operaciones.csv", CAMPOS_OP, ops), ("instrumentos.csv", CAMPOS_IN, ins)):
        with open(BASE / nombre, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, campos, extrasaction="ignore"); w.writeheader(); w.writerows(datos)
    print(f"procesado: {len(ops)} documentos, {len(ins)} filas de instrumentos, {len(largo)} celdas", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo-procesar", action="store_true")
    ap.add_argument("--minutos", type=float, default=PRESUPUESTO_SEG / 60)
    ap.add_argument("--hasta", default=HASTA, help="fecha (AAAA-MM-DD) hasta la que se retrocede")
    a = ap.parse_args()
    BASE.mkdir(parents=True, exist_ok=True)
    indice = leer_indice()
    if not a.solo_procesar:
        cursor = json.loads(CURSOR.read_text()) if CURSOR.exists() else {}
        for k in [k for k in cursor if k in ("nodo", "norma", "nodo_al_dia", "norma_al_dia")]:
            cursor.pop(k)   # cursores del primer esquema (de dic-2023 hacia adelante), abandonado
        t0 = time.time(); total = a.minutos * 60
        # lo nuevo primero; después se retrocede con el tiempo que quede (las normas, con un mínimo de 3 minutos)
        plan = [("nodo", "frente", 0.35), ("nodo", "atras", 0.80), ("norma", "frente", 0.90), ("norma", "atras", 1.0)]
        for origen, sentido, hasta_fraccion in plan:
            fin = max(t0 + total * hasta_fraccion, time.time() + 3 * 60 if origen == "norma" else 0)
            recorrer(origen, sentido, cursor, indice, fin, a.hasta)
            guardar_indice(indice); CURSOR.write_text(json.dumps(cursor, indent=1))
    procesar(indice)


if __name__ == "__main__":
    main()
