# Cómo montar la Raspberry Pi del photomatón

Guía completa para dejar una Raspberry Pi 5 como photomatón: pantalla táctil de 3,5", webcam, disparo con mandos Bluetooth y control desde el móvil **sin internet** (por Bluetooth, con la [webapp](https://mibaldi.github.io/photomaton-mailen/)).

Todos los ficheros mencionados están en esta carpeta (`raspberry/`). Los de impresión 3D, en [`../impresion-3d/`](../impresion-3d/).

## Índice

1. [Material](#1-material)
2. [Sistema operativo](#2-sistema-operativo)
3. [Pantalla MHS35 de 3,5"](#3-pantalla-mhs35-de-35)
4. [photobooth-app](#4-photobooth-app)
5. [Modo quiosco (pantalla completa al arrancar)](#5-modo-quiosco)
6. [Cámara Logitech C920](#6-cámara-logitech-c920)
7. [Mandos Bluetooth para disparar](#7-mandos-bluetooth-para-disparar)
8. [Control desde el móvil por Bluetooth (sin internet)](#8-control-desde-el-móvil-por-bluetooth-sin-internet)
9. [Flash y sonido al hacer la foto](#9-flash-y-sonido-al-hacer-la-foto)
10. [Apagar de forma segura](#10-apagar-de-forma-segura)
11. [Extras con internet: bot de Telegram y subida a Google Drive](#11-extras-con-internet)
12. [Impresora Canon SELPHY CP1500](#12-impresora-canon-selphy-cp1500)
13. [Comprobaciones y problemas conocidos](#13-comprobaciones-y-problemas-conocidos)

En esta guía el usuario de la Pi se llama `admin`. Si usas otro, cambia `/home/admin` y `admin` en los ficheros.

---

## 1. Material

| Pieza | Notas |
|---|---|
| Raspberry Pi 5 | Con tarjeta microSD de 32 GB o más |
| Fuente oficial de 27 W (5 V / 5 A) | **Importante.** Con cargadores flojos la Pi se reinicia y limita los USB |
| Pantalla CUQI 3,5" SPI (MHS35) | Táctil resistiva, 480×320 |
| Logitech C920 | Cualquier webcam UVC vale, ajustando resolución |
| Mando Bluetooth de selfies (opcional) | Probados "AF15" y "SnapStand" |
| Ventilador o Active Cooler (recomendado) | Dentro de la caja cerrada llegó a 83 °C |
| Caja impresa en 3D | Ver [`../impresion-3d/`](../impresion-3d/) |

La Pi 5 **no tiene salida de audio** (ni jack). Para que suene, hace falta un altavoz USB "con audio por USB" o Bluetooth. Sin altavoz, el sonido puede salir por el móvil con la webapp.

## 2. Sistema operativo

1. Con **Raspberry Pi Imager**, instala **Raspberry Pi OS (64-bit)** con escritorio (probado con Trixie / Debian 13).
2. En las opciones del Imager: usuario `admin`, Wi-Fi de casa (solo para instalar) y **SSH activado**.
3. Arranca y entra por SSH: `ssh admin@<ip-de-la-pi>`.
4. Actualiza:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git pipx v4l-utils unclutter python3-dbus python3-gi python3-tk
```

## 3. Pantalla MHS35 de 3,5"

Se usa el driver de goodtft (LCD-show). **Desactiva el HDMI** y pasa el escritorio a X11.

```bash
cd ~
git clone https://github.com/goodtft/LCD-show.git
cd LCD-show
sudo ./MHS35-show          # reinicia solo
```

Para girarla 180° (cables hacia arriba, como va en la caja):

```bash
cd ~/LCD-show && sudo ./rotate.sh 180    # reinicia solo
```

Esto deja `dtoverlay=mhs35:rotate=270` en `/boot/firmware/config.txt` y la calibración táctil girada.

Para volver al HDMI: `cd ~/LCD-show && sudo ./LCD-hdmi`.

> **Pantalla en blanco:** es normal mientras la Pi está apagada o arrancando. La pantalla recibe corriente pero nadie le manda imagen. LED rojo de la Pi = apagada.

## 4. photobooth-app

Se usa [photobooth-app](https://photobooth-app.org/) 9.x.

```bash
pipx install photobooth-app
mkdir -p ~/photobooth-data ~/.config/systemd/user
cp systemd/user/photobooth-app.service ~/.config/systemd/user/
sudo loginctl enable-linger admin            # que los servicios de usuario arranquen sin iniciar sesión
systemctl --user daemon-reload
systemctl --user enable --now photobooth-app
```

Abre `http://<ip-de-la-pi>:8000` desde otro equipo de la misma red. El panel de administración está en `/#/admin` (contraseña por defecto `0000`: **cámbiala**).

### Ajustes de la app

`photobooth/ajustar_config.py` deja la app en modo "un solo botón": solo fotos, sin galería ni botones tras la foto, textos en español y marco de fiesta.

```bash
python3 photobooth/ajustar_config.py
systemctl --user restart photobooth-app
```

Antes, edita en el script la ruta de tu cámara (`ls /dev/v4l/by-id/`) y copia tu marco:

```bash
mkdir -p ~/photobooth-data/userdata
cp ../impresion-3d/marco/marco_fiesta_mailen.png ~/photobooth-data/userdata/marco.png
```

El marco es un PNG de 1280×720 con el centro transparente. Lo genera `../impresion-3d/marco/marco.py` (Pillow); cambia el texto y vuelve a ejecutarlo.

## 5. Modo quiosco

Chromium a pantalla completa al arrancar el escritorio, esperando a que la app responda:

```bash
cp kiosko/photobooth-kiosk.sh ~/ && chmod +x ~/photobooth-kiosk.sh
mkdir -p ~/.config/autostart && cp kiosko/photobooth-kiosk.desktop ~/.config/autostart/
sudo raspi-config nonint do_blanking 1      # que la pantalla no se apague
```

`--force-device-scale-factor=0.6` hace que la interfaz quepa en 480×320 y `--disable-gpu` evita problemas, porque con este driver no hay aceleración.

> Por SSH usa `pkill -x chromium`, no `pkill -f chromium`, que también mata tu propia sesión.

## 6. Cámara Logitech C920

1. Ajustes de imagen al arrancar la app (50 Hz para evitar parpadeo de las luces, algo más de brillo y compensación de contraluz):

```bash
mkdir -p ~/.config/systemd/user/photobooth-app.service.d
cp systemd/user/photobooth-app.service.d/camara.conf ~/.config/systemd/user/photobooth-app.service.d/
# edita el id de la cámara dentro (ls /dev/v4l/by-id/)
systemctl --user daemon-reload && systemctl --user restart photobooth-app
```

2. **Parche para que la foto no salga oscura.** En cada foto, photobooth-app corta y reabre el stream de la webcam. La C920, al reabrirse tan rápido, entrega imágenes mucho más oscuras durante varios segundos: la previsualización se veía bien y la foto salía oscura. El parche hace que la foto sea el fotograma de la previsualización, sin cortar el stream:

```bash
python3 parches/webcamv4l_foto_desde_stream.py
systemctl --user restart photobooth-app
```

Requiere `switch_to_high_resolution_for_stills: false`, que ya pone `ajustar_config.py`. Las fotos quedan a 1280×720. **Si actualizas photobooth-app, vuelve a aplicarlo.**

## 7. Mandos Bluetooth para disparar

Los mandos de selfies son teclados Bluetooth que mandan "subir/bajar volumen".

1. Empareja el mando (pon el mando en modo emparejamiento antes):

```bash
bluetoothctl
  power on
  agent NoInputNoOutput
  default-agent
  scan on            # espera a que salga el mando y copia su dirección
  pair XX:XX:XX:XX:XX:XX
  trust XX:XX:XX:XX:XX:XX
  connect XX:XX:XX:XX:XX:XX
  quit
```

2. Quita los atajos de volumen del escritorio. Openbox se "come" esas teclas:

```bash
mkdir -p ~/.config/openbox
python3 - <<'EOF'
import re
s = open("/etc/xdg/openbox/rpd-rc.xml").read()
s = re.sub(r'\s*<keybind key="XF86Audio(Raise|Lower)Volume">.*?</keybind>', "", s, flags=re.S)
open("/home/admin/.config/openbox/rpd-rc.xml", "w").write(s)
EOF
DISPLAY=:0 openbox --reconfigure
```

3. Servicio que lee los mandos y dispara la foto (cualquier tecla de volumen, con 2 s de antirrebote):

```bash
sudo usermod -aG input admin     # permiso para leer /dev/input (cierra sesión o reinicia)
mkdir -p ~/bin && cp bin/mandos-foto.py ~/bin/ && chmod +x ~/bin/mandos-foto.py
cp systemd/user/mandos-foto.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now mandos-foto
```

Si tu mando tiene otro nombre, añádelo en `NOMBRES` dentro de `mandos-foto.py` (míralo con `cat /proc/bus/input/devices`).

> No pongas `After=photobooth-app.service` en estos servicios: photobooth-app ya lleva `After=default.target` y se crea un ciclo que impide que arranquen.

## 8. Control desde el móvil por Bluetooth (sin internet)

La Pi anuncia un servicio Bluetooth LE llamado **"Photomaton"**. La [webapp](https://mibaldi.github.io/photomaton-mailen/) (Chrome en Android) se conecta y manda órdenes: **foto, estado, reiniciar, apagar**. No hace falta Wi-Fi ni internet: solo Bluetooth.

```bash
sudo install -m 755 ble/photomaton-ble.py /usr/local/bin/photomaton-ble.py
sudo cp systemd/system/photomaton-ble.service /etc/systemd/system/
sudo cp polkit/50-admin-apagar.rules /etc/polkit-1/rules.d/
sudo systemctl daemon-reload && sudo systemctl enable --now photomaton-ble
```

En el móvil:

1. Abre la webapp en **Chrome** (necesita HTTPS; por eso está en GitHub Pages).
2. Menú ⋮ → **Añadir a pantalla de inicio**. Funciona sin conexión gracias al service worker.
3. Pulsa **Conectar** y elige "Photomaton".

Detalles técnicos:

| | UUID |
|---|---|
| Servicio | `a07498ca-ad5b-474e-940d-16f1fbe7e8cd` |
| Órdenes (write, texto) | `a07498ca-ad5b-474e-940d-16f1fbe7e8ce` |
| Respuestas (notify, JSON) | `a07498ca-ad5b-474e-940d-16f1fbe7e8cf` |

> Si BlueZ dice "No valid service object found", la propiedad `Service` de la característica tiene que ser `dbus.ObjectPath`. Ya está corregido en el script. Si sale "Maximum advertisements reached", `sudo systemctl restart bluetooth`.

## 9. Flash y sonido al hacer la foto

photobooth-app trae el plugin **commander**, que ejecuta un comando en cada evento. En `capture_still` se lanza `bin/foto-efectos.sh`, que hace tres cosas:

- **Destello blanco** a pantalla completa en la pantalla de la caja (`bin/flash.py`, 250 ms).
- **Sonido de obturador** (`obturador.wav`) si hay altavoz conectado.
- **Aviso por Bluetooth al móvil** (UDP local → servidor BLE). La webapp suena, destella y vibra. Solo funciona con la página abierta y la casilla "Sonido y flash en este móvil" marcada.

```bash
cp bin/flash.py bin/foto-efectos.sh ~/bin/ && chmod +x ~/bin/flash.py ~/bin/foto-efectos.sh
python3 bin/generar-obturador.py                          # crea ~/photobooth-data/userdata/obturador.wav
cp photobooth/plugin_commander.json ~/photobooth-data/config/
systemctl --user restart photobooth-app
```

## 10. Apagar de forma segura

Nunca desenchufes con la Pi encendida (puede corromperse la tarjeta). Formas de apagar:

- **Webapp** (Bluetooth) → botón Apagar.
- **Bot de Telegram** (si hay internet) → ⏻ Apagar.
- **Botón de la Pi 5** → apaga directamente. Para que no salga el menú del escritorio, cambia en `~/.config/openbox/rpd-rc.xml` el comando de la tecla `XF86PowerOff`:

```bash
sed -i "s#<command>pwrkey</command>#<command>systemctl poweroff</command>#" ~/.config/openbox/rpd-rc.xml
DISPLAY=:0 openbox --reconfigure
```

En la caja, el botón se pulsa desde fuera por la rejilla con un palito impreso (`../impresion-3d/palos_boton_punta.stl`).

Cuando la pantalla se quede en blanco y el LED en rojo, ya se puede desenchufar.

**Encender:** enchufar la corriente (arranca sola). Si la desenchufaste y vuelves a enchufar enseguida, puede quedarse en rojo: espera unos 15 s antes de enchufar, o pulsa el botón.

## 11. Extras con internet

Son opcionales: el photomatón funciona igual sin red. Las fotos se guardan en la Pi (`~/photobooth-data/media/processed_full`).

### Bot de Telegram

Botones: 📷 Foto, 🖼 Última foto, 📊 Estado, 🔄 Reiniciar, ⏻ Apagar.

1. Crea un bot con [@BotFather](https://t.me/BotFather) y copia el token.
2. En la Pi:

```bash
cp bin/photomaton-bot.py ~/bin/ && chmod +x ~/bin/photomaton-bot.py
cp bin/photomaton-bot.env.example ~/.config/photomaton-bot.env
nano ~/.config/photomaton-bot.env          # pega el token
chmod 600 ~/.config/photomaton-bot.env
cp systemd/user/photomaton-bot.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now photomaton-bot
```

3. Escribe al bot desde tu Telegram: **el primer chat privado queda como dueño** y el bot ya no hace caso a nadie más.

### Subida automática a Google Drive (rclone)

1. Configura un remoto `gdrive` con `rclone config`. El token se puede generar en otro ordenador con `rclone authorize drive`. Pon `root_folder_id` = id de la carpeta de Drive.
2. Instala el timer, que sube cada minuto lo nuevo a `gdrive:Fotos`:

```bash
touch ~/.config/rclone/excluir_pruebas.txt       # nombres de fotos de prueba que no quieres subir
cp systemd/user/photobooth-drive.service systemd/user/photobooth-drive.timer ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now photobooth-drive.timer
```

Sin internet simplemente falla y lo vuelve a intentar: cuando haya conexión sube todo lo pendiente.

## 12. Impresora Canon SELPHY CP1500

Conectada por USB (cable USB-A a USB-C de datos; **no viene en la caja**). Imprime en tamaño postal sin internet.

```bash
sudo apt install -y cups printer-driver-gutenprint
sudo usermod -aG lpadmin admin
# ipp-usb se queda con la impresora y no funciona con la CP1500 ("Device initialization timed out")
sudo systemctl stop ipp-usb && sudo systemctl mask ipp-usb
sudo modprobe -r usblp && sudo modprobe usblp
U=$(sudo lpinfo -v | grep -o "usb://Canon/[^ ]*" | head -1)
# gutenprint 5.3.4 (Debian) no trae la CP1500: se usa el driver de la CP1300, casi idéntica
sudo lpadmin -p SELPHY -E -v "$U" -m gutenprint.5.3://canon-cp1300/expert -o PageSize=Postcard
sudo lpadmin -d SELPHY
cp bin/imprimir-foto.sh ~/bin/ && chmod +x ~/bin/imprimir-foto.sh
```

La versión actual de gutenprint en desarrollo ya incluye la CP1500 (`canon-cp1500`). Si el driver de la CP1300 da problemas, compílala desde [el código fuente](https://sourceforge.net/p/gimp-print/source/).

Cómo se imprime:

- **Botón "🖨 Imprimir última foto"** en la webapp (orden BLE `imprimir`).
- **Impresión automática**: casilla en la webapp (órdenes `auto_on` / `auto_off`). El plugin commander ejecuta `imprimir-foto.sh auto` al terminar cada foto, que solo imprime si existe `~/.config/photomaton-impresion/auto`.
- **Límite de copias** (para que no se acabe el papel): `echo 54 > ~/.config/photomaton-impresion/limite`. El contador está en `~/.config/photomaton-impresion/contador` (bórralo para empezar de cero).
- Registro en `~/photobooth-data/log/impresion.log`.

## 13. Comprobaciones y problemas conocidos

```bash
systemctl --user is-active photobooth-app mandos-foto photomaton-bot photobooth-drive.timer
systemctl is-active photomaton-ble
vcgencmd measure_temp; vcgencmd get_throttled    # 0x0 = alimentación OK
tail -f ~/photobooth-data/log/photobooth_*.log
```

| Problema | Causa / solución |
|---|---|
| Pantalla en blanco | Pi apagada o arrancando (LED rojo = apagada) |
| Foto más oscura que la previsualización | Falta el parche del apartado 6 |
| El mando no dispara | ¿Emparejado y `trust`? ¿Servicio `mandos-foto` activo? ¿Usuario en el grupo `input`? |
| La webapp no encuentra "Photomaton" | Usa Chrome en Android; `sudo systemctl restart bluetooth photomaton-ble` |
| Reinicios solos | Fuente de alimentación insuficiente: usa la oficial de 27 W |
| `get_throttled` distinto de `0x0` | Poca corriente o mucha temperatura: ventilador y fuente oficial |
| No imprime | `lpstat -p SELPHY`; si está pausada: `cupsenable SELPHY`. Papel y cartucho bien puestos |
| No suena | La Pi 5 no tiene audio: altavoz USB/Bluetooth, o usa el sonido de la webapp |
