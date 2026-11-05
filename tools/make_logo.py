'''AresPilot logo: a spearhead "A" (Ares + pilot arrow) in the UI blue on black.'''
import sys
from PIL import Image, ImageChops, ImageDraw, ImageFilter

S = 2048
out_png, out_ico, preview = sys.argv[1:4]


def P(x, y):
    return (x * S, y * S)


def vgrad(top, bottom):
    g = Image.new('RGBA', (S, S))
    d = ImageDraw.Draw(g)
    for y in range(S):
        t = y / (S - 1)
        d.line([(0, y), (S, y)], fill = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,))
    return g


img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
# Background tile: near-black with a faint lift at the top.
tile_mask = Image.new('L', (S, S), 0)
ImageDraw.Draw(tile_mask).rounded_rectangle([0, 0, S - 1, S - 1], radius = int(0.225 * S), fill = 255)
img.paste(vgrad((30, 30, 34), (6, 6, 8)), (0, 0), tile_mask)

# Orbit ring with a gap at the top where the spear tip passes.
ring = Image.new('L', (S, S), 0)
rd = ImageDraw.Draw(ring)
(cx, cy, r, wdt) = (0.5 * S, 0.53 * S, 0.37 * S, int(0.022 * S))
rd.arc([cx - r, cy - r, cx + r, cy + r], start = -62, end = 242, fill = 255, width = wdt)
img.paste(Image.new('RGBA', (S, S), (10, 132, 255, 255)), (0, 0), ring.point(lambda v: v * 70 // 255))

# Spearhead "A": two legs meeting at a sharp tip, an inner notch, and a crossbar.
spear = Image.new('L', (S, S), 0)
sd = ImageDraw.Draw(spear)
sd.polygon([P(0.5, 0.13), P(0.765, 0.80), P(0.635, 0.80), P(0.5, 0.445), P(0.365, 0.80), P(0.235, 0.80)], fill = 255)
sd.polygon([P(0.355, 0.585), P(0.645, 0.585), P(0.625, 0.655), P(0.375, 0.655)], fill = 255)
glow = spear.filter(ImageFilter.GaussianBlur(S * 0.03)).point(lambda v: v * 110 // 255)
img.paste(Image.new('RGBA', (S, S), (10, 132, 255, 255)), (0, 0), ImageChops.multiply(glow, tile_mask))
img.paste(vgrad((100, 210, 255), (10, 110, 255)), (0, 0), spear)
# Highlight on the left face of the tip.
hl = Image.new('L', (S, S), 0)
ImageDraw.Draw(hl).polygon([P(0.5, 0.13), P(0.5, 0.445), P(0.365, 0.80), P(0.235, 0.80)], fill = 60)
img.paste(Image.new('RGBA', (S, S), (255, 255, 255, 255)), (0, 0), ImageChops.multiply(hl, spear))

final = img.resize((512, 512), Image.LANCZOS)
final.save(out_png)
img.resize((256, 256), Image.LANCZOS).save(out_ico, sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
sheet = Image.new('RGBA', (512 + 20 + 64 + 20 + 32 + 20 + 16, 512), (0, 0, 0, 255))
sheet.paste(final, (0, 0), final)
x = 532
for n in (64, 32, 16):
    small = img.resize((n, n), Image.LANCZOS)
    sheet.paste(small, (x, 20), small)
    x += n + 20
sheet.save(preview)
print('ok')
