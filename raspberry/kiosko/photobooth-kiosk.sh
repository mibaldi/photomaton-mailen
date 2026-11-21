#!/bin/bash
# Kiosko del photomatón: espera al servidor y abre Chromium a pantalla completa.
# Si Chromium se cierra o el vigilante lo mata por estar colgado, se vuelve a abrir solo.
xset s off; xset -dpms; xset s noblank
pgrep -x unclutter >/dev/null || unclutter -idle 0.5 -root &
PREFS=~/.config/chromium/Default/Preferences
while true; do
  until curl -s http://localhost:8000 >/dev/null; do sleep 1; done
  # que no salga el aviso de "Chromium no se cerró correctamente" tras un reinicio brusco
  [ -f "$PREFS" ] && sed -i 's/"exit_type":"[^"]*"/"exit_type":"Normal"/; s/"exited_cleanly":false/"exited_cleanly":true/' "$PREFS"
  # --remote-debugging-port solo escucha en 127.0.0.1: lo usa el vigilante para saber si la página responde
  chromium --kiosk --password-store=basic --disable-pinch --disable-features=Translate,OverscrollHistoryNavigation,DisableLoadExtensionCommandLineSwitch --load-extension=/home/admin/marcos/extension --remote-debugging-port=9222 --noerrdialogs --disable-infobars --no-first-run --disable-session-crashed-bubble --check-for-update-interval=31536000 --ozone-platform=x11 --disable-gpu --force-device-scale-factor=0.6 --start-maximized http://localhost:8000/
  sleep 2
done
