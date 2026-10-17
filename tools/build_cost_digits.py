"""Ricava i glyph di riferimento delle cifre (templates/digits/) da screenshot con costi noti.

Il lettore dei costi (app/core/cost_reader.py) confronta ogni cifra con questi glyph.
Va rilanciato solo se Supercell cambia il font dei prezzi.

Uso (dalla cartella principale del progetto):
    python tools/build_cost_digits.py            # usa i campioni in SAMPLES
    python tools/build_cost_digits.py --list screens/build_top.png
--list stampa le righe trovate nella colonna dei costi (y e numero di glyph), utile per
aggiungere nuovi campioni: (file, y della riga, testo atteso; '?' = carattere da ignorare).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from app.core.cost_reader import extract_band_glyphs  # noqa: E402

# Colonna dei costi del pannello Build (frazioni del frame, 16:9).
COST_COLUMN = (0.87, 0.07, 0.109, 0.82)

SAMPLES = [
    ('build_top.png', 530, '144000'),
    ('build_top.png', 645, '6400000'),
    ('build_top.png', 919, '208000'),
    ('build_top.png', 1032, '176000'),
    ('build_top.png', 1147, '120000'),
    ('build_top.png', 1260, '64000'),
    ('build_top.png', 296, '3?5'),  # timer "3d 5H" (la H bassa viene scartata): unica fonte del 3
    ('build_mid.png', 173, '9600000'),
    ('build_mid.png', 401, '8800000'),
    ('build_mid.png', 630, '8000000'),
    ('build_mid.png', 743, '7200000'),
    ('build_mid.png', 858, '6800000'),
    ('build_mid.png', 971, '6560000'),
    ('build_bottom.png', 134, '12800000'),
    ('build_bottom.png', 318, '11200000'),
    ('build_bottom.png', 432, '10400000'),
    ('build_bottom.png', 888, '7600000'),
]
MAX_PER_DIGIT = 6


def region_of(img):
    h, w = img.shape[:2]
    (fx, fy, fw, fh) = COST_COLUMN
    return (round(w * fx), round(h * fy), round(w * fw), round(h * fh))


def main():
    if '--list' in sys.argv:
        for p in [a for a in sys.argv[1:] if not a.startswith('--')]:
            img = cv2.imread(p)
            for (y, glyphs) in extract_band_glyphs(img, region_of(img)):
                print(f'{Path(p).name} y={y} glyph={len(glyphs)}')
        return
    per_digit = {str(d): [] for d in range(10)}
    for (name, y_ref, text) in SAMPLES:
        img = cv2.imread(str(ROOT / 'screens' / name))
        if img is None:
            print(f'manca screens/{name}')
            continue
        bands = extract_band_glyphs(img, region_of(img))
        match = [g for (y, g) in bands if abs(y - y_ref) <= 6]
        if not match or len(match[0]) != len(text):
            print(f'{name} y={y_ref}: atteso {len(text)} glyph, trovati {[len(g) for (y, g) in bands if abs(y - y_ref) <= 6]}')
            continue
        for ch, glyph in zip(text, match[0]):
            if ch == '?':
                continue
            pool = per_digit[ch]
            if len(pool) < MAX_PER_DIGIT and all(((glyph >= 128) != (g >= 128)).mean() > 0.03 for g in pool):
                pool.append(glyph)
    out = ROOT / 'templates' / 'digits'
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob('*.png'):
        old.unlink()
    for d, pool in per_digit.items():
        for i, g in enumerate(pool):
            cv2.imwrite(str(out / f'{d}_{i}.png'), g)
        print(f'cifra {d}: {len(pool)} glyph')
    missing = [d for d, pool in per_digit.items() if not pool]
    if missing:
        print('ATTENZIONE: nessun campione per', ', '.join(missing))


if __name__ == '__main__':
    main()

