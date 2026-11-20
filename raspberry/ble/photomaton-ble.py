#!/usr/bin/env python3
"""Servidor BLE (GATT) del photomatón: recibe órdenes de texto desde la webapp (Web Bluetooth).
Órdenes: foto | estado | imprimir | auto_on | auto_off | invitados_on | invitados_off | wifi_fiesta_on | wifi_fiesta_off |
apagar | reiniciar | ping.
Marcos y modos: marco <n> | marco_sig | marco_ant | modo <foto|tira|boomerang> (los guarda marcos-servicio, 127.0.0.1:8010).
Galería por BLE: lista | mini <foto> | ver <foto> | trozos <tipo> <foto> <n,n,…> | imprimir <foto>.
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


def lista_fotos():
    try:
        excl = [l.strip().lstrip("/") for l in open(EXCLUIR) if l.strip() and not l.startswith("#")]
    except OSError:
        excl = []
    fotos = [(os.path.getmtime(f), os.path.basename(f)) for f in glob.glob(os.path.join(FOTOS, "*.jpg")) + glob.glob(os.path.join(FOTOS, "*.mp4"))]
    return [n for _, n in sorted(fotos, reverse=True) if NOMBRE_OK.match(n) and not any(fnmatch.fnmatch(n, p) for p in excl)]


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
        return {"marco": e["actual"], "modo": e["modo"]}
    except Exception:
        return {"marco": None, "modo": None}


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
        self.on_write(bytes(value).decode("utf-8", "ignore").strip().lower())

    @dbus.service.method("org.bluez.GattCharacteristic1")
    def StartNotify(self):
        self.notifying = True

    @dbus.service.method("org.bluez.GattCharacteristic1")
    def StopNotify(self):
        self.notifying = False

    def on_write(self, txt):
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
        if txt.split(" ", 1)[0] in ("lista", "mini", "ver", "trozos") or txt.startswith("imprimir "):
            galeria(txt)
        elif txt == "foto":
            antes = n_fotos()
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
        elif txt == "ping":
            responder({"ok": True, "cmd": "ping", "msg": "pong"})
        else:
            responder({"ok": False, "cmd": txt, "msg": "Orden desconocida"})

    cmd.on_write = lambda txt: threading.Thread(target=ejecutar, args=(txt,), daemon=True).start()

    # Aviso de "foto en este instante": lo manda ~/bin/foto-efectos.sh (plugin commander) por UDP local.
    # La webapp lo recibe como notificación {"cmd":"click"} y hace sonido + flash en el móvil.
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(("127.0.0.1", 47800))
    udp.setblocking(False)

    def on_udp(src, cond):
        try:
            while True:
                udp.recv(64)
        except BlockingIOError:
            pass
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

    gatt.RegisterApplication(app.path, {}, reply_handler=lambda: print("GATT registrado", flush=True), error_handler=fallo)
    adv_mgr.RegisterAdvertisement(adv.PATH, {}, reply_handler=lambda: print("Anunciando como", NOMBRE, flush=True), error_handler=fallo)
    loop.run()
    raise SystemExit(1)


if __name__ == "__main__":
    main()
