#!/bin/bash
# Imprime una foto del photomatón en la Canon SELPHY (cola CUPS "SELPHY").
#   imprimir-foto.sh            -> imprime la última foto (botón de la webapp)
#   imprimir-foto.sh auto       -> igual, pero solo si la impresión automática está activada (plugin commander)
#   imprimir-foto.sh <ruta.jpg> -> imprime esa foto
# Límite de copias: ~/.config/photomaton-impresion/limite (vacío o 0 = sin límite)
#
# Las fotos se mandan de una en una: la SELPHY sigue imprimiendo ~1 min después de que CUPS da el
# trabajo por terminado, y si le llega otro en ese rato el driver se cuelga. Un proceso en segundo
# plano (--cola) hace turno con flock, espera a que acabe y, si se atasca, cancela, reinicia CUPS y reintenta.
IMPRESORA=SELPHY
FOTOS=/home/admin/photobooth-data/media/processed_full
CFG=/home/admin/.config/photomaton-impresion
LOG=/home/admin/photobooth-data/log/impresion.log
ESPERA_TRAS_ENVIO=60     # s que tarda la impresora en terminar el papel tras recibir los datos
MAX_ENVIO=150            # s máximos de "enviando datos" antes de darlo por atascado
mkdir -p "$CFG"
log(){ echo "$(date '+%F %T') $*" >> "$LOG"; echo "$*"; }

if [ "$1" = "--cola" ]; then
    FOTO="$2"
    exec 9>"$CFG/cola.lock"
    flock 9                                   # esperar turno
    for intento in 1 2; do
        cupsenable "$IMPRESORA" 2>/dev/null   # por si se quedó pausada tras un error de papel
        JOB=$(lp -d "$IMPRESORA" -o media=Postcard -o fit-to-page "$FOTO" 2>/dev/null | grep -o "$IMPRESORA-[0-9]*")
        [ -n "$JOB" ] || { log "ERROR CUPS no aceptó $(basename "$FOTO")"; exit 4; }
        t=0
        while lpstat -o "$IMPRESORA" 2>/dev/null | grep -q "^$JOB "; do
            sleep 3; t=$((t + 3))
            [ $t -ge $MAX_ENVIO ] && break
        done
        if [ $t -lt $MAX_ENVIO ]; then
            log "OK enviada $(basename "$FOTO") ($JOB)"
            sleep $ESPERA_TRAS_ENVIO          # dejar que termine el papel antes de la siguiente
            exit 0
        fi
        log "AVISO $JOB atascado, cancelo y reinicio CUPS (intento $intento)"
        cancel "$JOB" 2>/dev/null
        sudo -n systemctl restart cups 2>/dev/null
        sleep 15
    done
    log "ERROR no se pudo imprimir $(basename "$FOTO") tras reintentar"
    exit 5
fi

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
EN_COLA=$(pgrep -fc "imprimir-foto.sh --cola")
echo $((HECHAS + 1)) > "$CFG/contador"
setsid "$0" --cola "$FOTO" </dev/null >/dev/null 2>&1 &
DE=""; [ "${LIMITE:-0}" -gt 0 ] && DE=" de $LIMITE"
TURNO=""; [ "$EN_COLA" -gt 0 ] && TURNO=", $EN_COLA por delante"
log "OK imprimiendo $(basename "$FOTO") (copia $((HECHAS + 1))$DE$TURNO)"
