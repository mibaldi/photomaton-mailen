#!/usr/bin/env python3
"""Elección de marco y de modo del photomatón (solo en la Pi, 127.0.0.1:8010).
Cada marco es una acción "image" de photobooth-app (misma configuración, distinto img_frame): la acción N
lleva el marco N de marcos.json. Este servicio guarda cuál está elegido y dispara la foto con él.

  GET  /estado              {"actual": i, "modo": "foto", "modos": [...], "marcos": [{"clave","nombre","archivo"}]}
  POST /elegir/<i>  /siguiente  /anterior        marco (solo modo foto)
  POST /modo/<foto|tira|boomerang>  /modo_sig    modo
  POST /disparar            según el modo: foto con el marco elegido, tira de 4 o boomerang
                            (lo usan la pantalla, los mandos y el BLE)
  GET  /png/<archivo>       imagen del marco (para dibujarlo sobre la previsualización)"""
import json, os, re, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DIR = os.environ.get("MARCOS_DIR", "/home/admin/photobooth-data/userdata/marcos")
ESTADO = os.environ.get("MARCOS_ESTADO", "/home/admin/.config/photomaton-marco")
APP = os.environ.get("MARCOS_APP", "http://localhost:8000")
PUERTO = int(os.environ.get("MARCOS_PUERTO", "8010"))
MODOS = ["foto", "tira", "boomerang"]
ACCION = {"tira": "collage/0", "boomerang": "video/0"}
REPOSO = "http://127.0.0.1:8012"
REPOSO_FLAG = os.path.expanduser("~/.config/photomaton-reposo")


def avisar_reposo(ruta):
    try:
        urllib.request.urlopen(urllib.request.Request(REPOSO + ruta, method="POST"), timeout=2).read()
    except Exception:
        pass


def modo():
    try:
        m = open(ESTADO + "-modo").read().strip()
    except Exception:
        m = "foto"
    return m if m in MODOS else "foto"


def poner_modo(m):
    with open(ESTADO + "-modo.tmp", "w") as f:
        f.write(m)
    os.replace(ESTADO + "-modo.tmp", ESTADO + "-modo")


def marcos():
    try:
        return json.load(open(os.path.join(DIR, "marcos.json")))
    except Exception:
        return []


def actual():
    try:
        i = int(open(ESTADO).read().strip())
    except Exception:
        i = 0
    return i if 0 <= i < max(1, len(marcos())) else 0


def elegir(i):
    n = len(marcos()) or 1
    os.makedirs(os.path.dirname(ESTADO) or ".", exist_ok=True)
    with open(ESTADO + ".tmp", "w") as f:
        f.write(str(i % n))
    os.replace(ESTADO + ".tmp", ESTADO)


def copia_usb():
    """Aviso de la copia al pendrive (copia-usb.sh) mientras dura y 20 s después."""
    try:
        with open("/run/photomaton-copia.json") as f:
            c = json.load(f)
        import time
        if c.get("estado") == "copiando" or time.time() - c.get("ts", 0) < 20:
            return c
    except Exception:
        pass
    return None


def estado():
    return {"actual": actual(), "modo": modo(), "modos": MODOS, "marcos": marcos(), "copia": copia_usb()}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def resp(self, cod, cuerpo, tipo="application/json"):
        if isinstance(cuerpo, (dict, list)):
            cuerpo = json.dumps(cuerpo, ensure_ascii=False).encode()
        self.send_response(cod)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Access-Control-Allow-Origin", "*")     # la pantalla (localhost:8000) lo consulta
        self.send_header("Cache-Control", "no-store" if tipo == "application/json" else "max-age=3600")
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.end_headers()

    def do_GET(self):
        if self.path == "/estado":
            return self.resp(200, estado())
        m = re.fullmatch(r"/png/([\w-]+\.png)", self.path)
        if m and os.path.isfile(os.path.join(DIR, m.group(1))):
            return self.resp(200, open(os.path.join(DIR, m.group(1)), "rb").read(), "image/png")
        self.resp(404, {"error": "no existe"})

    def do_POST(self):
        p = self.path
        if p == "/disparar" and os.path.exists(REPOSO_FLAG):
            # en reposo, el primer disparo (mando, webapp, pantalla) solo despierta el photomatón
            avisar_reposo("/despertar?disparo")
            return self.resp(200, {"ok": True, "despertando": True, "modo": modo(), "marco": actual()})
        avisar_reposo("/actividad")
        m = re.fullmatch(r"/elegir/(\d+)", p)
        if m:
            elegir(int(m.group(1)))
        elif p == "/siguiente":
            elegir(actual() + 1)
        elif p == "/anterior":
            elegir(actual() - 1)
        elif re.fullmatch(r"/modo/(foto|tira|boomerang)", p):
            poner_modo(p.split("/")[2])
        elif p == "/modo_sig":
            poner_modo(MODOS[(MODOS.index(modo()) + 1) % len(MODOS)])
        elif p == "/disparar":
            i, m = actual(), modo()
            accion = ACCION.get(m, f"image/{i}")
            try:
                urllib.request.urlopen(f"{APP}/api/actions/{accion}", timeout=10).read()
            except Exception as e:
                return self.resp(502, {"ok": False, "msg": str(e)})
            return self.resp(200, {"ok": True, "modo": m, "marco": i})
        else:
            return self.resp(404, {"error": "no existe"})
        self.resp(200, estado())


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PUERTO), H).serve_forever()
