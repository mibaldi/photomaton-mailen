"""Soportes para dejar los cables enganchados en la tapa trasera de la caja (se pegan, como clip_palos).

- gancho_cable.stl  (imprimir 2): ganchos para enrollar el cable sobrante. Se pegan uno encima del otro
  (~10-12 cm de separación), el de arriba con la pestaña hacia arriba y el de abajo hacia abajo, y el cable
  se enrolla alrededor de los dos.
- clip_cables.stl   (imprimir 2): clip doble a presión para el cable de corriente USB-C (trenzado, más gordo)
  y el alargador USB de la impresora: sujeta las puntas para que no cuelguen.
- prueba_clips.stl: tira de clips de 3,5 a 5,5 mm (las muescas indican cuál es: 1 muesca = 3,5 mm, 2 = 4 mm…)
  para saber qué medida agarra bien cada cable antes de imprimir los clips definitivos.

Todo se imprime con la placa sobre la cama y sin soportes (las pestañas tienen chaflán a 45°).
Pegar con cinta de doble cara gruesa (tipo VHB) o pegamento de contacto sobre la tapa (PLA)."""
from manifold3d import Manifold, CrossSection, JoinType
import numpy as np, trimesh, sys, os

OUT = sys.argv[1] if len(sys.argv) > 1 else "."

PLACA_T = 2.5          # grosor de la placa que se pega
RADIO = 3.0            # redondeo de las placas

# --- gancho ---
G_ANCHO = 16.0         # ancho del gancho (a lo largo del cable)
G_POSTE = 6.0          # grosor del brazo
G_SALIENTE = 28.0      # cuánto sobresale de la tapa: caben ~4 vueltas de cable de 4-5 mm
G_PESTANA = 6.0        # pestaña que impide que el cable se salga
G_PESTANA_T = 3.0

# --- clips --- (diámetro del cable + 0,3 de holgura; boca al 72 % del cable para que entre a presión)
CABLE_USBC = 4.5       # cable de corriente trenzado (medir con calibre y ajustar)
CABLE_USBA = 3.8       # alargador USB de la impresora
C_ANCHO = 9.0          # ancho del clip
C_PARED = 1.6
C_BOCA = 0.72


def placa(ancho, alto):
    cs = CrossSection.square([ancho - 2 * RADIO, alto - 2 * RADIO], center=True).offset(
        RADIO, join_type=JoinType.Round, circular_segments=24)
    return Manifold.extrude(cs, PLACA_T)


def gancho():
    pl_x, pl_y = G_POSTE + G_PESTANA + 10, G_ANCHO + 10
    m = placa(pl_x, pl_y).translate([0, 0, 0])
    x0 = -pl_x / 2 + 5                                   # el brazo sale cerca de un borde de la placa
    brazo = Manifold.cube([G_POSTE, G_ANCHO, G_SALIENTE]).translate([x0, -G_ANCHO / 2, PLACA_T - 0.01])
    # pestaña al final del brazo, hacia +X, con chaflán de 45° por debajo (imprimible sin soportes)
    z1 = PLACA_T + G_SALIENTE
    perfil = CrossSection([[(0, 0), (G_PESTANA, G_PESTANA), (G_PESTANA, G_PESTANA + G_PESTANA_T),
                            (0, G_PESTANA + G_PESTANA_T)]])
    pest = Manifold.extrude(perfil, G_ANCHO).rotate([90, 0, 0]).translate(
        [x0 + G_POSTE - 0.01, G_ANCHO / 2, z1 - G_PESTANA - G_PESTANA_T])
    # refuerzo en la base del brazo
    cart = CrossSection([[(0, 0), (5, 0), (0, 5)]])
    refuerzo = Manifold.extrude(cart, G_ANCHO).rotate([90, 0, 0]).translate([x0 + G_POSTE - 0.01, G_ANCHO / 2, PLACA_T - 0.01])
    refuerzo2 = Manifold.extrude(cart, G_ANCHO).rotate([90, 0, 0]).rotate([0, 0, 180]).translate([x0 + 0.01, -G_ANCHO / 2, PLACA_T - 0.01])
    return m + brazo + pest + refuerzo + refuerzo2


def anillo(d_cable, ancho=C_ANCHO):
    """C abierta hacia arriba (+Z), eje a lo largo de Y, apoyada en la placa."""
    ri = (d_cable + 0.3) / 2
    ro = ri + C_PARED
    zc = PLACA_T + ro - 0.4
    ext = Manifold.cylinder(ancho, ro, circular_segments=64).rotate([-90, 0, 0])
    ext += Manifold.cube([2 * ro, ancho, ro]).translate([-ro, 0, -ro])          # base plana unida a la placa
    hueco = Manifold.cylinder(ancho + 2, ri, circular_segments=64).rotate([-90, 0, 0]).translate([0, -1, 0])
    boca = C_BOCA * d_cable
    corte = Manifold.cube([boca, ancho + 2, ro + 1]).translate([-boca / 2, -1, 0])
    # entrada en V para que el cable entre fácil
    v = CrossSection([[(-boca / 2, 0), (boca / 2, 0), (boca / 2 + 1.6, ro + 1), (-boca / 2 - 1.6, ro + 1)]])
    v = Manifold.extrude(v, ancho + 2).rotate([90, 0, 0]).translate([0, ancho + 1, ri * 0.55])
    c = (ext - hueco - corte - v).translate([0, -ancho / 2, zc])
    return c, ro


def clip_doble():
    a, ra = anillo(CABLE_USBC)
    b, rb = anillo(CABLE_USBA)
    sep = 3.0
    xa, xb = 0.0, ra + sep + rb                 # centros de los dos anillos
    izq, der = xa - ra - 4, xb + rb + 4
    m = placa(der - izq, C_ANCHO + 8).translate([(izq + der) / 2, 0, 0])
    return m + a.translate([xa, 0, 0]) + b.translate([xb, 0, 0])


def prueba():
    medidas = [3.5, 4.0, 4.5, 5.0, 5.5]
    anillos, centros, x = [], [], 2.0
    for d in medidas:
        c, r = anillo(d, ancho=7)
        cx = x + r
        anillos.append(c.translate([cx, 0, 0])); centros.append(cx)
        x = cx + r + 2.5
    alto = 15.0
    m = placa(x + 0.5, alto).translate([(x + 0.5) / 2, 0, 0])
    for c in anillos:
        m += c
    # muescas en el borde de la placa delante de cada anillo: 1 muesca = 3,5 mm, 2 = 4 mm, … 5 = 5,5 mm
    for i, cx in enumerate(centros):
        n = i + 1
        for k in range(n):
            mx = cx - (n - 1) + 2.0 * k
            m -= Manifold.cube([1.0, 2.0, PLACA_T + 1]).translate([mx - 0.5, -alto / 2 - 0.01, -0.5])
    return m


def guardar(m, nombre):
    mesh = m.to_mesh()
    t = trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts))
    t.apply_translation([-t.bounds[0][0], -t.bounds[0][1], -t.bounds[0][2]])
    ruta = os.path.join(OUT, nombre)
    t.export(ruta)
    print(nombre, "estanco" if t.is_watertight else "NO ESTANCO", np.round(t.extents, 1), "mm")
    return t


if __name__ == "__main__":
    guardar(gancho(), "gancho_cable.stl")
    guardar(clip_doble(), "clip_cables.stl")
    guardar(prueba(), "prueba_clips.stl")
