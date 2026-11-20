import random, math
from PIL import Image, ImageDraw, ImageFont, ImageFilter
W, H = 1280, 720
S = 2  # supersampling
w, h = W*S, H*S
random.seed(7)
COLS = ["#ff4d6d", "#ffb703", "#3a86ff", "#06d6a0", "#8338ec", "#fb5607", "#ff006e"]
img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# Borde exterior de color con esquinas redondeadas (hueco central transparente)
band = 26*S
d.rectangle([0, 0, w, h], fill="#ff4d6d")
d.rounded_rectangle([band, band, w-band, h-band], radius=40*S, fill=(0, 0, 0, 0))
# Fina línea blanca interior
d.rounded_rectangle([band, band, w-band, h-band], radius=40*S, outline="white", width=5*S)

# Confeti sobre la banda
for _ in range(500):
    x, y = random.uniform(0, w), random.uniform(0, h)
    if band+12*S < x < w-band-12*S and band+12*S < y < h-band-12*S:
        continue
    c = random.choice(COLS[1:] + ["#ffffff"])
    r = random.uniform(3, 7)*S
    if random.random() < .5:
        d.ellipse([x-r, y-r, x+r, y+r], fill=c)
    else:
        a = random.uniform(0, math.pi)
        dx, dy = math.cos(a)*r*1.8, math.sin(a)*r*1.8
        d.line([x-dx, y-dy, x+dx, y+dy], fill=c, width=int(3*S))

# Banderines colgando en la parte de arriba
def garland(x0, x1, y0, sag, n):
    pts = []
    for i in range(n+1):
        t = i/n
        pts.append((x0+(x1-x0)*t, y0+sag*4*t*(1-t)))
    d.line(pts, fill="#444444", width=3*S)
    for i in range(n):
        (ax, ay), (bx, by) = pts[i], pts[i+1]
        mx, my = (ax+bx)/2, (ay+by)/2
        d.polygon([(ax+4*S, ay), (bx-4*S, by), (mx, my+62*S)], fill=COLS[i % len(COLS)], outline="white")
garland(band-10*S, w//2+10*S, 14*S, 40*S, 8)
garland(w//2-10*S, w-band+10*S, 14*S, 40*S, 8)

# Globos en las esquinas inferiores
def balloon(cx, cy, rx, ry, col):
    d.line([(cx, cy+ry), (cx+random.uniform(-25, 25)*S, cy+ry+150*S)], fill="#555555", width=2*S)
    d.ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=col)
    d.polygon([(cx-9*S, cy+ry+12*S), (cx+9*S, cy+ry+12*S), (cx, cy+ry-6*S)], fill=col)
    d.ellipse([cx-rx*.5, cy-ry*.65, cx-rx*.15, cy-ry*.2], fill=(255, 255, 255, 110))
for (cx, cy, col) in [(70, 520, "#3a86ff"), (135, 575, "#ffb703"), (55, 640, "#ff006e"),
                      (1210, 520, "#06d6a0"), (1145, 575, "#8338ec"), (1225, 640, "#fb5607")]:
    balloon(cx*S, cy*S, 42*S, 52*S, col)

# Cartel inferior con el texto
font = None
for f in ["/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
          "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]:
    try:
        font = ImageFont.truetype(f, 46*S); break
    except OSError:
        pass
txt = "¡Feliz cumple, Mailen!"
tb = d.textbbox((0, 0), txt, font=font)
tw, th = tb[2]-tb[0], tb[3]-tb[1]
px, py = 34*S, 16*S
bx0 = (w-tw)//2 - px; bx1 = (w+tw)//2 + px
by1 = h - 10*S; by0 = by1 - th - 2*py
shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
ImageDraw.Draw(shadow).rounded_rectangle([bx0+6*S, by0+8*S, bx1+6*S, by1+8*S], radius=40*S, fill=(0, 0, 0, 110))
img = Image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(8*S)), img)
d = ImageDraw.Draw(img)
d.rounded_rectangle([bx0, by0, bx1, by1], radius=40*S, fill="#ffffff", outline="#ff4d6d", width=6*S)
d.text(((w-tw)//2 - tb[0], by0+py - tb[1]), txt, font=font, fill="#ff006e")

img = img.resize((W, H), Image.LANCZOS)
img.save("marco_fiesta_mailen.png")
# Vista previa con la última foto
try:
    base = Image.open("../ultima.jpg").convert("RGBA").resize((W, H))
    Image.alpha_composite(base, img).convert("RGB").save("preview.jpg", quality=90)
except FileNotFoundError:
    pass
