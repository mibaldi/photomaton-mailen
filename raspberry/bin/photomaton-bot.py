#!/usr/bin/env python3
"""Bot de Telegram para controlar el photomatón (foto, última foto, estado, reiniciar, apagar).
Solo obedece al chat guardado en OWNER (el primero que le escribe si aún no hay dueño)."""
import json, os, subprocess, time, uuid, glob, urllib.request, urllib.parse

ENV = os.path.expanduser("~/.config/photomaton-bot.env")
FOTOS = os.path.expanduser("~/photobooth-data/media/processed_full")
APP = "http://localhost:8000"

def leer_env():
    d = {}
    for l in open(ENV):
        if "=" in l:
            k, v = l.strip().split("=", 1); d[k] = v
    return d

cfg = leer_env()
API = f"https://api.telegram.org/bot{cfg["TOKEN"]}/"
OWNER = int(cfg["OWNER"]) if cfg.get("OWNER") else None

TECLADO = {"keyboard": [["📷 Foto", "🖼 Última foto"], ["📊 Estado"], ["🔄 Reiniciar", "⏻ Apagar"]],
           "resize_keyboard": True, "is_persistent": True}

def api(metodo, **params):
    data = urllib.parse.urlencode({k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in params.items()}).encode()
    with urllib.request.urlopen(API + metodo, data=data, timeout=70) as r:
        return json.load(r)

def enviar(texto, **kw):
    return api("sendMessage", chat_id=OWNER, text=texto, reply_markup=kw.pop("reply_markup", TECLADO), **kw)

def enviar_foto(ruta, caption=""):
    b = uuid.uuid4().hex
    partes = [f"--{b}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{OWNER}\r\n".encode(),
              f"--{b}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n".encode(),
              f"--{b}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"foto.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".encode(),
              open(ruta, "rb").read(), f"\r\n--{b}--\r\n".encode()]
    req = urllib.request.Request(API + "sendPhoto", data=b"".join(partes),
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    urllib.request.urlopen(req, timeout=60).read()

def ultima():
    fs = sorted(glob.glob(os.path.join(FOTOS, "*.jpg")), key=os.path.getmtime)
    return fs[-1] if fs else None

def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception as e:
        return f"? ({e})"

def estado():
    try:
        urllib.request.urlopen(APP + "/", timeout=3); app = "✅ funcionando"
    except Exception:
        app = "❌ no responde"
    cam = "✅" if glob.glob("/dev/v4l/by-id/*C920*") else "❌ no detectada"
    mandos = [n for n in ("AF15", "SnapStand") if n in open("/proc/bus/input/devices").read()]
    n = len(glob.glob(os.path.join(FOTOS, "*.jpg")))
    sync = sh("tail -n 200 ~/photobooth-data/log/drive-sync.log | grep -E 'Transferred:|ERROR' | tail -1")
    return (f"📊 Estado del photomatón\n"
            f"• App: {app}\n• Cámara C920: {cam}\n"
            f"• Mandos conectados ahora: {", ".join(mandos) or "ninguno (se conectan al pulsar)"}\n"
            f"• Fotos hechas: {n}\n"
            f"• Wi-Fi: {sh('nmcli -t -f active,ssid dev wifi | grep ^yes | cut -d: -f2') or "?"} ({sh("hostname -I").split()[0] if sh("hostname -I") else "sin IP"})\n"
            f"• Temperatura: {sh("vcgencmd measure_temp").replace("temp=", "")}\n"
            f"• Alimentación: {"✅ OK" if sh("vcgencmd get_throttled").endswith("=0x0") else "⚠️ " + sh("vcgencmd get_throttled")}\n"
            f"• Encendida: {sh("uptime -p")}\n"
            f"• Drive: {sync or "sin datos"}")

def hacer_foto():
    antes = ultima()
    try:
        urllib.request.urlopen(APP + "/api/actions/image/0", timeout=10).read()
    except Exception as e:
        enviar(f"❌ No he podido disparar: {e}"); return
    enviar("📷 ¡Foto en marcha! Sonreíd…")
    for _ in range(40):
        time.sleep(1)
        u = ultima()
        if u and u != antes:
            time.sleep(1); enviar_foto(u, "📸 Nueva foto"); return
    enviar("⚠️ La foto no ha aparecido en 40 s.")

def confirmar(accion, texto):
    api("sendMessage", chat_id=OWNER, text=texto,
        reply_markup={"inline_keyboard": [[{"text": "Sí", "callback_data": accion}, {"text": "Cancelar", "callback_data": "cancelar"}]]})

def guardar_owner(chat_id):
    global OWNER
    OWNER = chat_id
    with open(ENV, "a") as f:
        f.write(f"OWNER={chat_id}\n")

offset = None
while True:
    try:
        r = api("getUpdates", timeout=50, **({"offset": offset} if offset else {}))
    except Exception:
        time.sleep(5); continue
    for u in r.get("result", []):
        offset = u["update_id"] + 1
        if "callback_query" in u:
            q = u["callback_query"]
            if q["from"]["id"] != OWNER: continue
            api("answerCallbackQuery", callback_query_id=q["id"])
            api("editMessageReplyMarkup", chat_id=OWNER, message_id=q["message"]["message_id"], reply_markup={"inline_keyboard": []})
            if q["data"] == "apagar":
                enviar("⏻ Apagando… Cuando la pantalla se quede en blanco espera 10 s y desenchufa.")
                subprocess.Popen(["systemctl", "poweroff"])
            elif q["data"] == "reiniciar":
                enviar("🔄 Reiniciando… vuelvo en 1-2 minutos.")
                subprocess.Popen(["systemctl", "reboot"])
            else:
                enviar("Cancelado.")
            continue
        m = u.get("message")
        if not m: continue
        chat = m["chat"]["id"]
        if OWNER is None and m["chat"]["type"] == "private":
            guardar_owner(chat)
            enviar("👋 ¡Hola! Ahora este photomatón solo te obedece a ti. Usa los botones de abajo.")
            continue
        if chat != OWNER:
            continue
        t = (m.get("text") or "").lower()
        try:
            if "foto" in t and "última" not in t and "ultima" not in t: hacer_foto()
            elif "última" in t or "ultima" in t:
                f = ultima(); enviar_foto(f, os.path.basename(f)) if f else enviar("Aún no hay fotos.")
            elif "estado" in t: enviar(estado())
            elif "apagar" in t: confirmar("apagar", "¿Seguro que quieres APAGAR el photomatón?")
            elif "reiniciar" in t: confirmar("reiniciar", "¿Reiniciar el photomatón?")
            else: enviar("Usa los botones de abajo 👇")
        except Exception as e:
            try: enviar(f"❌ Error: {e}")
            except Exception: pass
