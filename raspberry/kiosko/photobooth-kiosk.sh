#!/bin/bash
# Kiosko del photomatón: espera al servidor y abre Chromium a pantalla completa
xset s off; xset -dpms; xset s noblank
unclutter -idle 0.5 -root &
until curl -s http://localhost:8000 >/dev/null; do sleep 1; done
exec chromium --kiosk --password-store=basic --disable-pinch --disable-features=Translate,OverscrollHistoryNavigation,DisableLoadExtensionCommandLineSwitch --load-extension=/home/admin/marcos/extension --noerrdialogs --disable-infobars --no-first-run --disable-session-crashed-bubble --check-for-update-interval=31536000 --ozone-platform=x11 --disable-gpu --force-device-scale-factor=0.6 --start-maximized http://localhost:8000/
