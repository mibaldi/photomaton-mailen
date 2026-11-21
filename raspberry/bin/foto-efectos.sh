#!/bin/bash
# Lo llama el plugin commander de photobooth-app:
#   foto-efectos.sh                 evento capture_still (la foto en este instante): flash, sonido y aviso al móvil
#   foto-efectos.sh cuenta <tipo>   evento counting (empieza la cuenta atrás): aviso al móvil para la voz 3, 2, 1…
if [ "$1" = "cuenta" ]; then
  echo "cuenta ${2:-image}" > /dev/udp/127.0.0.1/47800 2>/dev/null
  exit 0
fi
export DISPLAY=:0 XAUTHORITY=/home/admin/.Xauthority
echo click > /dev/udp/127.0.0.1/47800 2>/dev/null   # aviso a la webapp por BLE (sonido + flash en el móvil)
pw-play /home/admin/photobooth-data/userdata/obturador.wav >/dev/null 2>&1 &
/usr/bin/python3 /home/admin/bin/flash.py >/dev/null 2>&1 &
exit 0
