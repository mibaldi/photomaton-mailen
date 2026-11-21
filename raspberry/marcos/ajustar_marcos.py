#!/usr/bin/env python3
"""Configura en photobooth-app los modos del photomatón (copia de seguridad: config.json.bak-marcos):
  - foto:      una acción "image" por cada (filtro, marco): la acción f*nº_marcos + N lleva el marco N de
               userdata/marcos/marcos.json con el filtro f de FILTROS (0 = normal, así image/N sigue siendo el marco N).
               Con el filtro normal, si el marco trae su propio "filtro" (p. ej. blanco y negro), se aplica
  - tira:      collage de 4 fotos seguidas en tamaño postal (userdata/marcos/collage_4.png + collage.json)
  - boomerang: vídeo corto de ida y vuelta
Sin botones propios en pantalla: el disparo, las flechas y el modo los pone la extensión del quiosco.
Después: systemctl --user restart photobooth-app"""
import copy, json, pathlib, shutil

home = pathlib.Path.home()
cfg = home / "photobooth-data/config/config.json"
dmarcos = home / "photobooth-data/userdata/marcos"
marcos = json.loads((dmarcos / "marcos.json").read_text())
collage = json.loads((dmarcos / "collage.json").read_text())
shutil.copy2(cfg, cfg.with_suffix(".json.bak-marcos"))
c = json.loads(cfg.read_text())

# Misma lista y orden que FILTROS en marcos-servicio.py
FILTROS = [("Normal", "original"), ("Blanco y negro", "FilterPilgram2.inkwell"), ("Vintage", "FilterPilgram2.nashville")]

SIN_BOTON = {"ui_trigger": {"show_button": False}, "keyboard_trigger": {"keycode": ""}, "gpio_trigger": {"pin": ""}}

# --- foto: una acción por marco ---
base = copy.deepcopy(c["actions"]["image"][0])
base.setdefault("jobcontrol", {})["countdown_capture"] = 3.0   # 3, 2, 1… ¡patata! (voz en el móvil)
acciones = []
for f, (fnombre, fid) in enumerate(FILTROS):
    for i, m in enumerate(marcos):
        a = copy.deepcopy(base)
        a["name"] = f"Foto marco {m['nombre']}" + (f" · {fnombre}" if f else "")
        a["processing"]["img_frame"] = {"enable": True, "image": f"userdata/marcos/{m['archivo']}", "mirror_effect": False}
        a["processing"]["image_filter"] = m.get("filtro", "original") if f == 0 else fid
        trig = a.setdefault("trigger", {})
        trig.setdefault("ui_trigger", {})["show_button"] = False
        if i or f:
            trig.setdefault("keyboard_trigger", {})["keycode"] = ""
        acciones.append(a)
c["actions"]["image"] = acciones

# --- tira de 4 fotos ---
c["actions"]["collage"] = [{
    "name": "Tira de 4 fotos" + (f" · {fnombre}" if f else ""),
    "jobcontrol": {"countdown_capture": 3.0, "countdown_capture_second_following": 2.0,
                   "ask_approval_each_capture": False, "show_individual_captures_in_gallery": False},
    "processing": {
        "capture_remove_background": False, "capture_fill_background_enable": False, "capture_img_background_enable": False,
        "canvas_width": collage["ancho"], "canvas_height": collage["alto"],
        "merge_definition": [{"description": f"foto {k + 1}", "pos_x": x, "pos_y": y, "pos_z": 0, "width": w, "height": h,
                              "rotate": 0, "predefined_image": None, "image_filter": fid}
                             for k, (x, y, w, h) in enumerate(collage["huecos"])],
        "canvas_fill_background_enable": False, "canvas_img_background_enable": False,
        "canvas_img_front_enable": True, "canvas_img_front_file": "userdata/marcos/collage_4.png",
        "canvas_texts_enable": False, "canvas_texts": [],
    },
    "trigger": copy.deepcopy(SIN_BOTON),
} for f, (fnombre, fid) in enumerate(FILTROS)]

# --- boomerang ---
c["actions"]["video"] = [{
    "name": "Boomerang",
    "jobcontrol": {"countdown_capture": 3.0},
    "processing": {"video_duration": 3, "boomerang": True, "boomerang_speed": 1.5, "video_framerate": 15},
    "trigger": copy.deepcopy(SIN_BOTON),
}]

# La previsualización con marco la dibuja la extensión (cambia al elegir otro marco)
ov = c["uisettings"].get("livestream_frameoverlay")
if isinstance(ov, dict):
    ov["enable"] = False

cfg.write_text(json.dumps(c, indent=2, ensure_ascii=False))

# Impresión automática también para las tiras (plugin commander)
pc = home / "photobooth-data/config/plugin_commander.json"
if pc.exists():
    pcj = json.loads(pc.read_text())
    for t in pcj.get("tasks_commands", []):
        if "imprimir-foto.sh" in t.get("command", "") and "collage" not in t.get("filter_mediaitem_types", []):
            t["filter_mediaitem_types"].append("collage")
    pc.write_text(json.dumps(pcj, indent=2, ensure_ascii=False))

print(f"{len(acciones)} acciones de foto ({len(FILTROS)} filtros × {len(marcos)} marcos: {', '.join(m['nombre'] for m in marcos)}) + tira de 4 + boomerang")
