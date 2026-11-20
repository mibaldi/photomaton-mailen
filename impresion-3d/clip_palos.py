"""Clip para guardar el palito del botón y el lápiz de la pantalla táctil, pegado al lateral de la caja.
Se imprime con la placa sobre la cama; una vez pegado, las fundas quedan verticales con la boca arriba (y = LARGO)."""
from manifold3d import Manifold, CrossSection, JoinType
import numpy as np, trimesh

PLACA_T = 2.5
PARED = 1.6
LARGO = 30.0          # largo de las fundas
PALO_IN = 4.2         # hueco cuadrado para la varilla de 3,2 mm (la cabeza 14x10 hace de tope arriba)
LAPIZ_D = 6.6         # hueco redondo para el lápiz de 5-6 mm
FONDO = 1.6           # fondo cerrado de la funda del lápiz
SEP = 4.0

po = PALO_IN + 2 * PARED
lo = LAPIZ_D + 2 * PARED
ancho = 4 + po + SEP + lo + 4
alto = LARGO + 4

sq = CrossSection.square([ancho - 8, alto - 8], center=True).offset(4, join_type=JoinType.Round, circular_segments=24)
placa = Manifold.extrude(sq, PLACA_T).translate([ancho / 2, alto / 2 - 2, 0])

# funda cuadrada del palito (abierta por los dos extremos)
x0 = 4
palo = Manifold.cube([po, LARGO, po]).translate([x0, 0, PLACA_T - 0.01])
palo -= Manifold.cube([PALO_IN, LARGO + 2, PALO_IN]).translate([x0 + PARED, -1, PLACA_T + PARED - 0.01])

# funda redonda del lápiz (fondo cerrado en y = 0, boca en y = LARGO)
xc = x0 + po + SEP + lo / 2
zc = PLACA_T + lo / 2 - 0.01
tubo = Manifold.cylinder(LARGO, lo / 2, circular_segments=64).rotate([-90, 0, 0])
tubo += Manifold.cube([lo, LARGO, lo / 2]).translate([-lo / 2, 0, -lo / 2])   # base plana unida a la placa
hueco = Manifold.cylinder(LARGO, LAPIZ_D / 2, circular_segments=64).rotate([-90, 0, 0]).translate([0, FONDO, 0])
agujero = Manifold.cylinder(FONDO + 2, 1.5, circular_segments=24).rotate([-90, 0, 0]).translate([0, -1, 0])
tubo = (tubo - hueco - agujero).translate([xc, 0, zc])

m = placa + palo + tubo
mesh = m.to_mesh()
t = trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts))
t.export("clip_palos.stl")
print("clip_palos.stl", t.is_watertight, np.round(t.extents, 1))
t.apply_translation(-t.bounds[0])
