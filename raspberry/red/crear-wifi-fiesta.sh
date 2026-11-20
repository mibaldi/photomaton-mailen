#!/bin/bash
# Crea la Wi-Fi propia del photomatón ("modo fiesta"): la Pi hace de punto de acceso sin internet
# y los invitados entran al panel de fotos en http://10.42.0.1
#   sudo ./crear-wifi-fiesta.sh "Photomaton Mailen" "contraseña-de-8-o-más"
# - Se activa SOLA si al arrancar no hay ninguna Wi-Fi conocida (prioridad más baja que la de casa).
# - Desde la webapp (Bluetooth) se puede encender/apagar a mano: órdenes wifi_fiesta_on / wifi_fiesta_off.
set -e
SSID="${1:?Falta el nombre de la Wi-Fi}"
PASS="${2:?Falta la contraseña (mínimo 8 caracteres)}"
[ ${#PASS} -ge 8 ] || { echo "La contraseña debe tener al menos 8 caracteres"; exit 1; }
nmcli con delete wifi-fiesta >/dev/null 2>&1 || true
nmcli con add type wifi ifname wlan0 con-name wifi-fiesta ssid "$SSID" \
    802-11-wireless.mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 \
    ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv6.method disabled \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PASS" \
    connection.autoconnect yes connection.autoconnect-priority -10
echo "Creada la Wi-Fi \"$SSID\". Panel: http://10.42.0.1"
