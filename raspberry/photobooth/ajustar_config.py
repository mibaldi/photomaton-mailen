#!/usr/bin/env python3
"""Aplica en ~/photobooth-data/config/config.json los ajustes del photomatón (hace copia .bak antes).
Ejecutar con la app parada o reiniciarla después: systemctl --user restart photobooth-app"""
import json, pathlib, shutil

p = pathlib.Path.home() / "photobooth-data/config/config.json"
shutil.copy2(p, p.with_suffix(".json.bak"))
c = json.loads(p.read_text())

# Cámara: webcam V4L2 a 1280x720, la foto sale de la previsualización (ver parches/)
cam = c["cameras"]["group_backends"][0]
cam["backend_config"].update({
    "device_identifier": "/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920_XXXXXXXX-video-index0",  # tu cámara
    "CAM_RESOLUTION_WIDTH": 1280, "CAM_RESOLUTION_HEIGHT": 720,
    "switch_to_high_resolution_for_stills": False,
})

# Solo la acción "foto": sin collage, GIF, vídeo ni multicámara
for k in ("collage", "animation", "video", "multicamera"):
    c["actions"][k] = []
proc = c["actions"]["image"][0]["processing"]
proc.update({"remove_background": False, "img_background_enable": False, "fill_background_enable": False,
             "image_filter": "original", "texts_enable": False, "texts": []})
proc["img_frame"] = {"enable": True, "image": "userdata/marco.png", "mirror_effect": False}

# Disparo con los mandos BLE lo hace bin/mandos-foto.py, no el teclado del navegador
c["hardwareinputoutput"]["keyboard_input_enabled"] = False

# Interfaz: textos en español, sin galería ni botones tras la foto
st = 'class="fixed-center text-h4 text-weight-bold text-center text-white" style="text-shadow: 3px 3px 4px #444;"'
c["uisettings"].update({
    "FRONTPAGE_TEXT": f"<div {st}>🎉 ¡Es una fiesta! 🎉<br>¡Hazte una foto! 📷</div>",
    "GALLERY_EMPTY_MSG": f"<div {st}>Todavía no hay fotos 🤷<br>¡Estrena el photomatón! 📷💕</div>",
    "show_admin_on_frontpage": False,
    "show_gallery_on_frontpage": False,
    "enable_automatic_slideshow": False,
    "AUTOCLOSE_NEW_ITEM_ARRIVED": 5,
    "gallery_show_qrcode": False, "gallery_show_filter": False, "gallery_show_download": False,
    "gallery_show_delete": False, "gallery_show_shareprint": False,
    "itempresenter_show_trigger_last_action_again": False,
    "livestream_frameoverlay": {"enable": True, "image": "userdata/marco.png", "mirror_effect": False},
})
c["share"] = {"actions": []}

p.write_text(json.dumps(c, indent=2, ensure_ascii=False))
print("config.json actualizado (copia en config.json.bak)")
