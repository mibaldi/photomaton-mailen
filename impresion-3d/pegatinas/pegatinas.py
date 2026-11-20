"""Hoja A4 de pegatinas para decorar la caja del photomatón (imprimir al 100 % y recortar por la línea discontinua)."""
import math, random
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

DPI = 300
MM = DPI / 25.4
A4 = (round(210 * MM), round(297 * MM))
FONT = "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"
ROSA, ROSA2, AMAR, AZUL, VERDE, LILA, NARAN, BLANCO, OSC = (
    "#e8457a", "#c92e62", "#ffc93c", "#3fa7f5", "#2ec4a0", "#9b5de5", "#ff8c42", "#ffffff", "#2b1d24")
COLORES = [ROSA, AMAR, AZUL, VERDE, LILA, NARAN]
random.seed(7)


def mm(v):
    return round(v * MM)


def font(px):
    return ImageFont.truetype(FONT, px)


def lienzo(w, h):
    return Image.new("RGBA", (mm(w), mm(h)), (0, 0, 0, 0))


def acabar(img, borde=2.2):
    """Añade borde blanco (zona de corte segura) y línea de corte discontinua alrededor."""
    pad = mm(borde) + 12
    big = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
    big.alpha_composite(img, (pad, pad))
    a = big.getchannel("A").point(lambda v: 255 if v > 20 else 0)
    # dilatación rápida: reducir, MaxFilter, ampliar
    k = 4
    small = a.resize((a.width // k, a.height // k), Image.BILINEAR).point(lambda v: 255 if v > 0 else 0)
    r = max(3, (mm(borde) // k) * 2 + 1)
    dil = small.filter(ImageFilter.MaxFilter(r)).resize(a.size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(2))
    dil = dil.point(lambda v: 255 if v > 128 else 0)
    fondo = Image.new("RGBA", big.size, (255, 255, 255, 0))
    fondo.putalpha(dil)
    blanco = Image.new("RGBA", big.size, BLANCO)
    blanco.putalpha(dil)
    out = Image.new("RGBA", big.size, (0, 0, 0, 0))
    out.alpha_composite(blanco)
    out.alpha_composite(big)
    # contorno de corte
    edge = ImageChops.subtract(dil.filter(ImageFilter.MaxFilter(5)), dil)
    # discontinua: enmascarar con rayas diagonales
    rayas = Image.new("L", big.size, 0)
    dr = ImageDraw.Draw(rayas)
    for x in range(-big.height, big.width, 28):
        dr.line([(x, 0), (x + big.height, big.height)], fill=255, width=16)
    edge = ImageChops.multiply(edge, rayas)
    linea = Image.new("RGBA", big.size, (120, 120, 120, 255))
    linea.putalpha(edge)
    out.alpha_composite(linea)
    return out


def texto_centrado(d, caja, txt, px, fill, stroke=0, stroke_fill=None):
    f = font(px)
    x0, y0, x1, y1 = caja
    bb = d.textbbox((0, 0), txt, font=f, stroke_width=stroke)
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    d.text(((x0 + x1 - w) / 2 - bb[0], (y0 + y1 - h) / 2 - bb[1]), txt, font=f, fill=fill,
           stroke_width=stroke, stroke_fill=stroke_fill)


# ---------- dibujos ----------
def cartel(txt, w, h, color=ROSA, px=None, txtcol=BLANCO):
    im = lienzo(w, h); d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius=mm(h / 2.6), fill=color)
    d.rounded_rectangle([mm(1.5), mm(1.5), im.width - mm(1.5), im.height - mm(1.5)], radius=mm(h / 3), outline=BLANCO, width=mm(0.8))
    texto_centrado(d, (0, 0, im.width, im.height), txt, px or mm(h * 0.45), txtcol)
    return im


def globo(color, w=26, h=42):
    im = lienzo(w, h); d = ImageDraw.Draw(im)
    bw, bh = im.width, int(im.height * 0.72)
    d.ellipse([0, 0, bw - 1, bh], fill=color)
    d.ellipse([bw * 0.2, bh * 0.12, bw * 0.38, bh * 0.38], fill=(255, 255, 255, 140))
    cx = bw // 2
    d.polygon([(cx - mm(2), bh - mm(0.5)), (cx + mm(2), bh - mm(0.5)), (cx, bh + mm(2.5))], fill=color)
    pts = [(cx + math.sin(t / 6) * mm(2), bh + mm(2.5) + t * (im.height - bh - mm(3)) / 40) for t in range(41)]
    d.line(pts, fill=OSC, width=mm(0.6))
    return im


def estrella(color, s=22):
    im = lienzo(s, s); d = ImageDraw.Draw(im)
    c, R, r = im.width / 2, im.width / 2 - 2, im.width / 4.6
    pts = [(c + (R if i % 2 == 0 else r) * math.sin(i * math.pi / 5), c - (R if i % 2 == 0 else r) * math.cos(i * math.pi / 5)) for i in range(10)]
    d.polygon(pts, fill=color)
    return im


def banderines(w=170, h=24, n=9):
    im = lienzo(w, h); d = ImageDraw.Draw(im)
    W, H = im.width, im.height
    curva = lambda x: mm(2) + math.sin(x / W * math.pi) * mm(3)
    d.line([(x, curva(x)) for x in range(0, W, 10)] + [(W - 1, curva(W - 1))], fill=OSC, width=mm(0.7))
    paso = W / n
    for i in range(n):
        x0, x1 = i * paso + mm(1.5), (i + 1) * paso - mm(1.5)
        xm = (x0 + x1) / 2
        d.polygon([(x0, curva(x0)), (x1, curva(x1)), (xm, H - mm(1))], fill=COLORES[i % len(COLORES)])
    return im


def tarta(w=44, h=44):
    im = lienzo(w, h); d = ImageDraw.Draw(im); W, H = im.width, im.height
    d.rounded_rectangle([mm(3), H * 0.45, W - mm(3), H - mm(2)], radius=mm(3), fill="#f7c6d9")
    d.rounded_rectangle([mm(3), H * 0.45, W - mm(3), H * 0.58], radius=mm(3), fill=ROSA)
    for i in range(6):
        x = mm(6) + i * (W - mm(12)) / 5
        d.ellipse([x - mm(1.6), H * 0.55, x + mm(1.6), H * 0.55 + mm(4)], fill=ROSA)
    d.rectangle([mm(1), H - mm(3), W - mm(1), H - mm(1)], fill="#d9d9d9")
    for i, c in enumerate([AZUL, AMAR, VERDE]):
        x = W * (0.3 + 0.2 * i)
        d.rectangle([x - mm(1.2), H * 0.26, x + mm(1.2), H * 0.45], fill=c)
        d.ellipse([x - mm(1.8), H * 0.12, x + mm(1.8), H * 0.25], fill=NARAN)
        d.ellipse([x - mm(0.9), H * 0.16, x + mm(0.9), H * 0.24], fill=AMAR)
    for _ in range(14):
        x, y = random.uniform(mm(6), W - mm(6)), random.uniform(H * 0.62, H - mm(5))
        d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=random.choice(COLORES))
    return im


def regalo(color=AZUL, lazo=AMAR, s=34):
    im = lienzo(s, s); d = ImageDraw.Draw(im); W = im.width
    d.rectangle([mm(2), W * 0.38, W - mm(2), W - mm(1)], fill=color)
    d.rectangle([mm(1), W * 0.28, W - mm(1), W * 0.42], fill=color)
    d.rectangle([W / 2 - mm(2), W * 0.28, W / 2 + mm(2), W - mm(1)], fill=lazo)
    d.ellipse([W * 0.22, W * 0.05, W / 2, W * 0.32], outline=lazo, width=mm(2))
    d.ellipse([W / 2, W * 0.05, W * 0.78, W * 0.32], outline=lazo, width=mm(2))
    return im


def camara(w=46, h=34, color=OSC):
    im = lienzo(w, h); d = ImageDraw.Draw(im); W, H = im.width, im.height
    d.rounded_rectangle([W * 0.3, 0, W * 0.6, H * 0.25], radius=mm(2), fill=color)
    d.rounded_rectangle([0, H * 0.15, W - 1, H - 1], radius=mm(5), fill=color)
    c = (W / 2, H * 0.58); r = H * 0.3
    d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=BLANCO)
    d.ellipse([c[0] - r * 0.7, c[1] - r * 0.7, c[0] + r * 0.7, c[1] + r * 0.7], fill=ROSA)
    d.ellipse([c[0] - r * 0.3, c[1] - r * 0.45, c[0] - r * 0.05, c[1] - r * 0.2], fill=BLANCO)
    d.ellipse([W * 0.8, H * 0.28, W * 0.9, H * 0.4], fill=AMAR)
    return im


def mira_aqui(w=70, h=40):
    im = lienzo(w, h); d = ImageDraw.Draw(im); W, H = im.width, im.height
    d.polygon([(W / 2, 0), (W / 2 - mm(9), mm(11)), (W / 2 + mm(9), mm(11))], fill=AMAR)
    d.rounded_rectangle([0, mm(10), W - 1, H - 1], radius=mm(8), fill=AMAR)
    texto_centrado(d, (0, mm(10), W, H), "¡Mira aquí!", mm(8.5), OSC)
    return im


def bocadillo(txt, w, h, color=BLANCO, txtcol=ROSA, px=None):
    im = lienzo(w, h); d = ImageDraw.Draw(im); W, H = im.width, im.height
    d.ellipse([0, 0, W - 1, H * 0.85], fill=color, outline=txtcol, width=mm(1.2))
    d.polygon([(W * 0.25, H * 0.7), (W * 0.18, H - 1), (W * 0.42, H * 0.78)], fill=color, outline=txtcol)
    d.line([(W * 0.25, H * 0.72), (W * 0.18, H - 2), (W * 0.42, H * 0.79)], fill=txtcol, width=mm(1.2))
    texto_centrado(d, (0, 0, W, H * 0.85), txt, px or mm(h * 0.28), txtcol)
    return im


def confeti(s=12):
    im = lienzo(s, s); d = ImageDraw.Draw(im); W = im.width
    for _ in range(9):
        x, y, c = random.uniform(mm(1.5), W - mm(1.5)), random.uniform(mm(1.5), W - mm(1.5)), random.choice(COLORES)
        if random.random() < 0.5:
            d.ellipse([x - mm(1.2), y - mm(1.2), x + mm(1.2), y + mm(1.2)], fill=c)
        else:
            d.rectangle([x - mm(1.6), y - mm(0.6), x + mm(1.6), y + mm(0.6)], fill=c)
    return im


def corazon(color=ROSA, s=20):
    im = lienzo(s, s); d = ImageDraw.Draw(im); W = im.width
    d.ellipse([0, 0, W * 0.55, W * 0.55], fill=color)
    d.ellipse([W * 0.45, 0, W - 1, W * 0.55], fill=color)
    d.polygon([(W * 0.03, W * 0.36), (W * 0.97, W * 0.36), (W / 2, W * 0.95)], fill=color)
    return im


# ---------- composición en la hoja ----------
hoja = Image.new("RGBA", A4, BLANCO)
dh = ImageDraw.Draw(hoja)
margen = mm(8)
dh.text((margen, mm(4)), "Pegatinas photomatón - imprimir al 100 % (tamaño real) y recortar por la línea discontinua",
        font=font(mm(3)), fill=(140, 140, 140, 255))

filas = [
    [banderines()],
    [cartel("¡Feliz cumple, Mailen!", 150, 26, ROSA, mm(12))],
    [mira_aqui(60, 34), cartel("¡Hazte una foto!", 92, 22, AZUL, mm(10))],
    [camara(), bocadillo("¡Sonríe!", 48, 34), tarta(), regalo(LILA, AMAR, 34)],
    [globo(ROSA, 24, 36), globo(AMAR, 24, 36), globo(AZUL, 24, 36), globo(VERDE, 24, 36), globo(LILA, 24, 36), corazon(NARAN, 18)],
    [cartel("Pulsa el botón 📷".replace(" 📷", ""), 70, 18, VERDE, mm(8)), cartel("¡Qué guapos!", 62, 18, NARAN, mm(8)),
     corazon(ROSA), corazon(LILA)],
    [estrella(AMAR, 18), estrella(ROSA, 18), estrella(AZUL, 18), estrella(VERDE, 18), estrella(NARAN, 18),
     regalo(ROSA, AMAR, 22)] + [confeti() for _ in range(2)],
]

y = mm(10)
for fila in filas:
    piezas = [acabar(p) for p in fila]
    ancho = sum(p.width for p in piezas)
    hueco = (A4[0] - 2 * margen - ancho) / max(1, len(piezas) - 1) if len(piezas) > 1 else 0
    x = margen if len(piezas) > 1 else (A4[0] - ancho) / 2
    alto = max(p.height for p in piezas)
    for p in piezas:
        hoja.alpha_composite(p, (int(x), int(y + (alto - p.height) / 2)))
        x += p.width + max(hueco, mm(2))
    y += alto + mm(1.5)

print("altura usada: %.0f mm de 297" % (y / MM))
hoja.convert("RGB").save("pegatinas_photomaton.pdf", resolution=DPI)
hoja.convert("RGB").resize((A4[0] // 4, A4[1] // 4)).save("pegatinas_preview.png")
