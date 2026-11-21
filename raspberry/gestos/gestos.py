#!/usr/bin/env python3
"""Foto con la palma de la mano: mira la previsualización de photobooth-app y, si alguien enseña
la palma abierta a la cámara durante ~1 s, dispara (en el modo elegido: foto, tira o boomerang).

- Imagen: el stream MJPEG de photobooth-app (no abre la cámara, que ya usa la app).
- Reconocimiento: MediaPipe Gesture Recognizer (gesto "Open_Palm"), modelo local
  ~/gestos/gesture_recognizer.task: funciona sin internet.
- Dispara con marcos-servicio (POST 127.0.0.1:8010/disparar), igual que los mandos.
- Se desactiva creando ~/.config/photomaton-gestos-off (órdenes BLE gestos_on / gestos_off).
- Estado para la pantalla (extensión del quiosco): GET 127.0.0.1:8011/estado
  -> {"activo": bool, "progreso": 0..1, "disparo": timestamp del último disparo}

Se ejecuta con su propio venv (~/gestos/venv, pip install mediapipe)."""
import json, os, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mpt
from mediapipe.tasks.python import vision

STREAM = "http://127.0.0.1:8000/api/aquisition/stream.mjpg"
MARCOS = "http://127.0.0.1:8010"
MODELO = os.path.expanduser("~/gestos/gesture_recognizer.task")
APAGADO = os.path.expanduser("~/.config/photomaton-gestos-off")
REPOSO = os.path.expanduser("~/.config/photomaton-reposo")
LOG = os.path.expanduser("~/photobooth-data/log/gestos.log")
PUERTO = 8011

CADA = 0.33           # s entre análisis (~3 por segundo: la Pi va justa de temperatura)
ANCHO = 384           # se analiza la imagen reducida a 384x216
SCORE = 0.6           # confianza mínima del gesto "Open_Palm"
TAM_MIN = 0.07        # la mano debe ocupar al menos un 7 % del ancho: alguien delante, no al fondo
NECESARIOS = 3        # análisis con palma para disparar (~1 s)
ESPERA = {"foto": 10, "tira": 26, "boomerang": 18}   # s sin volver a disparar tras una foto

estado = {"activo": True, "progreso": 0.0, "disparo": 0}


def log(msg):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def activo():
    return not os.path.exists(APAGADO)


def mirar():
    """Solo se lee la cámara si está activado y el photomatón no está en reposo."""
    return activo() and not os.path.exists(REPOSO)


def marcos(ruta, metodo="GET"):
    req = urllib.request.Request(MARCOS + ruta, method=metodo)
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)


def disparar():
    try:
        modo = marcos("/estado").get("modo", "foto")
    except Exception:
        modo = "foto"
    try:
        marcos("/disparar", "POST")
        log(f"palma -> disparo ({modo})")
    except Exception as e:
        log(f"palma, pero no se pudo disparar: {e}")
    return ESPERA.get(modo, 10)


def palma(res):
    for i, gestos in enumerate(res.gestures):
        if not gestos or gestos[0].category_name != "Open_Palm" or gestos[0].score < SCORE:
            continue
        xs = [p.x for p in res.hand_landmarks[i]]
        if max(xs) - min(xs) >= TAM_MIN:
            return True
    return False


def fotogramas():
    """Devuelve una imagen JPEG cada CADA s del stream multipart (--frame); las demás se descartan
    sin copiarlas (el stream va a ~7 MB/s). Se reconecta si se corta (p. ej. al reiniciarse la app)."""
    SEP = b"--frame"
    while True:
        while not mirar():
            estado["activo"] = activo(); estado["progreso"] = 0.0
            time.sleep(1)
        try:
            with urllib.request.urlopen(STREAM, timeout=10) as r:
                buf, desde, ultimo = bytearray(), 0, 0.0
                while True:
                    trozo = r.read1(262144)
                    if not trozo or not mirar():
                        break
                    buf += trozo
                    while True:
                        a = buf.find(SEP)
                        if a < 0:
                            del buf[:max(0, len(buf) - len(SEP))]; desde = 0
                            break
                        b = buf.find(SEP, max(a + len(SEP), desde))
                        if b < 0:
                            desde = max(a + len(SEP), len(buf) - len(SEP))
                            if a:
                                del buf[:a]; desde -= a
                            break
                        ahora = time.time()
                        if ahora - ultimo >= CADA:
                            cab = buf.find(b"\r\n\r\n", a, b)
                            if cab > 0:
                                ultimo = ahora
                                yield bytes(buf[cab + 4:b])
                        del buf[:b]; desde = 0
        except Exception:
            pass
        time.sleep(3)


def vigilar():
    op = vision.GestureRecognizerOptions(
        base_options=mpt.BaseOptions(model_asset_path=MODELO),
        running_mode=vision.RunningMode.VIDEO, num_hands=2)
    rec = vision.GestureRecognizer.create_from_options(op)
    cuenta, bloqueo = 0, 0.0
    log("gestos arrancado")
    for jpg in fotogramas():
        ahora = time.time()
        estado["activo"] = activo()
        if not estado["activo"] or ahora < bloqueo:
            cuenta = 0; estado["progreso"] = 0.0
            continue
        img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_REDUCED_COLOR_2)   # ya a mitad de tamaño: más rápido
        if img is None:
            continue
        h, w = img.shape[:2]
        img = cv2.resize(img, (ANCHO, int(h * ANCHO / w)))
        res = rec.recognize_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)),
            int(ahora * 1000))
        cuenta = min(NECESARIOS, cuenta + 1) if palma(res) else max(0, cuenta - 1)
        estado["progreso"] = cuenta / NECESARIOS
        if cuenta >= NECESARIOS:
            estado["disparo"] = ahora; estado["progreso"] = 0.0; cuenta = 0
            bloqueo = ahora + disparar()


class Api(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def responder(self, datos):
        cuerpo = json.dumps(datos).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        self.responder(estado)

    def do_POST(self):
        if self.path == "/on" and os.path.exists(APAGADO):
            os.remove(APAGADO)
        elif self.path == "/off":
            open(APAGADO, "w").close()
        estado["activo"] = activo()
        self.responder(estado)


if __name__ == "__main__":
    ThreadingHTTPServer.daemon_threads = True
    srv = ThreadingHTTPServer(("127.0.0.1", PUERTO), Api)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    vigilar()
