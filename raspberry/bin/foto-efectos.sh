#!/bin/bash
# Lo llama el plugin commander de photobooth-app en el evento capture_still
export DISPLAY=:0 XAUTHORITY=/home/admin/.Xauthority
echo click > /dev/udp/127.0.0.1/47800 2>/dev/null   # aviso a la webapp por BLE (sonido + flash en el móvil)
pw-play /home/admin/photobooth-data/userdata/obturador.wav >/dev/null 2>&1 &
/usr/bin/python3 /home/admin/bin/flash.py >/dev/null 2>&1 &
exit 0
