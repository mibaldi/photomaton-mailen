#!/usr/bin/env python3
"""Reposo del photomatón: si nadie lo usa en X minutos, pone la pantalla en negro y deja de mirar
la cámara (photobooth-app solo saca imagen si alguien la mira). Así casi no gasta CPU y se enfría
(de ~85 °C a ~76 °C). La Pi 5 no tiene suspensión real y la MHS35 no deja apagar la luz.

Se despierta (2-3 s) tocando la pantalla, con un mando, o desde la webapp (orden BLE "despertar"
o cualquier "foto": marcos-servicio despierta en vez de disparar).

  GET  /estado          {"reposo": bool, "minutos": N, "inactivo": s}
  GET  /pantalla        página negra que se ve en reposo (al tocarla, despierta)
  POST /actividad       algo se ha usado (pantalla, mandos, BLE, marcos…): reinicia la cuenta
  POST /dormir          a reposo ya
  POST /despertar       sale del reposo
  POST /minutos/N       minutos sin uso para entrar en reposo (0 = nunca)

Mientras está en reposo existe ~/.config/photomaton-reposo (el vigilante y gestos.py lo respetan).
Usa el puerto de depuración de Chromium (127.0.0.1:9222) para cambiar la página del quiosco:
se ejecuta con el Python de photobooth-app (trae websockets)."""
import asyncio, json, os, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PUERTO = 8012
APP = "http://localhost:8000/"
PANTALLA = f"http://127.0.0.1:{PUERTO}/pantalla"
CDP = "http://127.0.0.1:9222/json/list"
FLAG = os.path.expanduser("~/.config/photomaton-reposo")
CFG = os.path.expanduser("~/.config/photomaton-reposo-min")
MEDIA = os.path.expanduser("~/photobooth-data/media/processed_full")
LOG = os.path.expanduser("~/photobooth-data/log/reposo.log")
POR_DEFECTO = 10
ARRANQUE = 180        # s tras arrancar sin dormirse

ultima = time.time()
cerrojo = threading.Lock()

HTML = """<!doctype html><html lang="es" translate="no"><head><meta charset="utf-8"><meta name="google" content="notranslate"><title>Reposo</title>
<style>html,body{margin:0;height:100%;background:#000;cursor:none;overflow:hidden}
div{position:fixed;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;
color:#555;font:700 54px system-ui,sans-serif;text-align:center;gap:18px;user-select:none}
small{font-size:34px;color:#3a3a3a}</style></head>
<body><div>😴<span>Toca la pantalla<br>para hacerte una foto</span><small>📸 Photomatón</small></div>
<script>
let ya=false;
function despertar(){ if(ya) return; ya=true; document.querySelector("span").textContent="¡Despertando!";
  fetch("/despertar",{method:"POST"}).catch(()=>{}).finally(()=>setTimeout(()=>{ya=false},4000)); }
addEventListener("pointerdown",despertar); addEventListener("touchstart",despertar); addEventListener("keydown",despertar);
</script></body></html>"""


def log(msg):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def minutos():
    try:
        return max(0, int(open(CFG).read().strip()))
    except Exception:
        return POR_DEFECTO


def dormido():
    return os.path.exists(FLAG)


def ultima_foto():
    try:
        return max((e.stat().st_mtime for e in os.scandir(MEDIA)), default=0)
    except OSError:
        return 0


def inactivo():
    return time.time() - max(ultima, ultima_foto())


def pagina():
    """(url, websocket) de la pestaña del quiosco, o (None, None)."""
    try:
        for t in json.load(urllib.request.urlopen(CDP, timeout=3)):
            if t.get("type") == "page":
                return t.get("url", ""), t.get("webSocketDebuggerUrl")
    except Exception:
        pass
    return None, None


def navegar(url):
    import websockets
    _, ws_url = pagina()
    if not ws_url:
        return False

    async def ir():
        async with websockets.connect(ws_url, open_timeout=5) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": url}}))
            await asyncio.wait_for(ws.recv(), 5)
    try:
        asyncio.run(ir())
        return True
    except Exception:
        return False


def dormir(motivo):
    with cerrojo:
        if dormido():
            return
        open(FLAG, "w").close()
        navegar(PANTALLA)
        log(f"a reposo ({motivo})")


def despertar(motivo):
    global ultima
    with cerrojo:
        ultima = time.time()
        if not dormido():
            return
        os.remove(FLAG)
        navegar(APP)
        log(f"despierto ({motivo})")


def bucle():
    arranque = time.time()
    if dormido():
        os.remove(FLAG)             # tras reiniciar la Pi, siempre empieza despierto
    while True:
        time.sleep(5)
        if dormido():
            url, _ = pagina()
            if url is not None and not url.startswith(PANTALLA):
                navegar(PANTALLA)   # Chromium se ha reabierto con la app: vuelve a la pantalla negra
            continue
        m = minutos()
        if m and time.time() - arranque > ARRANQUE and inactivo() > m * 60:
            dormir(f"{m} min sin uso")


class Api(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def responder(self, datos, tipo="application/json", codigo=200):
        cuerpo = datos.encode() if isinstance(datos, str) else json.dumps(datos).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", tipo + "; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def estado(self):
        self.responder({"reposo": dormido(), "minutos": minutos(), "inactivo": int(inactivo())})

    def do_GET(self):
        if self.path == "/pantalla":
            return self.responder(HTML, "text/html")
        self.estado()

    def do_POST(self):
        global ultima
        p = self.path
        if p == "/actividad":
            ultima = time.time()
        elif p == "/dormir":
            threading.Thread(target=dormir, args=("a mano",)).start()
            time.sleep(0.3)
        elif p.startswith("/despertar"):
            despertar(p.split("?", 1)[1] if "?" in p else "pantalla")
        elif p.startswith("/minutos/") and p[9:].isdigit():
            with open(CFG, "w") as f:
                f.write(str(min(int(p[9:]), 240)))
            ultima = time.time()
        else:
            return self.responder({"error": "no existe"}, codigo=404)
        self.estado()


if __name__ == "__main__":
    ThreadingHTTPServer.daemon_threads = True
    threading.Thread(target=bucle, daemon=True).start()
    log("reposo arrancado")
    ThreadingHTTPServer(("127.0.0.1", PUERTO), Api).serve_forever()
