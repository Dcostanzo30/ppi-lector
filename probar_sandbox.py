# Prueba de las claves de sandbox de PPI. Solo entra al entorno de pruebas: no toca las claves de produccion
# ni abre conexion en tiempo real (la API key/secret se usa solo para entrar al sandbox). Nunca imprime el valor de una clave.
# Prueba la direccion que mando PPI por correo y la de la libreria, y limpia espacios invisibles de las claves.
import os
import requests

print("probar_sandbox: arranca", flush=True)
def clave(n):
    v = os.environ.get(n, "")
    if v != v.strip():
        print(f"OJO: {n} tenía espacios o saltos de línea al principio o al final (se limpian)")
    return v.strip()

AU, CL = clave("SBX_AU"), clave("SBX_CL")
PK, PS = clave("PPI_API_KEY"), clave("PPI_API_SECRET")
print(f"AuthorizedClient: {len(AU)} caracteres; ClientKey: {len(CL)} caracteres; API key de siempre: {'cargada' if PK and PS else 'VACIA'}")
BASES = ["https://clientapi_sandbox.portfoliopersonal.com/api/",     # la del correo de PPI
         "https://clientapi_sandbox.portfoliopersonal.com/",
         "https://clientapisbx.portfoliopersonal.com/api/"]          # la de la libreria


def intento(base, nombre, headers):
    try:
        r = requests.post(base + "1.0/Account/LoginApi", headers=dict(headers, **{"Content-type": "application/json"}), timeout=30)
        ok = r.status_code == 200 and "accessToken" in r.text
        print(f"  [{nombre}] {r.status_code} {'ENTRÓ' if ok else r.text[:140]}", flush=True)
        return r.json()["accessToken"] if ok else None
    except Exception as e:
        print(f"  [{nombre}] error: {str(e)[:140]}", flush=True)
        return None


token = base_ok = cab_ok = None
for base in BASES:
    if token:
        break
    print(f"Dirección {base}", flush=True)
    try:
        print("  responde:", requests.get(base, timeout=20).status_code)
    except Exception as e:
        print("  no responde:", str(e)[:120]); continue
    for nombre, h in (("E: claves del correo + API key de siempre", {"AuthorizedClient": AU, "ClientKey": CL, "ApiKey": PK, "ApiSecret": PS}),
                      ("F: cliente de la libreria + API key de siempre",
                       {"AuthorizedClient": "API_CLI_PYTHON", "ClientKey": "ppPYTHONSb", "ApiKey": PK, "ApiSecret": PS})):
        token = intento(base, nombre, h)
        if token:
            base_ok, cab_ok = base, {k: h[k] for k in ("AuthorizedClient", "ClientKey")}
            break

if token:
    h = dict(cab_ok, Authorization="Bearer " + token)
    for desc, uri in (("cuentas", "1.0/Account/Accounts"),
                      ("precio GGAL", "1.0/MarketData/Current?ticker=GGAL&type=ACCIONES&settlement=A-24HS")):
        try:
            r = requests.get(base_ok + uri, headers=h, timeout=30)
            txt = r.text
            if desc == "cuentas":
                try:
                    txt = f"{len(r.json())} cuenta(s)"
                except Exception:
                    txt = txt[:120]
            print(f"{desc}: {r.status_code} {txt[:200]}", flush=True)
        except Exception as e:
            print(f"{desc}: error {str(e)[:100]}")
    print(f"RESULTADO: las claves de sandbox FUNCIONAN con {base_ok}")
else:
    print("RESULTADO: no se pudo entrar al sandbox (ver respuestas arriba).")
print("probar_sandbox: FIN", flush=True)
# FIN probar_sandbox.py
