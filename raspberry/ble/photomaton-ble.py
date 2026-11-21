#!/usr/bin/env python3
"""Servidor BLE (GATT) del photomatón: recibe órdenes de texto desde la webapp (Web Bluetooth).
Órdenes: foto | estado | imprimir | auto_on | auto_off | invitados_on | invitados_off | gestos_on | gestos_off | dormir | despertar | reposo <min> | comprobar | fiesta | pin <n> | cambiar_pin <n> | wifi_fiesta_on | wifi_fiesta_off |
apagar | reiniciar | ping.
Marcos y modos: marco <n> | marco_sig | marco_ant | modo <foto|tira|boomerang> | filtro <n> | filtro_sig
  (los guarda marcos-servicio, 127.0.0.1:8010). Notifica {"cmd":"cuenta","seg":N} al empezar cada cuenta atrás.
Galería por BLE: lista | mini <foto> | ver <foto> | trozos <tipo> <foto> <n,n,…> | imprimir <foto>.
Cámara en directo: vista (devuelve la imagen actual de la cámara, 320 px, por el mismo sistema de trozos).
  La cabecera {"cmd":"datos",tipo,id,tam,trozo,n} va por RESP y los bytes por la característica DATA,
  en trozos de [2 bytes de número de trozo][datos]. La webapp junta los trozos y pide los que falten. Responde por notificación en la característica RESP.
Se ejecuta como servicio de sistema (root)."""
import fnmatch, glob, json, os, re, socket, subprocess, threading, time, urllib.request
import dbus, dbus.exceptions, dbus.mainloop.glib, dbus.service
from gi.repository import GLib

SVC_UUID = "a07498ca-ad5b-474e-940d-16f1fbe7e8cd"
CMD_UUID = "a07498ca-ad5b-474e-940d-16f1fbe7e8ce"
RESP_UUID = "a07498ca-ad5b-474e-940d-16f1fbe7e8cf"
DATA_UUID = "a07498ca-ad5b-474e-940d-16f1fbe7e8d0"
NOMBRE = "Photomaton"
FOTOS = "/home/admin/photobooth-data/media/processed_full"
APP = "http://localhost:8000"
MARCOS = "http://127.0.0.1:8010"

BLUEZ = "org.bluez"
GATT_MGR = "org.bluez.GattManager1"
ADV_MGR = "org.bluez.LEAdvertisingManager1"
PROPS = "org.freedesktop.DBus.Properties"
OM = "org.freedesktop.DBus.ObjectManager"


def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return "?"


def n_fotos():
    return len(glob.glob(os.path.join(FOTOS, "*.jpg"))) + len(glob.glob(os.path.join(FOTOS, "*.mp4")))


def estado():
    try:
        urllib.request.urlopen(APP + "/", timeout=3)
        app = True
    except Exception:
        app = False
    thr = sh("vcgencmd get_throttled")
    return {
        "app": app,
        "camara": bool(glob.glob("/dev/v4l/by-id/*C920*")),
        "fotos": n_fotos(),
        "temp": sh("vcgencmd measure_temp").replace("temp=", ""),
        "alim_ok": thr.endswith("=0x0"),
        "wifi": sh("nmcli -t -f active,ssid dev wifi | grep ^yes | cut -d: -f2") or None,
        "internet": sh("ping -c1 -W2 8.8.8.8 >/dev/null 2>&1 && echo si") == "si",
        "hotspot": wifi_fiesta(),
        "gestos": gestos_activo(),
        **reposo_api("/estado", "GET"),
        "copia": (estado_copia() or {}).get("msg"),
        **marco_y_modo(),
        **estado_impresora(),
    }


IMPR_CFG = "/home/admin/.config/photomaton-impresion"


def estado_impresora():
    lp = sh("lpstat -p SELPHY 2>/dev/null")
    def leer(n, d="0"):
        try:
            return open(os.path.join(IMPR_CFG, n)).read().strip() or d
        except OSError:
            return d
    return {
        "impresora": ("lista" if "idle" in lp or "inactiva" in lp else "imprimiendo" if "printing" in lp or "imprimiendo" in lp
                      else "pausada/error" if lp else "no configurada"),
        "auto_print": os.path.exists(os.path.join(IMPR_CFG, "auto")),
        "impresas": int(leer("contador")),
        "limite": int(leer("limite")),
        "invitados": not os.path.exists(os.path.join(IMPR_CFG, "invitados_no")),
    }


def wifi_fiesta():
    """True si la Pi está emitiendo su propia Wi-Fi (panel de fotos en http://10.42.0.1)."""
    return "wifi-fiesta" in sh("nmcli -t -f NAME con show --active").splitlines()


# ---------- Galería por BLE ----------
CACHE = "/home/admin/photobooth-data/ble-cache"
EXCLUIR = "/home/admin/.config/rclone/excluir_pruebas.txt"     # las fotos de prueba no salen
PY_FOTOS = "/home/admin/.local/share/pipx/venvs/photobooth-app/bin/python"   # trae Pillow
NOMBRE_OK = re.compile(r"^[\w.-]+\.(jpg|mp4)$")      # fotos/tiras (jpg) y boomerangs (mp4)
TAMANOS = {"mini": (320, 65), "foto": (1280, 80)}   # lado mayor, calidad JPEG
PAUSA_TROZO = 0.008                                 # s entre notificaciones (no saturar D-Bus/BlueZ)
REDUCIR = """import sys
from PIL import Image
src, dst, lado, q = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
im = Image.open(src); im.thumbnail((lado, lado)); im.convert("RGB").save(dst, "JPEG", quality=q, optimize=True)
"""


# ---------- Cámara en directo por BLE ----------
# Un proceso aparte (Python de photobooth-app, que trae Pillow) lee el MJPEG de la cámara y deja la imagen
# reducida en /dev/shm. Solo vive mientras la webapp pide imágenes (se para a los 6 s sin peticiones).
VISTA = "/dev/shm/photomaton-vista.jpg"
VISTA_VIVO = "/dev/shm/photomaton-vista.vivo"
LECTOR_VISTA = r"""import io, os, sys, time, urllib.request
from PIL import Image
url, out, vivo = sys.argv[1:4]
r = urllib.request.urlopen(url, timeout=10)
buf, ult = bytearray(), 0.0
while time.time() - os.path.getmtime(vivo) < 6:
    trozo = r.read(32768)
    if not trozo:
        break
    buf += trozo
    fin = buf.rfind(b"\xff\xd9")
    if fin < 0:
        if len(buf) > 4000000: del buf[:-200000]
        continue
    ini = buf.rfind(b"\xff\xd8", 0, fin)
    jpg = bytes(buf[ini:fin + 2]) if ini >= 0 else None
    del buf[:fin + 2]
    if not jpg or time.time() - ult < 0.2:
        continue
    ult = time.time()
    try:
        im = Image.open(io.BytesIO(jpg)); im.draft("RGB", (320, 180)); im = im.convert("RGB"); im.thumbnail((320, 320))
        im.save(out + ".tmp", "JPEG", quality=55); os.replace(out + ".tmp", out)
    except Exception:
        pass
"""
_lector = {"p": None, "enviada": 0.0, "n": 0}


def imagen_vista():
    """Bytes de una imagen de la cámara más nueva que la última enviada (o None si no llega en 4 s)."""
    with open(VISTA_VIVO, "a"):
        pass
    os.utime(VISTA_VIVO)
    p = _lector["p"]
    if p is None or p.poll() is not None:
        _lector["p"] = subprocess.Popen([PY_FOTOS, "-c", LECTOR_VISTA, APP + "/api/aquisition/stream.mjpg", VISTA, VISTA_VIVO],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    fin = time.time() + 4
    while time.time() < fin:
        try:
            t = os.path.getmtime(VISTA)
            if t > _lector["enviada"]:
                _lector["enviada"] = t
                return open(VISTA, "rb").read()
        except OSError:
            pass
        time.sleep(0.04)
    return None


def lista_fotos():
    try:
        excl = [l.strip().lstrip("/") for l in open(EXCLUIR) if l.strip() and not l.startswith("#")]
    except OSError:
        excl = []
    fotos = [(os.path.getmtime(f), os.path.basename(f)) for f in glob.glob(os.path.join(FOTOS, "*.jpg")) + glob.glob(os.path.join(FOTOS, "*.mp4"))]
    return [n for _, n in sorted(fotos, reverse=True) if NOMBRE_OK.match(n) and "_hidden" not in n and not any(fnmatch.fnmatch(n, p) for p in excl)]


def ruta_foto(nombre):
    r = os.path.join(FOTOS, nombre or "")
    return r if NOMBRE_OK.match(nombre or "") and os.path.isfile(r) else None


def foto_reducida(nombre, tipo):
    """Devuelve los bytes de la foto reducida (se guarda en caché)."""
    src = ruta_foto(nombre)
    if not src:
        return None
    os.makedirs(CACHE, exist_ok=True)
    if nombre.endswith(".mp4"):
        return video_reducido(src, nombre, tipo)
    dst = os.path.join(CACHE, f"{tipo}-{nombre}")
    if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
        lado, q = TAMANOS[tipo]
        r = subprocess.run([PY_FOTOS, "-c", REDUCIR, src, dst + ".tmp", str(lado), str(q)], capture_output=True, timeout=30)
        if r.returncode != 0:
            return open(src, "rb").read() if tipo == "foto" else None
        os.replace(dst + ".tmp", dst)
    return open(dst, "rb").read()


def video_reducido(src, nombre, tipo):
    """Boomerang: la miniatura es un fotograma; para verlo, el vídeo a 480 px (unos 200-300 KB por Bluetooth)."""
    if tipo == "mini":
        dst = os.path.join(CACHE, f"mini-{nombre[:-4]}.jpg")
        args = ["ffmpeg", "-y", "-loglevel", "error", "-ss", "0.3", "-i", src, "-frames:v", "1", "-vf", "scale=320:-2", dst + ".tmp.jpg"]
    else:
        dst = os.path.join(CACHE, f"foto-{nombre}")
        args = ["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vf", "scale=480:-2", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "30", "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", dst + ".tmp.mp4"]
    if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
        if subprocess.run(args, capture_output=True, timeout=90).returncode != 0:
            return None
        os.replace(args[-1], dst)
    return open(dst, "rb").read()


def marcos_api(ruta, metodo="POST"):
    req = urllib.request.Request(MARCOS + ruta, data=b"" if metodo == "POST" else None, method=metodo)
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def marco_y_modo():
    try:
        e = marcos_api("/estado", "GET")
        return {"marco": e["actual"], "modo": e["modo"], "filtro": e.get("filtro", 0)}
    except Exception:
        return {"marco": None, "modo": None, "filtro": None}


CONFIG_APP = os.path.expanduser("~admin/photobooth-data/config/config.json")
_ultima_cuenta = {"tipo": "", "t": 0.0}


def segundos_cuenta(tipo):
    """Duración de la cuenta atrás que va a empezar (la de photobooth-app para ese tipo de foto)."""
    try:
        acc = json.load(open(CONFIG_APP))["actions"]
        if tipo == "collage":
            jc = acc["collage"][0]["jobcontrol"]
            seguida = _ultima_cuenta["tipo"] == "collage" and time.time() - _ultima_cuenta["t"] < 15
            seg = jc.get("countdown_capture_second_following", 1) if seguida else jc.get("countdown_capture", 2)
        else:
            seg = acc["video" if tipo == "video" else "image"][0].get("jobcontrol", {}).get("countdown_capture", 2)
    except Exception:
        seg = 3 if tipo in ("collage", "video") else 2
    _ultima_cuenta.update(tipo=tipo, t=time.time())
    return float(seg)


PIN_FICHERO = "/etc/photomaton-pin"     # PIN de la webapp (4-8 cifras, root 600; si no existe, sin PIN)
REPOSO = "http://127.0.0.1:8012"
REPOSO_FLAG = "/home/admin/.config/photomaton-reposo"


def reposo_api(ruta, metodo="POST"):
    try:
        req = urllib.request.Request(REPOSO + ruta, data=b"" if metodo == "POST" else None, method=metodo)
        with urllib.request.urlopen(req, timeout=8) as r:
            e = json.load(r)
        return {"reposo": e.get("reposo"), "reposo_min": e.get("minutos")}
    except Exception:
        return {"reposo": None, "reposo_min": None}


GESTOS = "http://127.0.0.1:8011"
GESTOS_OFF = "/home/admin/.config/photomaton-gestos-off"


def gestos_activo():
    """None si el detector de la palma (gestos.py) no está instalado o no responde."""
    try:
        with urllib.request.urlopen(GESTOS + "/estado", timeout=2) as r:
            return bool(json.load(r).get("activo"))
    except Exception:
        return None


COPIA_ESTADO = "/run/photomaton-copia.json"   # lo escribe copia-usb.sh


def estado_copia():
    try:
        with open(COPIA_ESTADO) as f:
            return json.load(f)
    except Exception:
        return None


def http_ok(url, t=3):
    try:
        urllib.request.urlopen(url, timeout=t).read(1)
        return True
    except Exception:
        return False


def camara_da_imagen():
    try:
        with urllib.request.urlopen(APP + "/api/aquisition/stream.mjpg", timeout=6) as r:
            datos, fin = b"", time.time() + 6
            while time.time() < fin and len(datos) < 200000:
                datos += r.read(8192)
                if b"\xff\xd8" in datos and len(datos) > 20000:
                    return True
    except Exception:
        pass
    return False


def comprobaciones():
    """Lista de (nivel, texto) para la tarjeta "Modo fiesta": nivel ok | aviso | mal | info."""
    c = []
    app = http_ok(APP + "/")
    c.append(("ok" if app else "mal", "App del photomatón " + ("funcionando" if app else "NO responde")))
    usb = glob.glob("/dev/v4l/by-id/*C920*")
    if not usb:
        c.append(("mal", "Cámara C920 NO conectada"))
    elif os.path.exists(REPOSO_FLAG):
        c.append(("ok", "Cámara conectada (en reposo: se enciende al tocar la pantalla)"))
    elif app:
        img = camara_da_imagen()
        c.append(("ok" if img else "mal", "Cámara " + ("da imagen" if img else "conectada pero SIN imagen")))
    servicios = {"marcos": "http://127.0.0.1:8010/estado", "palma": GESTOS + "/estado",
                 "reposo": REPOSO + "/estado", "panel Wi-Fi": "http://127.0.0.1/api/fotos"}
    caidos = [n for n, u in servicios.items() if not http_ok(u)]
    c.append(("ok" if not caidos else "aviso", "Servicios funcionando" if not caidos else "No responden: " + ", ".join(caidos)))
    ei = estado_impresora()
    conectada = "04a9:" in sh("lsusb")            # Canon
    if not conectada:
        c.append(("mal", "Impresora NO conectada por USB (o apagada)"))
    else:
        c.append(("ok" if ei["impresora"] in ("lista", "imprimiendo") else "aviso", f"Impresora {ei['impresora']}"))
    c.append(("info", f"Impresas: {ei['impresas']}" + (f" de {ei['limite']}" if ei["limite"] else "")
              + " · impresión automática " + ("SÍ" if ei["auto_print"] else "no")))
    pareados = set(re.findall(r"Device (\S+)", sh("bluetoothctl devices Paired")))
    conectados = set(re.findall(r"Device (\S+)", sh("bluetoothctl devices Connected")))
    if pareados:
        n = len(pareados & conectados)
        c.append(("ok" if n == len(pareados) else "aviso", f"Mandos conectados: {n} de {len(pareados)}"
                  + ("" if n == len(pareados) else " (pulsa un botón del mando para despertarlo)")))
    try:
        t = float(sh("vcgencmd measure_temp").split("=")[1].split("'")[0])
        c.append(("ok" if t < 75 else "aviso" if t < 82 else "mal", f"Temperatura {t:.0f} °C"
                  + ("" if t < 75 else " (pon ventilación o el ventilador)")))
    except Exception:
        pass
    thr = sh("vcgencmd get_throttled").split("=")[-1]
    try:
        v = int(thr, 16)
        if v & 0x1:
            c.append(("mal", "Alimentación insuficiente AHORA (usa la fuente oficial de 27 W)"))
        elif v & 0x10000:
            c.append(("aviso", "Ha habido bajadas de alimentación desde que arrancó"))
        else:
            c.append(("ok", "Alimentación correcta"))
    except ValueError:
        pass
    st = os.statvfs("/home/admin")
    libre = st.f_bavail * st.f_frsize / 1e9
    c.append(("ok" if libre > 3 else "aviso" if libre > 1 else "mal", f"Espacio libre: {libre:.0f} GB"))
    c.append(("info", f"Fotos y boomerangs hechos: {n_fotos()}"))
    g = gestos_activo()
    r = reposo_api("/estado", "GET")
    c.append(("info", "Palma: " + ("activada" if g else "desactivada" if g is False else "no disponible")
              + " · reposo: " + (f"tras {r['reposo_min']} min" if r["reposo_min"] else "nunca" if r["reposo_min"] == 0 else "no disponible")))
    creada = "wifi-fiesta" in sh("nmcli -t -f NAME con show").splitlines()
    c.append(("ok" if wifi_fiesta() else "info" if creada else "aviso",
              "Wi-Fi de la fiesta " + ("encendida (pase en http://10.42.0.1/pase)" if wifi_fiesta() else "creada, apagada" if creada else "NO creada")))
    cp = estado_copia()
    if cp:
        c.append(("ok" if cp.get("estado") == "hecha" else "info", "Copia USB: " + cp.get("msg", "")))
    else:
        c.append(("info", "Copia USB: aún no se ha hecho ninguna (enchufa un pendrive al final)"))
    ahora = time.localtime()
    c.append(("ok" if ahora.tm_year >= 2026 else "mal", "Hora: " + time.strftime("%d/%m/%Y %H:%M", ahora)
              + ("" if ahora.tm_year >= 2026 else " (MAL: las fotos saldrán con fecha errónea)")))
    return c


def como_admin(*args):
    """Ejecuta como el usuario admin (el servicio BLE corre como root)."""
    try:
        r = subprocess.run(["runuser", "-u", "admin", "--", *args], capture_output=True, text=True, timeout=30)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return 1, str(e)


class Advertisement(dbus.service.Object):
    PATH = "/org/photomaton/adv0"

    def __init__(self, bus):
        super().__init__(bus, self.PATH)

    @dbus.service.method(PROPS, in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
        return {
            "Type": "peripheral",
            "LocalName": dbus.String(NOMBRE),
            "ServiceUUIDs": dbus.Array([SVC_UUID], signature="s"),
            "Includes": dbus.Array(["tx-power"], signature="s"),
        }

    @dbus.service.method("org.bluez.LEAdvertisement1")
    def Release(self):
        pass


class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = "/org/photomaton"
        self.services = []
        super().__init__(bus, self.path)

    @dbus.service.method(OM, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        out = {}
        for s in self.services:
            out[s.path] = s.props()
            for c in s.chars:
                out[c.path] = c.props()
        return out


class Service(dbus.service.Object):
    def __init__(self, bus, idx):
        self.path = f"/org/photomaton/service{idx}"
        self.chars = []
        super().__init__(bus, self.path)

    def props(self):
        return {"org.bluez.GattService1": {
            "UUID": SVC_UUID, "Primary": True,
            "Characteristics": dbus.Array([c.path for c in self.chars], signature="o")}}


class Characteristic(dbus.service.Object):
    def __init__(self, bus, idx, service, uuid, flags):
        self.path = f"{service.path}/char{idx}"
        self.service, self.uuid, self.flags = service, uuid, flags
        self.value = []
        self.notifying = False
        self.mtu = 0
        super().__init__(bus, self.path)

    def props(self):
        return {"org.bluez.GattCharacteristic1": {
            "Service": dbus.ObjectPath(self.service.path), "UUID": self.uuid,
            "Flags": dbus.Array(self.flags, signature="s")}}

    @dbus.service.method(PROPS, in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
        return self.props()["org.bluez.GattCharacteristic1"]

    @dbus.service.signal(PROPS, signature="sa{sv}as")
    def PropertiesChanged(self, iface, changed, invalidated):
        pass

    @dbus.service.method("org.bluez.GattCharacteristic1", in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        return dbus.Array(self.value, signature="y")

    @dbus.service.method("org.bluez.GattCharacteristic1", in_signature="aya{sv}")
    def WriteValue(self, value, options):
        if "mtu" in options:
            self.mtu = int(options["mtu"])
        self.on_write(bytes(value).decode("utf-8", "ignore").strip().lower(), str(options.get("device", "")))

    @dbus.service.method("org.bluez.GattCharacteristic1")
    def StartNotify(self):
        self.notifying = True

    @dbus.service.method("org.bluez.GattCharacteristic1")
    def StopNotify(self):
        self.notifying = False

    def on_write(self, txt, dispositivo=""):
        pass

    def notify(self, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()[:500]
        self.value = [dbus.Byte(b) for b in data]
        if self.notifying:
            self.PropertiesChanged("org.bluez.GattCharacteristic1",
                                   {"Value": dbus.Array(self.value, signature="y")}, [])

    def notify_raw(self, data):
        if self.notifying:
            self.PropertiesChanged("org.bluez.GattCharacteristic1",
                                   {"Value": dbus.ByteArray(data)}, [])


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    adapter = "/org/bluez/hci0"
    dbus.Interface(bus.get_object(BLUEZ, adapter), PROPS).Set("org.bluez.Adapter1", "Powered", dbus.Boolean(1))

    app = Application(bus)
    svc = Service(bus, 0)
    resp = Characteristic(bus, 1, svc, RESP_UUID, ["read", "notify"])
    cmd = Characteristic(bus, 0, svc, CMD_UUID, ["write", "write-without-response"])
    datos = Characteristic(bus, 2, svc, DATA_UUID, ["notify"])
    svc.chars = [cmd, resp, datos]
    envio = threading.Lock()
    ultimo = {}          # último envío, para reenviar trozos perdidos
    app.services = [svc]

    def responder(obj):
        GLib.idle_add(lambda: (resp.notify(obj), False)[1])

    def trozo_max():
        # La webapp en Android negocia MTU 517; BlueZ nos la pasa en cada escritura. 3 bytes de ATT + 2 de número.
        return max(18, min((cmd.mtu or 185) - 5, 509))

    def emitir(i, trozo, data):
        GLib.idle_add(lambda b=bytes([i >> 8, i & 255]) + data[i * trozo:(i + 1) * trozo]: (datos.notify_raw(b), False)[1])

    def enviar_datos(tipo, ident, data, solo=None):
        with envio:
            if solo is None:
                trozo = trozo_max()
                n = (len(data) + trozo - 1) // trozo
                ultimo.update(tipo=tipo, id=ident, data=data, trozo=trozo)
                responder({"ok": True, "cmd": "datos", "tipo": tipo, "id": ident, "tam": len(data), "trozo": trozo, "n": n,
                       "video": ident.endswith(".mp4") and tipo == "foto"})
                time.sleep(0.05)
                indices = range(n)
            else:
                trozo, indices = ultimo["trozo"], solo
            for i in indices:
                emitir(i, trozo, data)
                time.sleep(PAUSA_TROZO)

    def galeria(txt):
        partes = txt.split()
        orden = partes[0]
        if orden == "lista":
            enviar_datos("lista", "lista", json.dumps({"fotos": lista_fotos()}).encode())
        elif orden in ("mini", "ver") and len(partes) == 2:
            tipo = "mini" if orden == "mini" else "foto"
            data = foto_reducida(partes[1], tipo)
            if data is None:
                responder({"ok": False, "cmd": "datos", "tipo": tipo, "id": partes[1], "msg": "Esa foto no existe"})
            else:
                enviar_datos(tipo, partes[1], data)
        elif orden == "vista":
            if os.path.exists(REPOSO_FLAG):
                responder({"ok": False, "cmd": "datos", "tipo": "vista", "id": "vista", "reposo": True,
                           "msg": "😴 El photomatón está en reposo: despiértalo para ver la cámara"})
                return
            data = imagen_vista()
            if data is None:
                responder({"ok": False, "cmd": "datos", "tipo": "vista", "id": "vista", "msg": "La cámara no da imagen"})
            else:
                _lector["n"] += 1
                enviar_datos("vista", f"v{_lector['n']}", data)
        elif orden == "trozos" and len(partes) == 4:
            if ultimo.get("tipo") == partes[1] and ultimo.get("id") == partes[2]:
                n = (len(ultimo["data"]) + ultimo["trozo"] - 1) // ultimo["trozo"]
                faltan = [int(x) for x in partes[3].split(",") if x.isdigit() and int(x) < n]
                enviar_datos(partes[1], partes[2], ultimo["data"], solo=faltan)
        elif orden == "imprimir" and len(partes) == 2:
            ruta = ruta_foto(partes[1])
            if not ruta or not ruta.endswith(".jpg"):
                responder({"ok": False, "cmd": "imprimir", "msg": "⚠️ Solo se pueden imprimir fotos"})
                return
            rc, out = como_admin("/home/admin/bin/imprimir-foto.sh", ruta)
            responder({"ok": rc == 0, "cmd": "imprimir", "msg": ("🖨 " if rc == 0 else "⚠️ ") + (out.replace("OK ", "") or "sin respuesta"), **estado_impresora()})

    def ejecutar(txt):
        if txt.split(" ", 1)[0] in ("lista", "mini", "ver", "trozos", "vista") or txt.startswith("imprimir "):
            galeria(txt)
        elif txt == "foto":
            antes = n_fotos()
            if os.path.exists(REPOSO_FLAG):
                # desde el móvil sí se quiere la foto: despierta, deja que la cámara coja luz y dispara
                responder({"ok": True, "cmd": "reposo", "msg": "😴 Despertando el photomatón…", **reposo_api("/despertar?webapp")})
                threading.Event().wait(4)
            try:
                try:
                    marcos_api("/disparar")                     # con el marco elegido
                except Exception:
                    urllib.request.urlopen(APP + "/api/actions/image/0", timeout=10).read()
            except Exception as e:
                responder({"ok": False, "cmd": "foto", "msg": f"No se pudo disparar: {e}"})
                return
            responder({"ok": True, "cmd": "foto", "msg": "Foto en marcha…"})
            for _ in range(60):
                threading.Event().wait(1)
                if n_fotos() > antes:
                    responder({"ok": True, "cmd": "foto_hecha", "msg": "¡Foto hecha!", "fotos": n_fotos()})
                    return
            responder({"ok": False, "cmd": "foto", "msg": "La foto no ha aparecido en 60 s"})
        elif txt == "estado":
            responder({"ok": True, "cmd": "estado", **estado()})
        elif txt == "apagar":
            responder({"ok": True, "cmd": "apagar", "msg": "Apagando… espera 10 s cuando la pantalla quede en blanco y desenchufa"})
            threading.Timer(2, lambda: subprocess.Popen(["systemctl", "poweroff"])).start()
        elif txt == "reiniciar":
            responder({"ok": True, "cmd": "reiniciar", "msg": "Reiniciando… vuelve en 1-2 min"})
            threading.Timer(2, lambda: subprocess.Popen(["systemctl", "reboot"])).start()
        elif txt == "imprimir":
            rc, out = como_admin("/home/admin/bin/imprimir-foto.sh")
            responder({"ok": rc == 0, "cmd": "imprimir", "msg": ("🖨 " if rc == 0 else "⚠️ ") + (out.replace("OK ", "") or "sin respuesta"), **estado_impresora()})
        elif txt in ("auto_on", "auto_off"):
            como_admin("mkdir", "-p", IMPR_CFG)
            como_admin("touch" if txt == "auto_on" else "rm", "-f" if txt == "auto_off" else "--", os.path.join(IMPR_CFG, "auto"))
            responder({"ok": True, "cmd": "auto", "msg": "Impresión automática " + ("activada" if txt == "auto_on" else "desactivada"), **estado_impresora()})
        elif txt in ("invitados_on", "invitados_off"):
            como_admin("mkdir", "-p", IMPR_CFG)
            como_admin("rm" if txt == "invitados_on" else "touch", "-f" if txt == "invitados_on" else "--", os.path.join(IMPR_CFG, "invitados_no"))
            responder({"ok": True, "cmd": "invitados", "msg": "Los invitados " + ("pueden" if txt == "invitados_on" else "ya no pueden") + " imprimir desde el panel", **estado_impresora()})
        elif txt == "comprobar":
            lista = comprobaciones()
            for i, (nivel, texto) in enumerate(lista):
                responder({"cmd": "check", "i": i, "n": len(lista), "nivel": nivel, "txt": texto})
                threading.Event().wait(0.05)
            malos = sum(1 for n, _ in lista if n == "mal"); avisos = sum(1 for n, _ in lista if n == "aviso")
            responder({"ok": malos == 0, "cmd": "check_fin", "msg": "✅ Todo listo para la fiesta" if not malos and not avisos
                       else f"{'❌ ' + str(malos) + ' problema(s)' if malos else ''}{' · ' if malos and avisos else ''}{'⚠️ ' + str(avisos) + ' aviso(s)' if avisos else ''}"})
        elif txt == "fiesta":
            # deja todo como para la fiesta: despierto, palma activada, reposo a 2 min si estaba en "nunca",
            # y la Wi-Fi propia encendida (la Pi deja la Wi-Fi de casa)
            reposo_api("/despertar?fiesta")
            como_admin("rm", "-f", GESTOS_OFF)
            if reposo_api("/estado", "GET")["reposo_min"] == 0:
                reposo_api("/minutos/2")
            hecho = ["☀️ despierto", "✋ palma activada"]
            if "wifi-fiesta" in sh("nmcli -t -f NAME con show").splitlines():
                if not wifi_fiesta():
                    sh("nmcli con up wifi-fiesta")
                    threading.Event().wait(3)
                hecho.append("📶 Wi-Fi de la fiesta " + ("encendida" if wifi_fiesta() else "NO se pudo encender"))
            responder({"ok": True, "cmd": "fiesta", "msg": "🎉 Listo: " + ", ".join(hecho), "hotspot": wifi_fiesta(),
                       "gestos": gestos_activo(), **reposo_api("/estado", "GET")})
        elif txt in ("dormir", "despertar") or re.fullmatch(r"reposo \d+", txt):
            if txt == "dormir":
                e = reposo_api("/dormir"); msg = "😴 Photomatón en reposo: se despierta tocando la pantalla"
            elif txt == "despertar":
                e = reposo_api("/despertar?webapp"); msg = "☀️ Photomatón despierto"
            else:
                n = int(txt.split()[1]); e = reposo_api(f"/minutos/{n}")
                msg = f"😴 Reposo tras {n} min sin uso" if n else "😴 Reposo automático desactivado"
            responder({"ok": e["reposo"] is not None, "cmd": "reposo", **e,
                       "msg": msg if e["reposo"] is not None else "El servicio de reposo no responde"})
        elif txt in ("gestos_on", "gestos_off"):
            como_admin("rm" if txt == "gestos_on" else "touch", "-f" if txt == "gestos_on" else "--", GESTOS_OFF)
            on = gestos_activo()
            responder({"ok": on is not None, "cmd": "gestos", "gestos": on,
                       "msg": ("✋ Foto con la palma " + ("activada" if on else "desactivada")) if on is not None else "El detector de la palma no está funcionando"})
        elif txt in ("wifi_fiesta_on", "wifi_fiesta_off"):
            if "wifi-fiesta" not in sh("nmcli -t -f NAME con show").splitlines():
                responder({"ok": False, "cmd": "wifi", "msg": "La Wi-Fi de la fiesta no está creada (raspberry/red/crear-wifi-fiesta.sh)", "hotspot": False})
                return
            sh("nmcli con " + ("up" if txt == "wifi_fiesta_on" else "down") + " wifi-fiesta")
            threading.Event().wait(3)
            on = wifi_fiesta()
            responder({"ok": on == (txt == "wifi_fiesta_on"), "cmd": "wifi", "hotspot": on,
                       "msg": "📶 Wi-Fi de la fiesta encendida: panel en http://10.42.0.1" if on else "Wi-Fi de la fiesta apagada (vuelve a la Wi-Fi de casa si está cerca)"})
        elif txt in ("marco_sig", "marco_ant") or re.fullmatch(r"marco \d+", txt):
            ruta = {"marco_sig": "/siguiente", "marco_ant": "/anterior"}.get(txt) or "/elegir/" + txt.split()[1]
            try:
                e = marcos_api(ruta)
                responder({"ok": True, "cmd": "marco", "marco": e["actual"], "modo": e["modo"], "msg": "🖼 Marco: " + e["marcos"][e["actual"]]["nombre"]})
            except Exception as ex:
                responder({"ok": False, "cmd": "marco", "msg": f"No se pudo cambiar el marco: {ex}"})
        elif re.fullmatch(r"modo (foto|tira|boomerang)", txt):
            try:
                e = marcos_api("/modo/" + txt.split()[1])
                nombres = {"foto": "📷 Foto", "tira": "🎞 Tira de 4 fotos", "boomerang": "🔁 Boomerang"}
                responder({"ok": True, "cmd": "modo", "modo": e["modo"], "marco": e["actual"], "msg": "Modo: " + nombres[e["modo"]]})
            except Exception as ex:
                responder({"ok": False, "cmd": "modo", "msg": f"No se pudo cambiar el modo: {ex}"})
        elif txt == "filtro_sig" or re.fullmatch(r"filtro \d+", txt):
            try:
                e = marcos_api("/filtro_sig" if txt == "filtro_sig" else "/filtro/" + txt.split()[1])
                responder({"ok": True, "cmd": "filtro", "filtro": e["filtro"], "msg": "🎨 Filtro: " + e["filtros"][e["filtro"]]["nombre"]})
            except Exception as ex:
                responder({"ok": False, "cmd": "filtro", "msg": f"No se pudo cambiar el filtro: {ex}"})
        elif txt == "ping":
            responder({"ok": True, "cmd": "ping", "msg": "pong"})
        else:
            responder({"ok": False, "cmd": txt, "msg": "Orden desconocida"})

    def ejecutar_con_registro(txt):
        if not txt.startswith(("mini ", "trozos ", "ver ", "vista")):
            print("orden:", txt, flush=True)
        try:
            ejecutar(txt)
        except Exception as e:
            import traceback
            print("ERROR en la orden", repr(txt), ":", e, flush=True)
            traceback.print_exc()
            responder({"ok": False, "cmd": txt.split()[0] if txt else "", "msg": f"Error en el photomatón: {e}"})

    # --- PIN: cada móvil tiene que mandar "pin NNNN" al conectarse; hasta entonces no se ejecuta nada.
    # Se comprueba aquí, sin hilo, para que un "estado" enviado justo detrás del PIN ya esté autorizado.
    autorizados, fallos = set(), {}

    def leer_pin():
        try:
            return open(PIN_FICHERO).read().strip()
        except OSError:
            return ""

    def al_escribir(txt, dispositivo):
        pin = leer_pin()
        if txt.startswith("pin "):
            n, hasta = fallos.get(dispositivo, (0, 0))
            if time.time() < hasta:
                responder({"ok": False, "cmd": "pin", "necesita_pin": True, "msg": f"🔒 Demasiados intentos: espera {int(hasta - time.time()) + 1} s"})
            elif not pin or txt[4:].strip() == pin:
                autorizados.add(dispositivo); fallos.pop(dispositivo, None)
                print("PIN correcto:", dispositivo, flush=True)
                responder({"ok": True, "cmd": "pin", "msg": "🔓 PIN correcto"})
            else:
                n += 1
                fallos[dispositivo] = (0, time.time() + 60) if n >= 5 else (n, 0)   # 5 fallos: 1 min bloqueado
                print("PIN incorrecto:", dispositivo, flush=True)
                responder({"ok": False, "cmd": "pin", "necesita_pin": True, "msg": "🔒 PIN incorrecto"})
            return
        if pin and dispositivo not in autorizados and txt != "ping":
            responder({"ok": False, "cmd": "pin", "necesita_pin": True, "msg": "🔒 Introduce el PIN del photomatón"})
            return
        if txt.startswith("cambiar_pin "):
            nuevo = txt.split(" ", 1)[1].strip()
            if not re.fullmatch(r"\d{4,8}", nuevo):
                responder({"ok": False, "cmd": "pin_cambiado", "msg": "El PIN debe tener de 4 a 8 cifras"})
                return
            fd = os.open(PIN_FICHERO, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(nuevo + "\n")
            autorizados.clear(); autorizados.add(dispositivo)
            responder({"ok": True, "cmd": "pin_cambiado", "pin": nuevo, "msg": "🔒 PIN cambiado"})
            return
        threading.Thread(target=ejecutar_con_registro, args=(txt,), daemon=True).start()

    def al_cambiar_dispositivo(iface, cambios, invalidadas, path=None):
        # al desconectarse un móvil, pierde la autorización (tendrá que mandar el PIN otra vez)
        if iface == "org.bluez.Device1" and "Connected" in cambios and not cambios["Connected"]:
            autorizados.discard(str(path))

    bus.add_signal_receiver(al_cambiar_dispositivo, signal_name="PropertiesChanged", dbus_interface=PROPS,
                            bus_name=BLUEZ, path_keyword="path")
    cmd.on_write = al_escribir

    # Aviso de "foto en este instante": lo manda ~/bin/foto-efectos.sh (plugin commander) por UDP local.
    # La webapp lo recibe como notificación {"cmd":"click"} y hace sonido + flash en el móvil.
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(("127.0.0.1", 47800))
    udp.setblocking(False)

    def on_udp(src, cond):
        # "click" (foto en este instante) o "cuenta <image|collage|video>" (empieza la cuenta atrás)
        msgs = []
        try:
            while True:
                msgs.append(udp.recv(64).decode(errors="replace").strip())
        except BlockingIOError:
            pass
        for m in msgs:
            if m.startswith("cuenta"):
                tipo = (m.split() + ["image"])[1]
                resp.notify({"ok": True, "cmd": "cuenta", "seg": segundos_cuenta(tipo), "tipo": tipo})
            else:
                resp.notify({"ok": True, "cmd": "click"})
        return True

    GLib.io_add_watch(udp.fileno(), GLib.IO_IN, on_udp)

    gatt = dbus.Interface(bus.get_object(BLUEZ, adapter), GATT_MGR)
    adv_mgr = dbus.Interface(bus.get_object(BLUEZ, adapter), ADV_MGR)
    adv = Advertisement(bus)
    loop = GLib.MainLoop()

    def fallo(e):
        print("Error registrando:", e, flush=True)
        loop.quit()

    # Los móviles (Web Bluetooth, sin emparejar) que siguieran conectados al servidor anterior tienen
    # guardados los identificadores viejos: sus órdenes se perderían sin error. Se desconectan para
    # que la webapp se reconecte limpia. Los mandos están emparejados y no se tocan.
    try:
        objetos = dbus.Interface(bus.get_object("org.bluez", "/"), OM).GetManagedObjects()
        for ruta, ifaces in objetos.items():
            d = ifaces.get("org.bluez.Device1")
            if d and d.get("Connected") and not d.get("Paired"):
                print("desconecto móvil con conexión antigua:", d.get("Name", "?"), flush=True)
                dbus.Interface(bus.get_object("org.bluez", ruta), "org.bluez.Device1").Disconnect()
    except Exception as e:
        print("no se pudieron revisar las conexiones antiguas:", e, flush=True)

    gatt.RegisterApplication(app.path, {}, reply_handler=lambda: print("GATT registrado", flush=True), error_handler=fallo)
    adv_mgr.RegisterAdvertisement(adv.PATH, {}, reply_handler=lambda: print("Anunciando como", NOMBRE, flush=True), error_handler=fallo)
    loop.run()
    raise SystemExit(1)


if __name__ == "__main__":
    main()
