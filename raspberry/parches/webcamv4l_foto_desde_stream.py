#!/usr/bin/env python3
"""Parche para photobooth-app 9.x (backend WebcamV4l): la foto se toma del fotograma actual del stream.

Problema: en cada foto la app corta el stream de la webcam y lo vuelve a abrir. La Logitech C920, tras
reabrir tan rápido, entrega imágenes bastante más oscuras durante varios segundos, así que la foto sale
oscura aunque la previsualización se vea bien.

Solución: si `switch_to_high_resolution_for_stills` es false, se guarda como foto el fotograma que se está
mostrando en la previsualización, sin cortar el stream.

Uso (en la Pi):  python3 webcamv4l_foto_desde_stream.py
Se guarda una copia del original como webcamv4l.py.orig. Hay que volver a aplicarlo si se actualiza photobooth-app.
"""
import glob, os, shutil, sys

rutas = glob.glob(os.path.expanduser(
    "~/.local/share/pipx/venvs/photobooth-app/lib/python3*/site-packages/photobooth/services/backends/webcamv4l.py"))
if not rutas:
    sys.exit("No encuentro webcamv4l.py de photobooth-app (¿instalado con pipx?)")
p = rutas[0]
s = open(p).read()
if "PARCHE photomaton" in s:
    sys.exit("Ya estaba parcheado")
if not os.path.exists(p + ".orig"):
    shutil.copy2(p, p + ".orig")

old = """                    # check for pending mode change? if so break out the stream and switch
                    if self._mode_machine.is_mode_change_pending:
                        break
"""
new = """                    # PARCHE photomaton: sin cambio de resolución, la foto es el fotograma actual del stream.
                    # Reiniciar el stream (comportamiento original) deja la C920 oscura varios segundos.
                    if not self._config.switch_to_high_resolution_for_stills:
                        with self._hires_lock:
                            req = self._hires_queue.popleft() if self._hires_queue and isinstance(self._hires_queue[0], StillRequest) else None
                        if req:
                            with NamedTemporaryFile(
                                mode="wb", delete=False, dir="tmp", prefix=f"{filename_str_time()}_v4l2_", suffix=".jpg"
                            ) as f:
                                f.write(jpeg_buffer)
                            logger.info(f"still desde el stream (sin reiniciar) -> {Path(f.name)}")
                            self._mode_machine.request_video()
                            with req.condition:
                                req.result_file = Path(f.name)
                                req.condition.notify_all()
                            continue

                    # check for pending mode change? if so break out the stream and switch
                    # (PARCHE: si se pide "still" sin cambio de resolución, no se corta: se sirve arriba desde el stream)
                    if self._mode_machine.is_mode_change_pending and not (
                        not self._config.switch_to_high_resolution_for_stills and self._mode_machine.requested_mode == "still"
                    ):
                        break
"""
if s.count(old) != 1:
    sys.exit("No encuentro el bloque esperado: esta versión de photobooth-app es distinta, revisa el parche a mano")
open(p, "w").write(s.replace(old, new))
print("Parcheado:", p)
print("Reinicia la app: systemctl --user restart photobooth-app")
