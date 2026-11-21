#!/usr/bin/env python3
"""Panel de fotos para los invitados: galería web servida por la Pi (Wi-Fi de la fiesta, sin internet).
Cada foto se puede ver, guardar, compartir (WhatsApp…) e imprimir en la SELPHY.

  GET  /                 página del panel (index.html junto a este script)
  GET  /api/fotos        lista de fotos, la más nueva primero
  GET  /mini/<foto>      miniatura (se genera y se guarda en caché)
  GET  /foto/<foto>      foto completa (?descargar=1 para forzar descarga)
  POST /api/imprimir     {"foto": "<nombre>"} -> la manda a la cola de impresión
  GET  /pase             pase de fotos a pantalla completa para una tele/tablet/portátil (pase.html)
  GET  /api/pase         fotos y boomerangs (mp4), el más nuevo primero
  GET  /video/<video>    boomerang mp4 (admite Range, que piden los navegadores de las teles)

Se ejecuta con el Python de photobooth-app (trae Pillow) como usuario admin, en el puerto 80."""
import fnmatch, json, os, re, subprocess, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PUERTO = int(os.environ.get("PANEL_PUERTO", "80"))
BASE = os.path.dirname(os.path.abspath(__file__))
FOTOS = os.environ.get("PANEL_FOTOS", "/home/admin/photobooth-data/media/processed_full")
CACHE = os.environ.get("PANEL_CACHE", "/home/admin/photobooth-data/panel-cache")
EXCLUIR = "/home/admin/.config/rclone/excluir_pruebas.txt"   # las fotos de prueba no salen en el panel
# los *_hidden.jpg son las 4 fotos sueltas con las que photobooth-app monta la tira: tampoco salen
IMPR_CFG = os.environ.get("PANEL_IMPR_CFG", "/home/admin/.config/photomaton-impresion")
IMPRIMIR = os.environ.get("PANEL_IMPRIMIR", "/home/admin/bin/imprimir-foto.sh")
ESPERA_POR_MOVIL = 20          # s mínimos entre impresiones desde el mismo móvil
NOMBRE_OK = re.compile(r"^[\w.-]+\.jpg$")
VIDEO_OK = re.compile(r"^[\w.-]+\.mp4$")

os.makedirs(CACHE, exist_ok=True)
ultima_impresion = {}
cerrojo = threading.Lock()


def patrones_excluidos():
    try:
        return [l.strip().lstrip("/") for l in open(EXCLUIR) if l.strip() and not l.startswith("#")]
    except OSError:
        return []


def lista_fotos(videos=False):
    excl = patrones_excluidos()
    fotos = []
    for n in os.listdir(FOTOS):
        if (NOMBRE_OK.match(n) or (videos and VIDEO_OK.match(n))) and "_hidden" not in n and not any(fnmatch.fnmatch(n, p) for p in excl):
            fotos.append((os.path.getmtime(os.path.join(FOTOS, n)), n))
    return [n for _, n in sorted(fotos, reverse=True)]


def ruta_foto(nombre):
    if not NOMBRE_OK.match(nombre or ""):
        return None
    r = os.path.join(FOTOS, nombre)
    return r if os.path.isfile(r) else None


def miniatura(ruta):
    destino = os.path.join(CACHE, os.path.basename(ruta))
    if not os.path.exists(destino) or os.path.getmtime(destino) < os.path.getmtime(ruta):
        try:
            from PIL import Image
            with Image.open(ruta) as im:
                im.thumbnail((480, 480))
                im.convert("RGB").save(destino + ".tmp", "JPEG", quality=78)
            os.replace(destino + ".tmp", destino)
        except Exception:
            return ruta                     # sin Pillow: se sirve la original
    return destino


def invitados_pueden_imprimir():
    return not os.path.exists(os.path.join(IMPR_CFG, "invitados_no"))


class Panel(BaseHTTPRequestHandler):
    server_version = "PanelPhotomaton"

    def log_message(self, fmt, *args):
        pass

    def enviar(self, codigo, cuerpo, tipo="application/json; charset=utf-8", extra=None):
        if isinstance(cuerpo, (dict, list)):
            cuerpo = json.dumps(cuerpo, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(cuerpo)

    def fichero(self, ruta, tipo, extra=None):
        with open(ruta, "rb") as f:
            self.enviar(200, f.read(), tipo, extra)

    def video(self, ruta):
        tam = os.path.getsize(ruta)
        ini, fin = 0, tam - 1
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                ini = int(m.group(1)); fin = int(m.group(2)) if m.group(2) else fin
            else:
                ini = max(0, tam - int(m.group(2)))
            fin = min(fin, tam - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {ini}-{fin}/{tam}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(fin - ini + 1))
        self.send_header("Cache-Control", "max-age=86400")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(ruta, "rb") as f:
            f.seek(ini)
            falta = fin - ini + 1
            while falta > 0:
                trozo = f.read(min(65536, falta))
                if not trozo:
                    break
                self.wfile.write(trozo)
                falta -= len(trozo)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urlparse(self.path)
        p = url.path
        if p in ("/", "/index.html"):
            return self.fichero(os.path.join(BASE, "index.html"), "text/html; charset=utf-8", {"Cache-Control": "no-cache"})
        if p == "/pase":
            return self.fichero(os.path.join(BASE, "pase.html"), "text/html; charset=utf-8", {"Cache-Control": "no-cache"})
        if p == "/api/pase":
            return self.enviar(200, {"items": lista_fotos(videos=True)}, extra={"Cache-Control": "no-store"})
        if p.startswith("/video/"):
            n = p[len("/video/"):]
            r = os.path.join(FOTOS, n)
            if not VIDEO_OK.match(n) or not os.path.isfile(r):
                return self.enviar(404, {"error": "no existe"})
            return self.video(r)
        if p == "/api/fotos":
            return self.enviar(200, {"fotos": lista_fotos(), "imprimir": invitados_pueden_imprimir()}, extra={"Cache-Control": "no-store"})
        for pref in ("/mini/", "/foto/"):
            if p.startswith(pref):
                ruta = ruta_foto(p[len(pref):])
                if not ruta:
                    return self.enviar(404, {"error": "no existe"})
                extra = {"Cache-Control": "max-age=86400"}
                if pref == "/foto/" and "descargar" in parse_qs(url.query):
                    extra["Content-Disposition"] = f'attachment; filename="photomaton-mailen-{os.path.basename(ruta)}"'
                return self.fichero(miniatura(ruta) if pref == "/mini/" else ruta, "image/jpeg", extra)
        # Cualquier otra dirección (p. ej. comprobaciones de los móviles) lleva al panel
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        if urlparse(self.path).path != "/api/imprimir":
            return self.enviar(404, {"error": "no existe"})
        try:
            datos = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 2048)) or b"{}")
        except Exception:
            datos = {}
        ruta = ruta_foto(datos.get("foto"))
        if not ruta:
            return self.enviar(400, {"ok": False, "msg": "Esa foto no existe"})
        if not invitados_pueden_imprimir():
            return self.enviar(403, {"ok": False, "msg": "La impresión desde el panel está desactivada"})
        ip = self.client_address[0]
        with cerrojo:
            falta = ESPERA_POR_MOVIL - (time.time() - ultima_impresion.get(ip, 0))
            if falta > 0:
                return self.enviar(429, {"ok": False, "msg": f"Espera {int(falta) + 1} s antes de imprimir otra"})
            ultima_impresion[ip] = time.time()
        r = subprocess.run([IMPRIMIR, ruta], capture_output=True, text=True, timeout=30)
        salida = (r.stdout + r.stderr).strip().splitlines()
        msg = salida[-1] if salida else ""
        if r.returncode == 0:
            delante = re.search(r"(\d+) por delante", msg)
            espera = f" (hay {delante.group(1)} delante)" if delante else ""
            return self.enviar(200, {"ok": True, "msg": f"¡Enviada a la impresora!{espera} Sale en 1-2 min por foto"})
        ultima_impresion.pop(ip, None)
        return self.enviar(500, {"ok": False, "msg": msg.replace("ERROR ", "") or "No se pudo imprimir"})


if __name__ == "__main__":
    ThreadingHTTPServer.daemon_threads = True
    print(f"Panel de fotos en el puerto {PUERTO}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PUERTO), Panel).serve_forever()
