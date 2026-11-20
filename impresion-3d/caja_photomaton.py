"""
Caja photomatón para Raspberry Pi 5 + carcasa CUQI 3,5" + Logitech C920 encima.
Paramétrica: cambia los valores de PARÁMETROS y vuelve a ejecutar.

Ejes: X = ancho, Y = alto (vertical en uso), Z = fondo (0 = cara frontal).
El cuerpo se imprime con el frontal sobre la cama (Z hacia arriba), sin soportes.
"""
from manifold3d import Manifold, CrossSection, JoinType
import numpy as np, trimesh, sys, pathlib

# ---------------- PARÁMETROS (mm) ----------------
# Carcasa CUQI medida por el usuario: 9 x 6 x 3 cm
CASE_W, CASE_H, CASE_D = 90.0, 60.0, 30.0
CLR = 0.4                 # holgura del rebaje alrededor de la carcasa
WIN_W, WIN_H = 76.0, 51.0  # ventana visible (zona activa de la pantalla ≈ 73,4 x 49)
WIN_OFF_X, WIN_OFF_Y = 0.0, 0.0  # desplazamiento de la pantalla respecto al centro de la carcasa

W, H, D = 180.0, 200.0, 70.0   # medidas exteriores del cuerpo (sin la tapa trasera)
WALL = 3.0                # grosor de paredes
FRONT = 3.0               # grosor del frontal
RECESS = 1.5              # profundidad del rebaje donde encaja la carcasa (bisel que queda: FRONT-RECESS)
TOP_CLEAR = 40.0          # hueco libre entre la carcasa y el techo (curva del USB-C)
BACK_T = 3.0              # grosor de la tapa trasera
COL = 9.0                 # columnas de las esquinas para los tornillos
PILOT = 2.6               # agujero guía para tornillo M3 autorroscante
SCREW = 3.4               # paso del tornillo M3 en la tapa
TRIPOD = 6.8              # agujero para tornillo 1/4"-20 (rosca de la C920)
TRIPOD_Z = 28.0           # distancia del agujero de trípode al frontal
CABLE_SLOT = (22.0, 11.0) # ranura del techo para meter el cable USB de la C920
EXIT = (44.0, 20.0)       # salida de cables abajo en la tapa trasera (ancho x alto)
PUSH_GAP = 0.6            # holgura entre el marco empujador y la carcasa
# Funda del mando BLE (AF15) en el lateral derecho
MANDO_W, MANDO_L, MANDO_T = 24.0, 35.0, 11.0  # ancho x largo x grueso (el grueso real es algo más de 1 cm)
MANDO_CLR = 1.2           # holgura total en el ancho (hueco 25,2 mm)
MANDO_CLR_T = 4.0         # hueco de 15 mm de grueso, como pidió el usuario
MANDO_PROF = 24.0         # cuánto entra el mando en la funda (el resto asoma para cogerlo)
MANDO_Y0 = 30.0           # altura del fondo de la funda desde la base
FUNDA_PARED = 2.0
CORDON = 4.5              # agujero para atar el cordón
FUNDA_INTEGRADA = False   # False: la funda va como pieza aparte (funda_mando.stl) para pegar
PLACA_T = 2.5             # grosor de la placa de pegado de la funda suelta
# --------------------------------------------------

def box(x0, y0, z0, x1, y1, z1):
    return Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])

def rbox(cx, cy, w, h, z0, z1, r=2.0):
    sq = CrossSection.square([w - 2 * r, h - 2 * r], center=True)
    sq = sq.offset(r, join_type=JoinType.Round, circular_segments=24)
    return Manifold.extrude(sq, z1 - z0).translate([cx, cy, z0])

def cyl_z(cx, cy, d, z0, z1, n=32):
    return Manifold.cylinder(z1 - z0, d / 2, d / 2, n).translate([cx, cy, z0])

def cyl_y(cx, cz, d, y0, y1, n=32):
    # cilindro a lo largo de Y
    return Manifold.cylinder(y1 - y0, d / 2, d / 2, n).rotate([-90, 0, 0]).translate([cx, y0, cz])

# Posición de la carcasa: centrada en X, pegada arriba dejando TOP_CLEAR
cx = W / 2
case_top = H - WALL - TOP_CLEAR
cy = case_top - CASE_H / 2
win_cx, win_cy = cx + WIN_OFF_X, cy + WIN_OFF_Y
case_back_z = FRONT - RECESS + CASE_D

col_pos = [(WALL, WALL), (W - WALL - COL, WALL), (WALL, H - WALL - COL), (W - WALL - COL, H - WALL - COL)]

def cuerpo():
    outer = box(0, 0, 0, W, H, D)
    inner = box(WALL, WALL, FRONT, W - WALL, H - WALL, D + 1)
    b = outer - inner
    # columnas de esquina con agujero guía en la parte de atrás
    for (x, y) in col_pos:
        b += box(x, y, FRONT, x + COL, y + COL, D)
        b -= cyl_z(x + COL / 2, y + COL / 2, PILOT, D - 14, D + 1)
    # rebaje para la carcasa y ventana de la pantalla
    b -= box(cx - CASE_W / 2 - CLR, cy - CASE_H / 2 - CLR, FRONT - RECESS, cx + CASE_W / 2 + CLR, cy + CASE_H / 2 + CLR, FRONT + 1)
    b -= rbox(win_cx, win_cy, WIN_W, WIN_H, -1, FRONT + 1, r=2.5)
    # repisa bajo la carcasa (soporta el peso) y topes laterales
    ledge_y = cy - CASE_H / 2 - CLR
    b += box(cx - CASE_W / 2 + 10, ledge_y - 3, FRONT, cx + CASE_W / 2 - 10, ledge_y, FRONT + CASE_D - 6)
    for s in (-1, 1):
        x = cx + s * (CASE_W / 2 + CLR)
        x0, x1 = (x, x + 3) if s > 0 else (x - 3, x)
        b += box(x0, cy - 15, FRONT, x1, cy + 15, FRONT + 12)
    # techo: agujero trípode 1/4" y ranura para el cable de la cámara
    b -= cyl_y(cx, TRIPOD_Z, TRIPOD, H - WALL - 1, H + 1)
    sw, sd = CABLE_SLOT
    b -= box(cx - sw / 2, H - WALL - 1, D - 8 - sd, cx + sw / 2, H + 1, D - 8)
    # rejillas laterales a la altura de la Pi
    for s in (0, 1):
        x0 = -1 if s == 0 else W - WALL - 1
        for i in range(6):
            y = cy - 25 + i * 10
            b -= box(x0, y, FRONT + 12, x0 + WALL + 2, y + 4, D - 12)
    # rejillas en la base (entrada de aire)
    for i in range(5):
        x = cx - 40 + i * 20
        b -= box(x - 2, -1, 18, x + 2, WALL + 1, D - 18)
    if FUNDA_INTEGRADA:
        b += funda()
    return b

def tapa():
    # La tapa se modela en su propio sistema: placa en Z 0..BACK_T, marco hacia +Z
    p = box(0, 0, 0, W, H, BACK_T)
    for (x, y) in col_pos:
        p -= cyl_z(x + COL / 2, y + COL / 2, SCREW, -1, BACK_T + 1)
        p -= cyl_z(x + COL / 2, y + COL / 2, 6.2, BACK_T - 1.2, BACK_T + 1)  # avellanado simple
    # rejilla detrás de la carcasa
    for i in range(7):
        y = cy - 27 + i * 9
        p -= rbox(cx, y + 2, 70, 4.5, -1, BACK_T + 1, r=2)
    # salida de cables abajo (en forma de U abierta al borde)
    ew, eh = EXIT
    p -= rbox(cx, eh / 2 - 6, ew, eh + 12, -1, BACK_T + 1, r=5)
    # marco empujador (aprieta la carcasa contra el frontal); hueco central para el aire
    L = D - case_back_z - PUSH_GAP
    fw, fh, ft = CASE_W - 14, CASE_H - 14, 2.5
    frame = rbox(cx, cy, fw, fh, BACK_T, BACK_T + L, r=4) - rbox(cx, cy, fw - 2 * ft, fh - 2 * ft, BACK_T - 1, BACK_T + L + 1, r=2)
    # ventanas en el marco para que circule el aire por los lados
    frame -= box(cx - fw / 2 - 1, cy - 8, BACK_T + 6, cx + fw / 2 + 1, cy + 8, BACK_T + L - 6)
    p += frame
    return p, L

def funda(full=True):
    # Funda abierta por arriba pegada al lateral derecho (x = W). Todas las paredes van a lo largo de Z: sin voladizos al imprimir.
    iw, it = MANDO_W + MANDO_CLR, MANDO_T + MANDO_CLR_T
    zc = D / 2
    x0, x1 = W - 0.01, W + it + FUNDA_PARED
    z0, z1 = zc - iw / 2 - FUNDA_PARED, zc + iw / 2 + FUNDA_PARED
    y0, y1 = MANDO_Y0 - FUNDA_PARED, MANDO_Y0 + MANDO_PROF
    f = box(x0, y0, z0, x1, y1, z1) - box(W, MANDO_Y0, zc - iw / 2, W + it, y1 + 1, zc + iw / 2)
    # muesca para el dedo en la pared exterior
    f -= box(W + it - 1, y1 - 12, zc - 7, x1 + 1, y1 + 1, zc + 7)
    # orejeta con agujero para el cordón debajo de la funda (agujero a lo largo de Z)
    ear = box(x0, y0 - 12, zc - 6, W + 9, y0, zc + 6) - cyl_z(W + 5, y0 - 6, CORDON, zc - 7, zc + 7)
    return f + ear

def funda_suelta():
    # Funda + placa de pegado. Se imprime con la placa sobre la cama: la placa queda en Z 0..PLACA_T.
    zc = D / 2
    iw = MANDO_W + MANDO_CLR
    y0 = MANDO_Y0 - FUNDA_PARED - 12          # incluye la orejeta del cordón
    y1 = MANDO_Y0 + MANDO_PROF
    plate = rbox((y0 + y1) / 2, zc, (y1 - y0) + 8, iw + 2 * FUNDA_PARED + 12, 0, PLACA_T, r=4)
    # plate se ha creado en coordenadas (Y, Z) -> lo paso al sistema de la funda
    plate = plate.rotate([0, 0, 0])
    f = funda().translate([-W + PLACA_T - 0.01, 0, 0])   # la funda empieza en x = PLACA_T
    # rbox trabaja en XY; reconstruyo la placa en el plano YZ con grosor en X
    pw, ph = (y1 - y0) + 8, iw + 2 * FUNDA_PARED + 12
    sq = CrossSection.square([pw - 8, ph - 8], center=True).offset(4, join_type=JoinType.Round, circular_segments=24)
    placa = Manifold.extrude(sq, PLACA_T).rotate([0, 90, 0])     # extruye a lo largo de X
    placa = placa.translate([PLACA_T, (y0 + y1) / 2, zc])
    # tras rotate([0,90,0]) la sección queda en el plano (Z,Y): ajusto por si acaso con la bbox
    m = placa + f
    m = m.rotate([0, -90, 0])                  # X -> Z: la placa sobre la cama
    bb = m.bounding_box()
    return m.translate([-bb[0], -bb[1], -bb[2]])

def prueba():
    # Trozo del frontal con ventana, rebaje y repisa: comprobar encaje de la carcasa
    m = 8
    x0, x1 = cx - CASE_W / 2 - m, cx + CASE_W / 2 + m
    y0, y1 = cy - CASE_H / 2 - m - 3, cy + CASE_H / 2 + m
    b = box(x0, y0, 0, x1, y1, FRONT)
    b -= box(cx - CASE_W / 2 - CLR, cy - CASE_H / 2 - CLR, FRONT - RECESS, cx + CASE_W / 2 + CLR, cy + CASE_H / 2 + CLR, FRONT + 1)
    b -= rbox(win_cx, win_cy, WIN_W, WIN_H, -1, FRONT + 1, r=2.5)
    ledge_y = cy - CASE_H / 2 - CLR
    b += box(cx - CASE_W / 2 + 10, ledge_y - 3, FRONT, cx + CASE_W / 2 - 10, ledge_y, FRONT + 10)
    return b.translate([-x0, -y0, 0])

def to_trimesh(m):
    mesh = m.to_mesh()
    return trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties)[:, :3], faces=np.asarray(mesh.tri_verts), process=True)

if __name__ == "__main__":
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    c = cuerpo()
    t, L = tapa()
    pr = prueba()
    pf = funda().translate([-W, 0, 0]) + box(-3, MANDO_Y0 - FUNDA_PARED - 12, D / 2 - MANDO_W / 2 - 6, 0.01, MANDO_Y0 + MANDO_PROF, D / 2 + MANDO_W / 2 + 6)
    for name, m in [("cuerpo", c), ("tapa_trasera", t), ("prueba_encaje", pr), ("prueba_funda_mando", pf), ("funda_mando", funda_suelta())]:
        tm = to_trimesh(m)
        tm.export(out / f"{name}.stl")
        print(f"{name}: watertight={tm.is_watertight} vol={tm.volume/1000:.1f} cm3 bbox={np.round(tm.extents,1)}")
    print(f"empujador L={L:.1f} mm, centro carcasa y={cy:.1f}, techo y={H}")
