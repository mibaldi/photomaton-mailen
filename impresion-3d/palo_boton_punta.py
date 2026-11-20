"""Palitos con punta fina (pin de ~2 mm) para entrar en el agujerito de la carcasa y pulsar el pulsador original.
Varilla 3,2 mm (pasa por la rejilla de 4 mm) + pin redondo en el extremo + cabeza tope con muescas (1-4)."""
from manifold3d import Manifold
import numpy as np, trimesh

VARILLA = 3.2
LARGOS = [40.0, 45.0, 50.0, 55.0]   # largo de la varilla (sin contar el pin)
PIN_D = 2.0                        # diámetro de la punta (el agujero de la carcasa ronda 2,5-3 mm)
PIN_L = 5.0                        # lo que entra la punta en el agujero
CABEZA = (14.0, 10.0, 4.0)

def palo(L, n):
    hx, hy, hz = CABEZA
    m = Manifold.cube([hx, hy, hz]).translate([-hx, -hy / 2, 0])
    m += Manifold.cube([L, VARILLA, VARILLA]).translate([0, -VARILLA / 2, 0])
    # pin redondo a lo largo de X, centrado en la varilla, con la base recortada para que apoye en la cama
    pin = Manifold.cylinder(PIN_L, PIN_D / 2, circular_segments=32).rotate([0, 90, 0])
    pin = pin.translate([L - 0.01, 0, VARILLA / 2])
    pin -= Manifold.cube([PIN_L + 2, 4, 2]).translate([L - 1, -2, VARILLA / 2 - PIN_D / 2 + 0.2 - 2])
    # pequeño cono de transición varilla -> pin para que no se parta
    cono = Manifold.cylinder(1.5, VARILLA / 2, PIN_D / 2, circular_segments=32).rotate([0, 90, 0]).translate([L - 0.01, 0, VARILLA / 2])
    cono -= Manifold.cube([3, 4, 2]).translate([L - 1, -2, -2 + 0.0001])
    m += pin + cono
    for i in range(n):
        m -= Manifold.cube([1.2, 2.5, hz + 1]).translate([-hx + 2 + i * 2.6, hy / 2 - 2, -0.5])
    return m

placa = Manifold()
for i, L in enumerate(LARGOS):
    placa += palo(L, i + 1).translate([0, i * (CABEZA[1] + 4), 0])
mesh = placa.to_mesh()
t = trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts))
t.export("palos_boton_punta.stl")
print("palos_boton_punta.stl", t.is_watertight, np.round(t.extents, 1), "zmin", round(t.bounds[0][2], 2))
