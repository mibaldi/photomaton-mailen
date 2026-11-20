#!/usr/bin/env python3
"""Servidor BLE (GATT) del photomatón: recibe órdenes de texto desde la webapp (Web Bluetooth).
Órdenes: foto | estado | imprimir | auto_on | auto_off | apagar | reiniciar | ping. Responde por notificación en la característica RESP.
Se ejecuta como servicio de sistema (root)."""
import glob, json, os, socket, subprocess, threading, urllib.request
import dbus, dbus.exceptions, dbus.mainloop.glib, dbus.service
from gi.repository import GLib

SVC_UUID = "a07498ca-ad5b-474e-940d-16f1fbe7e8cd"
CMD_UUID = "a07498ca-ad5b-474e-940d-16f1fbe7e8ce"
RESP_UUID = "a07498ca-ad5b-474e-940d-16f1fbe7e8cf"
NOMBRE = "Photomaton"
FOTOS = "/home/admin/photobooth-data/media/processed_full"
APP = "http://localhost:8000"

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
    return len(glob.glob(os.path.join(FOTOS, "*.jpg")))


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
        "pendientes_drive": None,
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
    }


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


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    adapter = "/org/bluez/hci0"
    dbus.Interface(bus.get_object(BLUEZ, adapter), PROPS).Set("org.bluez.Adapter1", "Powered", dbus.Boolean(1))

    app = Application(bus)
    svc = Service(bus, 0)
    resp = Characteristic(bus, 1, svc, RESP_UUID, ["read", "notify"])
    cmd = Characteristic(bus, 0, svc, CMD_UUID, ["write", "write-without-response"])
    svc.chars = [cmd, resp]
    app.services = [svc]

    def responder(obj):
        GLib.idle_add(lambda: (resp.notify(obj), False)[1])

    def ejecutar(txt):
        if txt == "foto":
            antes = n_fotos()
            try:
                urllib.request.urlopen(APP + "/api/actions/image/0", timeout=10).read()
            except Exception as e:
                responder({"ok": False, "cmd": "foto", "msg": f"No se pudo disparar: {e}"})
                return
            responder({"ok": True, "cmd": "foto", "msg": "Foto en marcha…"})
            for _ in range(40):
                threading.Event().wait(1)
                if n_fotos() > antes:
                    responder({"ok": True, "cmd": "foto_hecha", "msg": "¡Foto hecha!", "fotos": n_fotos()})
                    return
            responder({"ok": False, "cmd": "foto", "msg": "La foto no ha aparecido en 40 s"})
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
