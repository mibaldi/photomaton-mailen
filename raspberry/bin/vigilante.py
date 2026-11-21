#!/usr/bin/env python3
"""Vigilante del photomatón: si algo se cuelga, lo reinicia solo.

  - photobooth-app no responde, o la cámara deja de mandar imagen  -> reinicia photobooth-app
  - la página del quiosco no responde (pestaña colgada / "¡Oh, no!") -> mata Chromium
    (photobooth-kiosk.sh lo vuelve a abrir); si el propio quiosco no está, lo relanza
  - el quiosco se ha ido a otra web                                  -> vuelve a localhost:8000

Pide varios fallos seguidos antes de actuar (una foto, una tira o un boomerang pueden pausar
la imagen unos segundos) y no hace nada en los primeros minutos tras arrancar.
Necesita el paquete websockets: se ejecuta con el Python de photobooth-app.
Registro: ~/photobooth-data/log/vigilante.log"""
import asyncio, json, os, subprocess, time, urllib.request

APP = "http://127.0.0.1:8000"
STREAM = APP + "/api/aquisition/stream.mjpg"
CDP = "http://127.0.0.1:9222/json/list"
KIOSCO = "/home/admin/photobooth-kiosk.sh"
LOG = os.path.expanduser("~/photobooth-data/log/vigilante.log")
CADA = 10              # s entre comprobaciones
FALLOS_APP = 4         # ~40 s sin responder
FALLOS_CAMARA = 6      # ~60 s sin imagen
FALLOS_PAGINA = 4      # ~40 s con la página colgada
ARRANQUE = 120         # s de gracia tras arrancar la Pi o reiniciar algo
REPOSO = os.path.expanduser("~/.config/photomaton-reposo")   # reposo.py: pantalla negra y cámara parada


def log(msg):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def corre(*patron):
    # sin shell: así pgrep no se encuentra a sí mismo dentro de un "sh -c ..."
    return subprocess.run(["pgrep", *patron], capture_output=True).returncode == 0


def app_ok():
    try:
        return urllib.request.urlopen(APP + "/", timeout=5).status == 200
    except Exception:
        return False


def camara_ok():
    # lee un trozo del stream MJPEG y mira que traiga un JPEG (FF D8)
    try:
        with urllib.request.urlopen(STREAM, timeout=6) as r:
            datos = b""
            fin = time.time() + 6
            while len(datos) < 60000 and time.time() < fin:
                trozo = r.read(4096)
                if not trozo:
                    break
                datos += trozo
                if b"\xff\xd8" in datos and len(datos) > 8000:
                    return True
    except Exception:
        pass
    return False


async def evaluar(ws_url, expr):
    import websockets
    async with websockets.connect(ws_url, max_size=None, open_timeout=5) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                  "params": {"expression": expr, "returnByValue": True}}))
        while True:
            r = json.loads(await asyncio.wait_for(ws.recv(), 5))
            if r.get("id") == 1:
                return r.get("result", {}).get("result", {}).get("value")


async def navegar(ws_url, url):
    import websockets
    async with websockets.connect(ws_url, open_timeout=5) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": url}}))
        await asyncio.wait_for(ws.recv(), 5)


def pagina():
    """'ok', 'fuera' (otra web), 'colgada' o 'sin_chromium'"""
    if not corre("-x", "chromium"):
        return "sin_chromium", None
    try:
        objetivos = json.load(urllib.request.urlopen(CDP, timeout=5))
    except Exception:
        return "colgada", None
    pags = [t for t in objetivos if t.get("type") == "page"]
    if not pags:
        return "colgada", None
    p = pags[0]
    if not p.get("url", "").startswith(("http://localhost:8000", "http://127.0.0.1:8000")):
        return "fuera", p.get("webSocketDebuggerUrl")
    try:
        v = asyncio.run(asyncio.wait_for(evaluar(p["webSocketDebuggerUrl"], "document.readyState"), 8))
        return ("ok" if v else "colgada"), p.get("webSocketDebuggerUrl")
    except Exception:
        return "colgada", p.get("webSocketDebuggerUrl")


def cerrar_chromium():
    sh("pkill -x chromium")
    for _ in range(10):
        time.sleep(0.5)
        if not corre("-x", "chromium"):
            return
    log("Chromium no se cierra -> lo fuerzo")
    sh("pkill -KILL -x chromium")


def relanzar_kiosco():
    sh(f"systemd-run --user --unit=kiosco-{int(time.time())} --setenv=DISPLAY=:0 "
       f"--setenv=XAUTHORITY={os.path.expanduser('~/.Xauthority')} {KIOSCO}")


def main():
    log("vigilante arrancado")
    gracia = time.time() + ARRANQUE
    f_app = f_cam = f_pag = 0
    while True:
        time.sleep(CADA)
        if time.time() < gracia:
            continue
        if os.path.exists(REPOSO):
            f_app = f_cam = f_pag = 0
            gracia = time.time() + 30        # al despertar, la cámara tarda unos segundos
            continue

        # 1) photobooth-app y cámara
        if app_ok():
            f_app = 0
            f_cam = 0 if camara_ok() else f_cam + 1
        else:
            f_app += 1
        if f_app >= FALLOS_APP or f_cam >= FALLOS_CAMARA:
            log("photobooth-app no responde" if f_app >= FALLOS_APP else "la cámara no manda imagen")
            log("-> reinicio photobooth-app")
            sh("systemctl --user restart photobooth-app")
            f_app = f_cam = f_pag = 0
            gracia = time.time() + ARRANQUE
            continue
        if f_app:
            continue        # con la app caída no tiene sentido mirar la página

        # 2) pantalla (Chromium)
        estado, ws = pagina()
        if estado == "ok":
            f_pag = 0
        elif estado == "fuera":
            log("el quiosco estaba en otra web -> vuelvo a la del photomatón")
            try:
                asyncio.run(navegar(ws, "http://localhost:8000/"))
            except Exception:
                cerrar_chromium()
        elif estado == "sin_chromium" and not corre("-f", KIOSCO):
            log("no hay quiosco -> lo relanzo")
            relanzar_kiosco()
            gracia = time.time() + 60
        else:
            f_pag += 1
            if f_pag >= FALLOS_PAGINA:
                log(f"pantalla {estado} -> cierro Chromium para que se vuelva a abrir")
                cerrar_chromium()
                if not corre("-f", KIOSCO):
                    relanzar_kiosco()
                f_pag = 0
                gracia = time.time() + 60


if __name__ == "__main__":
    main()
