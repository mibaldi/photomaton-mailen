#!/bin/bash
# Imprime una foto del photomatón en la Canon SELPHY (cola CUPS "SELPHY").
#   imprimir-foto.sh            -> imprime la última foto (botón de la webapp)
#   imprimir-foto.sh auto       -> igual, pero solo si la impresión automática está activada (plugin commander)
#   imprimir-foto.sh <ruta.jpg> -> imprime esa foto
# Límite de copias: ~/.config/photomaton-impresion/limite (vacío o 0 = sin límite)
IMPRESORA=SELPHY
FOTOS=/home/admin/photobooth-data/media/processed_full
CFG=/home/admin/.config/photomaton-impresion
LOG=/home/admin/photobooth-data/log/impresion.log
mkdir -p "$CFG"
log(){ echo "$(date '+%F %T') $*" >> "$LOG"; echo "$*"; }

if [ "$1" = "auto" ]; then
    [ -f "$CFG/auto" ] || exit 0
    sleep 1                                   # que termine de escribirse la foto
    shift
fi
FOTO="${1:-$(ls -t "$FOTOS"/*.jpg 2>/dev/null | head -1)}"
[ -f "$FOTO" ] || { log "ERROR no hay fotos que imprimir"; exit 1; }

HECHAS=$(cat "$CFG/contador" 2>/dev/null || echo 0)
LIMITE=$(cat "$CFG/limite" 2>/dev/null || echo 0)
if [ "${LIMITE:-0}" -gt 0 ] && [ "$HECHAS" -ge "$LIMITE" ]; then
    log "ERROR límite de $LIMITE impresiones alcanzado"; exit 2
fi
if ! lpstat -p "$IMPRESORA" >/dev/null 2>&1; then
    log "ERROR la impresora $IMPRESORA no está configurada"; exit 3
fi
cupsenable "$IMPRESORA" 2>/dev/null           # por si se quedó pausada tras un error de papel
if lp -d "$IMPRESORA" -o media=Postcard -o fit-to-page "$FOTO" >/dev/null 2>&1; then
    echo $((HECHAS + 1)) > "$CFG/contador"
    DE=""; [ "${LIMITE:-0}" -gt 0 ] && DE=" de $LIMITE"
    log "OK imprimiendo $(basename "$FOTO") (copia $((HECHAS + 1))$DE)"
else
    log "ERROR CUPS no aceptó $(basename "$FOTO")"; exit 4
fi
