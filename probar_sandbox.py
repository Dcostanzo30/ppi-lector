# Prueba de las claves de sandbox de PPI. Solo entra al entorno de pruebas: no toca las claves de produccion
# ni abre conexion en tiempo real (la API key/secret se usa solo para entrar al sandbox). Nunca imprime el valor de una clave.
import os
import requests

print("probar_sandbox: arranca", flush=True)
AU = os.environ.get("SBX_AU", "")
CL = os.environ.get("SBX_CL", "")
PK = os.environ.get("PPI_API_KEY", "")
PS = os.environ.get("PPI_API_SECRET", "")
print(f"Secreto AuthorizedClient: {'cargado (' + str(len(AU)) + ' caracteres)' if AU else 'VACIO: el nombre del secreto no coincide'}")
print(f"Secreto ClientKey: {'cargado (' + str(len(CL)) + ' caracteres)' if CL else 'VACIO: el nombre del secreto no coincide'}")
print(f"API key de siempre: {'cargada' if PK and PS else 'VACIA: falta en el flujo'}")
BASE = "https://clientapisbx.portfoliopersonal.com/api/"
LOGIN = BASE + "1.0/Account/LoginApi"


def intento(nombre, headers):
    try:
        r = requests.post(LOGIN, headers=dict(headers, **{"Content-type": "application/json"}), timeout=30)
        cuerpo = r.text[:160].replace("\n", " ")
        ok = r.status_code == 200 and "accessToken" in r.text
        print(f"[{nombre}] respuesta {r.status_code} {'ENTRÓ' if ok else ''} {'' if ok else cuerpo}", flush=True)
        return r.json()["accessToken"] if ok else None
    except Exception as e:
        print(f"[{nombre}] error: {str(e)[:120]}", flush=True)
        return None


token, cab_ok = None, None
pruebas = [
    ("E: claves PPI como cliente + API key/secret de siempre",
     {"AuthorizedClient": AU, "ClientKey": CL, "ApiKey": PK, "ApiSecret": PS}),
    ("F: cliente de la libreria + API key/secret de siempre",
     {"AuthorizedClient": "API_CLI_PYTHON", "ClientKey": "ppPYTHONSb", "ApiKey": PK, "ApiSecret": PS}),
]
for nombre, h in pruebas:
    if AU and CL and PK and PS and token is None:
        token = intento(nombre, h)
        if token:
            cab_ok = {k: v for k, v in h.items() if k in ("AuthorizedClient", "ClientKey")}

if token:
    h = dict(cab_ok, Authorization="Bearer " + token)
    for desc, uri in (("cuentas", "1.0/Account/Accounts"),
                      ("precio GGAL", "1.0/MarketData/Current?ticker=GGAL&type=ACCIONES&settlement=A-24HS")):
        try:
            r = requests.get(BASE + uri, headers=h, timeout=30)
            txt = r.text
            if desc == "cuentas":
                try:
                    txt = f"{len(r.json())} cuenta(s)"
                except Exception:
                    txt = txt[:120]
            print(f"{desc}: {r.status_code} {txt[:200]}", flush=True)
        except Exception as e:
            print(f"{desc}: error {str(e)[:100]}")
    print("RESULTADO: las claves de sandbox FUNCIONAN.")
else:
    print("RESULTADO: no se pudo entrar al sandbox (ver respuestas arriba).")
print("probar_sandbox: FIN", flush=True)
# FIN probar_sandbox.py
