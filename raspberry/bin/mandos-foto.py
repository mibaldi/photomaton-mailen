#!/usr/bin/env python3
"""Dispara una foto en photobooth-app con cualquier pulsación de los mandos BLE (AF15, SnapStand)."""
import os, re, select, struct, time, urllib.request

NOMBRES = ("AF15", "SnapStand")
TECLAS = {114, 115}          # KEY_VOLUMEDOWN, KEY_VOLUMEUP
ESPERA = 2.0                 # s entre fotos (el SnapStand manda dos teclas por pulsación)
URL = "http://localhost:8000/api/actions/image/0"
EV = struct.Struct("llHHi")

def buscar():
    txt = open("/proc/bus/input/devices").read()
    nodos = []
    for bloque in txt.split("\n\n"):
        if any(n in bloque for n in NOMBRES):
            m = re.search(r"Handlers=.*?(event\d+)", bloque)
            if m:
                nodos.append("/dev/input/" + m.group(1))
    return nodos

abiertos, ultima = {}, 0.0
while True:
    for n in buscar():
        if n not in abiertos:
            try:
                abiertos[n] = os.open(n, os.O_RDONLY | os.O_NONBLOCK)
                print("mando conectado", n, flush=True)
            except OSError:
                pass
    if not abiertos:
        time.sleep(2); continue
    r, _, _ = select.select(list(abiertos.values()), [], [], 2)
    for fd in r:
        try:
            datos = os.read(fd, EV.size * 64)
        except OSError:
            datos = b""
        if not datos:
            n = [k for k, v in abiertos.items() if v == fd][0]
            os.close(fd); del abiertos[n]; print("mando desconectado", n, flush=True)
            continue
        for i in range(0, len(datos) - EV.size + 1, EV.size):
            _, _, tipo, codigo, valor = EV.unpack_from(datos, i)
            if tipo == 1 and valor == 1 and codigo in TECLAS and time.time() - ultima > ESPERA:
                ultima = time.time()
                try:
                    urllib.request.urlopen(URL, timeout=5).read()
                    print("foto", flush=True)
                except Exception as e:
                    print("error disparando:", e, flush=True)
