"""Genera los marcos del photomatón (1280x720, PNG con el hueco central transparente). Sin textos abajo.
  python generar_marcos.py [foto_de_ejemplo.jpg]   -> marcos/*.png, miniaturas/*.jpg y muestras.jpg"""
import math, random, sys, json, os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, S = 1280, 720, 2
w, h = W * S, H * S
FUENTE = "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"
COLS = ["#ff4d6d", "#ffb703", "#3a86ff", "#06d6a0", "#8338ec", "#fb5607", "#ff006e"]


def lienzo():
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def hueco(d, banda, radio, color, linea=None):
    d.rectangle([0, 0, w, h], fill=color)
    d.rounded_rectangle([banda, banda, w - banda, h - banda], radius=radio, fill=(0, 0, 0, 0))
    if linea:
        d.rounded_rectangle([banda, banda, w - banda, h - banda], radius=radio, outline=linea[0], width=linea[1])


def confeti(d, banda, n, cols, seed):
    rnd = random.Random(seed)
    for _ in range(n):
        x, y = rnd.uniform(0, w), rnd.uniform(0, h)
        if banda + 12 * S < x < w - banda - 12 * S and banda + 12 * S < y < h - banda - 12 * S:
            continue
        c = rnd.choice(cols)
        r = rnd.uniform(3, 7) * S
        if rnd.random() < .5:
            d.ellipse([x - r, y - r, x + r, y + r], fill=c)
        else:
            a = rnd.uniform(0, math.pi)
            dx, dy = math.cos(a) * r * 1.8, math.sin(a) * r * 1.8
            d.line([x - dx, y - dy, x + dx, y + dy], fill=c, width=3 * S)


def globo(d, cx, cy, rx, ry, col, rnd):
    d.line([(cx, cy + ry), (cx + rnd.uniform(-25, 25) * S, cy + ry + 150 * S)], fill="#555555", width=2 * S)
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=col)
    d.polygon([(cx - 9 * S, cy + ry + 12 * S), (cx + 9 * S, cy + ry + 12 * S), (cx, cy + ry - 6 * S)], fill=col)
    d.ellipse([cx - rx * .5, cy - ry * .65, cx - rx * .15, cy - ry * .2], fill=(255, 255, 255, 110))


def estrella(d, cx, cy, r, col, puntas=5, interior=.45):
    pts = []
    for i in range(puntas * 2):
        a = -math.pi / 2 + i * math.pi / puntas
        rr = r if i % 2 == 0 else r * interior
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=col)


def brillo(d, cx, cy, r, col):
    estrella(d, cx, cy, r, col, puntas=4, interior=.22)


def corazon(d, cx, cy, r, col):
    pts = []
    for i in range(80):
        t = i / 80 * 2 * math.pi
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * r / 16, cy - y * r / 16))
    d.polygon(pts, fill=col)


# ---------- 1. Mailen: banderines con su nombre, globos y confeti ----------
def marco_mailen():
    im = lienzo(); d = ImageDraw.Draw(im)
    banda = 26 * S
    hueco(d, banda, 40 * S, "#ff4d6d", ("white", 5 * S))
    confeti(d, banda, 500, COLS[1:] + ["#ffffff"], 7)
    letras = "MAILEN"
    fuente = ImageFont.truetype(FUENTE, 34 * S)
    n = 18
    pts = [(-10 * S + (w + 20 * S) * i / n, 14 * S + 60 * S * 4 * (i / n) * (1 - i / n)) for i in range(n + 1)]
    d.line(pts, fill="#444444", width=3 * S)
    ini = (n - len(letras)) // 2
    for i in range(n):
        (ax, ay), (bx, by) = pts[i], pts[i + 1]
        mx, my = (ax + bx) / 2, (ay + by) / 2
        d.polygon([(ax + 4 * S, ay), (bx - 4 * S, by), (mx, my + 70 * S)], fill=COLS[i % len(COLS)], outline="white")
        if ini <= i < ini + len(letras):
            d.text((mx, my + 24 * S), letras[i - ini], font=fuente, fill="white", anchor="mm",
                   stroke_width=2 * S, stroke_fill=(0, 0, 0, 60))
    rnd = random.Random(3)
    for (cx, cy, col) in [(70, 540, "#3a86ff"), (135, 595, "#ffb703"), (55, 660, "#ff006e"),
                          (1210, 540, "#06d6a0"), (1145, 595, "#8338ec"), (1225, 660, "#fb5607")]:
        globo(d, cx * S, cy * S, 42 * S, 52 * S, col, rnd)
    return im


# ---------- 2. Confeti: genérico de fiesta ----------
def marco_confeti():
    im = lienzo(); d = ImageDraw.Draw(im)
    banda = 34 * S
    hueco(d, banda, 30 * S, "#ffffff", ("#ffd1dc", 6 * S))
    confeti(d, banda, 1100, COLS, 11)
    rnd = random.Random(5)
    for _ in range(40):
        x, y = rnd.uniform(0, w), rnd.uniform(0, h)
        if banda < x < w - banda and banda < y < h - banda:
            continue
        estrella(d, x, y, rnd.uniform(7, 13) * S, rnd.choice(COLS))
    return im


# ---------- 3. Polaroid: borde blanco grueso ----------
def marco_polaroid():
    im = lienzo(); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w, h], fill="#fbfaf7")
    lat, arriba, abajo = 46 * S, 46 * S, 46 * S
    d.rectangle([lat, arriba, w - lat, h - abajo], fill=(0, 0, 0, 0))
    sombra = lienzo()
    ImageDraw.Draw(sombra).rectangle([lat, arriba, w - lat, h - abajo], outline=(0, 0, 0, 70), width=4 * S)
    im = Image.alpha_composite(im, sombra.filter(ImageFilter.GaussianBlur(3 * S)))
    d = ImageDraw.Draw(im)
    d.rectangle([lat, arriba, w - lat, h - abajo], fill=(0, 0, 0, 0))
    # cinta adhesiva arriba
    for cx, ang in ((w * .18, -8), (w * .82, 7)):
        cinta = Image.new("RGBA", (220 * S, 54 * S), (255, 236, 160, 190))
        cinta = cinta.rotate(ang, expand=True, resample=Image.BICUBIC)
        im.alpha_composite(cinta, (int(cx - cinta.width / 2), int(arriba - cinta.height / 2)))
    return im


# ---------- 4. Película: tira de cine con perforaciones ----------
def marco_pelicula():
    im = lienzo(); d = ImageDraw.Draw(im)
    banda_v, lat = 70 * S, 18 * S
    d.rectangle([0, 0, w, h], fill="#141414")
    d.rounded_rectangle([lat, banda_v, w - lat, h - banda_v], radius=10 * S, fill=(0, 0, 0, 0))
    paso, ancho, alto = 64 * S, 34 * S, 26 * S
    for y in (banda_v / 2, h - banda_v / 2):
        x = paso / 2
        while x < w:
            d.rounded_rectangle([x - ancho / 2, y - alto / 2, x + ancho / 2, y + alto / 2], radius=6 * S, fill="#f2efe6")
            x += paso
    return im


# ---------- 5. Neón: borde oscuro con tubos de luz ----------
def marco_neon():
    base = lienzo(); d = ImageDraw.Draw(base)
    banda = 40 * S
    hueco(d, banda, 34 * S, "#120a1f")
    luz = lienzo(); dl = ImageDraw.Draw(luz)
    m = banda - 14 * S
    dl.rounded_rectangle([m, m, w - m, h - m], radius=40 * S, outline="#ff2bd6", width=7 * S)
    m2 = 12 * S
    dl.rounded_rectangle([m2, m2, w - m2, h - m2], radius=30 * S, outline="#2be4ff", width=5 * S)
    for cx, cy in ((w - 95 * S, 80 * S), (95 * S, h - 80 * S)):
        estrella(dl, cx, cy, 42 * S, "#ffe62b")
    for cx, cy in ((95 * S, 80 * S), (w - 95 * S, h - 80 * S)):
        corazon(dl, cx, cy, 36 * S, "#ff2bd6")
    halo = luz.filter(ImageFilter.GaussianBlur(10 * S))
    im = Image.alpha_composite(base, halo)
    im = Image.alpha_composite(im, halo)
    im = Image.alpha_composite(im, luz)
    blanco = lienzo(); ImageDraw.Draw(blanco).rounded_rectangle([m, m, w - m, h - m], radius=40 * S, outline=(255, 255, 255, 170), width=2 * S)
    return Image.alpha_composite(im, blanco)


# ---------- 6. Dorado: glam con destellos ----------
def marco_dorado():
    im = lienzo(); d = ImageDraw.Draw(im)
    banda = 36 * S
    grad = Image.new("RGBA", (w, h))
    gd = ImageDraw.Draw(grad)
    for x in range(0, w, 2):
        t = (math.sin(x / w * math.pi * 6) + 1) / 2
        c = tuple(int(a + (b - a) * t) for a, b in zip((176, 128, 40), (255, 222, 130)))
        gd.line([(x, 0), (x, h)], fill=c + (255,), width=2)
    mascara = Image.new("L", (w, h), 255)
    ImageDraw.Draw(mascara).rounded_rectangle([banda, banda, w - banda, h - banda], radius=24 * S, fill=0)
    im.paste(grad, (0, 0), mascara)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([banda, banda, w - banda, h - banda], radius=24 * S, outline="#fff4c9", width=3 * S)
    d.rounded_rectangle([10 * S, 10 * S, w - 10 * S, h - 10 * S], radius=30 * S, outline="#8a5a14", width=3 * S)
    rnd = random.Random(9)
    for cx, cy, r in [(banda, banda, 46), (w - banda, banda, 46), (banda, h - banda, 46), (w - banda, h - banda, 46)]:
        brillo(d, cx, cy, r * S, "#ffffff")
    for _ in range(26):
        x, y = rnd.uniform(0, w), rnd.uniform(0, h)
        if banda < x < w - banda and banda < y < h - banda:
            continue
        brillo(d, x, y, rnd.uniform(8, 16) * S, "#fffbe6")
    return im


MARCOS = [("mailen", "Mailen", marco_mailen), ("confeti", "Confeti", marco_confeti), ("polaroid", "Polaroid", marco_polaroid),
          ("pelicula", "Película", marco_pelicula), ("neon", "Neón", marco_neon), ("dorado", "Dorado", marco_dorado)]

if __name__ == "__main__":
    base = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(os.path.join(base, "png"), exist_ok=True)
    os.makedirs(os.path.join(base, "miniaturas"), exist_ok=True)
    ejemplo = Image.open(sys.argv[1]).convert("RGBA").resize((W, H)) if len(sys.argv) > 1 else Image.new("RGBA", (W, H), "#9bb7d4")
    muestras = []
    for clave, nombre, fn in MARCOS:
        m = fn().resize((W, H), Image.LANCZOS)
        m.save(os.path.join(base, "png", f"{clave}.png"))
        comp = Image.alpha_composite(ejemplo, m).convert("RGB")
        comp.resize((320, 180), Image.LANCZOS).save(os.path.join(base, "miniaturas", f"{clave}.jpg"), quality=80)
        muestras.append(comp.resize((640, 360), Image.LANCZOS))
    json.dump([{"clave": c, "nombre": n, "archivo": f"{c}.png"} for c, n, _ in MARCOS],
              open(os.path.join(base, "marcos.json"), "w"), ensure_ascii=False, indent=1)
    hoja = Image.new("RGB", (1280, 360 * 3), "white")
    for i, m in enumerate(muestras):
        hoja.paste(m, ((i % 2) * 640, (i // 2) * 360))
    hoja.save(os.path.join(base, "muestras.jpg"), quality=85)
    print("ok", len(MARCOS), "marcos")
