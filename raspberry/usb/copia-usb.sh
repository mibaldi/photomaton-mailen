#!/bin/bash
# Copia de seguridad al enchufar un pendrive: copia las fotos y boomerangs que falten a
# "<pendrive>/Photomaton Mailen/" y lo desmonta para poder quitarlo. No borra nada del pendrive.
# La lanza udev (99-photomaton-usb.rules -> copia-usb@<dispositivo>.service) como root.
# Estado para la pantalla y la webapp en /run/photomaton-copia.json.
DEV="/dev/${1:?falta el dispositivo}"
ORIGEN=/home/admin/photobooth-data/media/processed_full
EXCLUIR=/home/admin/.config/rclone/excluir_pruebas.txt
DESTINO_NOMBRE="Photomaton Mailen"
ESTADO=/run/photomaton-copia.json
LOG=/home/admin/photobooth-data/log/copia-usb.log
PUNTO=/mnt/copia-usb

estado() {  # estado <copiando|hecha|error> <hechas> <total> <mensaje>
  printf '{"estado":"%s","hechas":%d,"total":%d,"msg":"%s","ts":%d}\n' "$1" "$2" "$3" "$4" "$(date +%s)" > "$ESTADO.tmp"
  mv "$ESTADO.tmp" "$ESTADO"; chmod 644 "$ESTADO"
}
log() { echo "$(date '+%F %T') $*" >> "$LOG"; }

estado copiando 0 0 "💾 Pendrive detectado…"
sleep 4                                     # por si el escritorio lo monta solo
MONTADO_POR_MI=0
DIR=$(findmnt -nro TARGET -S "$DEV" | head -1)
if [ -z "$DIR" ]; then
  mkdir -p "$PUNTO"
  if ! mount -o uid=1000,gid=1000,umask=022 "$DEV" "$PUNTO" 2>/dev/null && ! mount "$DEV" "$PUNTO" 2>>"$LOG"; then
    estado error 0 0 "⚠️ No se pudo leer el pendrive"; log "no se pudo montar $DEV"; exit 1
  fi
  DIR=$PUNTO; MONTADO_POR_MI=1
fi
DEST="$DIR/$DESTINO_NOMBRE"
mkdir -p "$DEST" || { estado error 0 0 "⚠️ El pendrive no deja escribir"; exit 1; }

# lista de ficheros: fotos y boomerangs, sin las fotos sueltas de la tira ni las de prueba
mapfile -t PATRONES < <(grep -v '^#' "$EXCLUIR" 2>/dev/null | sed 's|^/||' | grep -v '^$')
FICHEROS=()
for f in "$ORIGEN"/*.jpg "$ORIGEN"/*.mp4; do
  [ -e "$f" ] || continue
  n=$(basename "$f")
  [[ $n == *_hidden* ]] && continue
  saltar=0; for p in "${PATRONES[@]}"; do [[ $n == $p ]] && { saltar=1; break; }; done
  [ $saltar = 1 ] || FICHEROS+=("$f")
done
TOTAL=${#FICHEROS[@]}; HECHAS=0; NUEVAS=0; ERRORES=0
log "copia a $DEV ($DIR): $TOTAL ficheros"
for f in "${FICHEROS[@]}"; do
  d="$DEST/$(basename "$f")"
  if [ ! -e "$d" ] || [ "$(stat -c %s "$f")" != "$(stat -c %s "$d")" ]; then
    if cp "$f" "$d.tmp" && mv "$d.tmp" "$d"; then NUEVAS=$((NUEVAS+1)); else ERRORES=$((ERRORES+1)); rm -f "$d.tmp"; fi
  fi
  HECHAS=$((HECHAS+1))
  [ $((HECHAS % 5)) = 0 ] && estado copiando $HECHAS $TOTAL "💾 Copiando al pendrive… $HECHAS de $TOTAL"
done
estado copiando $TOTAL $TOTAL "💾 Terminando de grabar… no lo quites"
sync
[ $MONTADO_POR_MI = 1 ] && umount "$DIR"
if [ $ERRORES -gt 0 ]; then
  estado error $HECHAS $TOTAL "⚠️ Copia con $ERRORES errores (¿pendrive lleno?)"; log "errores: $ERRORES"
else
  estado hecha $TOTAL $TOTAL "✅ Copia hecha: $TOTAL fotos ($NUEVAS nuevas). Ya puedes quitar el pendrive"
fi
log "fin: $NUEVAS nuevas, $ERRORES errores"
