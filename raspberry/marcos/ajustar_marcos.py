#!/usr/bin/env python3
"""Crea en photobooth-app una acción "image" por cada marco de userdata/marcos/marcos.json.
Todas copian la acción 0 (cuenta atrás, procesado…) y solo cambian el marco. Sin botones propios en pantalla:
el botón de disparo y las flechas los pone la extensión del quiosco. Copia de seguridad: config.json.bak-marcos.
Después: systemctl --user restart photobooth-app"""
import copy, json, pathlib, shutil

home = pathlib.Path.home()
cfg = home / "photobooth-data/config/config.json"
marcos = json.loads((home / "photobooth-data/userdata/marcos/marcos.json").read_text())
shutil.copy2(cfg, cfg.with_suffix(".json.bak-marcos"))
c = json.loads(cfg.read_text())

base = copy.deepcopy(c["actions"]["image"][0])
acciones = []
for i, m in enumerate(marcos):
    a = copy.deepcopy(base)
    if "name" in a:
        a["name"] = f"Foto marco {m['nombre']}"
    if "id" in a:
        a["id"] = f"{base['id']}-{m['clave']}" if i else base["id"]
    a["processing"]["img_frame"] = {"enable": True, "image": f"userdata/marcos/{m['archivo']}", "mirror_effect": False}
    trig = a.get("trigger", {})
    if "ui_trigger" in trig:
        trig["ui_trigger"]["show_button"] = False
    if i and "keyboard_trigger" in trig:
        trig["keyboard_trigger"]["keycode"] = ""
    acciones.append(a)
c["actions"]["image"] = acciones

# La previsualización con marco la dibuja la extensión (cambia al elegir otro marco)
ov = c["uisettings"].get("livestream_frameoverlay")
if isinstance(ov, dict):
    ov["enable"] = False

cfg.write_text(json.dumps(c, indent=2, ensure_ascii=False))
print(f"{len(acciones)} acciones de foto, una por marco: " + ", ".join(m["nombre"] for m in marcos))
