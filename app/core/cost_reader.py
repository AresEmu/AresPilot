'''Glyph reader for the game's grouped cost numbers ("6 400 000"), UI ottobre 2026.

Tesseract misreads this font too often to trust with purchases (live repro on the new
Build panel: 9 600 000 → 5600000, 12 800 000 → 2800000, 6 800 000 → 6200000). The
digits are always the same font, so each glyph is matched against reference masks in
``templates/digits/<d>_<n>.png`` (normalized size, built by
``tools/build_cost_digits.py`` from screenshots with known costs).

Ink is near-white (affordable) OR saturated red (not affordable) — both survive the
mask, and the red share of the ink tells the two apart. Vision only — no clicks.
'''
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional, Tuple

import cv2
import numpy as np

from app.utils.common import get_resource_path

GLYPH_W = 16
GLYPH_H = 24
_MIN_GLYPH_SCORE = 0.80  # pixel agreement with the best reference
_RED_INK_FRACTION = 0.35  # share of red ink pixels for a "red" (unaffordable) number


@dataclass(frozen = True)
class CostLine:
    value: int
    bbox: Tuple[int, int, int, int]  # x, y, w, h in full-frame coordinates
    red: bool
    red_fraction: float

    @property
    def center(self):
        (x, y, w, h) = self.bbox
        return (x + w // 2, y + h // 2)


def ink_masks(bgr):
    '''(ink, red) boolean masks: ink = white OR red glyph fill.'''
    b = bgr[:, :, 0].astype(np.int16)
    g = bgr[:, :, 1].astype(np.int16)
    r = bgr[:, :, 2].astype(np.int16)
    white = (b >= 185) & (g >= 185) & (r >= 185)
    # Unaffordable costs are a salmon red (measured fill ~R230 G100-160 B100-130);
    # the brown card behind them peaks at R~105, the gold icon is fenced out by x.
    red = (r >= 200) & (g <= 170) & (b <= 150) & (r - g >= 60)
    # The upgrade dialog's green Confirm prints an affordable price in yellow
    # (~R230 G230 B0-30); the button's light-green body stays below r 200 or above b 90.
    yellow = (r >= 200) & (g >= 200) & (b <= 90)
    return (white | red | yellow, red)


def normalize_glyph(mask):
    '''Binary glyph crop → GLYPH_W×GLYPH_H uint8 (0/255), aspect kept, centered.'''
    (h, w) = mask.shape[:2]
    scale = min(GLYPH_W / w, GLYPH_H / h)
    nw = max(1, round(w * scale))
    nh = max(1, round(h * scale))
    small = cv2.resize(mask.astype(np.uint8) * 255, (nw, nh), interpolation = cv2.INTER_AREA)
    out = np.zeros((GLYPH_H, GLYPH_W), np.uint8)
    x0 = (GLYPH_W - nw) // 2
    y0 = (GLYPH_H - nh) // 2
    out[y0:y0 + nh, x0:x0 + nw] = small
    return out


@lru_cache(maxsize = 1)
def _references():
    refs = []
    folder = get_resource_path('templates/digits')
    try:
        paths = sorted(folder.glob('*.png'))
    except Exception:
        paths = []
    for p in paths:
        digit = p.name[0]
        if not digit.isdigit():
            continue
        img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        if img.shape != (GLYPH_H, GLYPH_W):
            img = cv2.resize(img, (GLYPH_W, GLYPH_H), interpolation = cv2.INTER_AREA)
        refs.append((digit, img >= 128))
    return refs


def classify_glyph(norm):
    '''Normalized glyph → (digit, score) against the references; ('', 0) if none loaded.'''
    probe = norm >= 128
    best = ('', 0.0)
    for (digit, ref) in _references():
        score = float((probe == ref).mean())
        if score > best[1]:
            best = (digit, score)
    return best


def _line_bands(ink, min_px, min_h):
    on = ink.sum(axis = 1) >= min_px
    bands = []
    start = None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= min_h:
                bands.append((start, i))
            start = None
    if start is not None and len(on) - start >= min_h:
        bands.append((start, len(on)))
    return bands


def line_glyphs(ink_band):
    '''Connected components of one text band → list of (x, y, w, h) sorted by x,
    keeping only full-height glyphs (drops dots, outline fragments, icon specks).'''
    (n, _lab, stats, _c) = cv2.connectedComponentsWithStats(ink_band.astype(np.uint8), connectivity = 8)
    comps = [tuple(int(v) for v in stats[i][:4]) for i in range(1, n) if stats[i][4] >= 12]
    if not comps:
        return []
    tallest = max(c[3] for c in comps)
    return sorted((c for c in comps if c[3] >= 0.85 * tallest), key = (lambda c: c[0]))


def _rightmost_cluster(glyphs):
    '''Keep the glyphs right of the last wide gap: crafting rows print a subtitle
    ("Cake-A-Pult Splash Damage") on the cost line that reaches into the column.
    Thousands separators measure ~0.6 digit widths; the subtitle gap is wider.'''
    widths = sorted(g[2] for g in glyphs)
    med_w = max(1, widths[len(widths) // 2])
    cut = 0
    for i in range(1, len(glyphs)):
        prev = glyphs[i - 1]
        if glyphs[i][0] - (prev[0] + prev[2]) > 1.1 * med_w:
            cut = i
    return glyphs[cut:]


def _group_digits(glyphs):
    '''Split glyph boxes into digit groups on the thousands-separator gaps.'''
    widths = sorted(g[2] for g in glyphs)
    med_w = max(1, widths[len(widths) // 2])
    groups = [[glyphs[0]]]
    for prev, cur in zip(glyphs, glyphs[1:]):
        gap = cur[0] - (prev[0] + prev[2])
        if gap > 0.45 * med_w:
            groups.append([])
        groups[-1].append(cur)
    return groups


def read_number_band(bgr_band, ink_band, red_band, origin = (0, 0), min_digits = 4):
    '''Read one band as a grouped number. Returns CostLine or None.
    The thousands grouping is the format check: a leading group of 1-3 digits then
    groups of exactly 3 — timers ("3d 14H") and labels never pass it.'''
    glyphs = line_glyphs(ink_band)
    if glyphs:
        glyphs = _rightmost_cluster(glyphs)
    if len(glyphs) < min_digits:
        return None
    groups = _group_digits(glyphs)
    if not 1 <= len(groups[0]) <= 3 or any(len(g) != 3 for g in groups[1:]):
        return None
    digits = []
    for (x, y, w, h) in glyphs:
        norm = normalize_glyph(ink_band[y:y + h, x:x + w])
        (d, score) = classify_glyph(norm)
        if not d or score < _MIN_GLYPH_SCORE:
            return None
        digits.append(d)
    text = ''.join(digits)
    if text[0] == '0' and len(text) > 1:
        return None
    x0 = min(g[0] for g in glyphs)
    y0 = min(g[1] for g in glyphs)
    x1 = max(g[0] + g[2] for g in glyphs)
    y1 = max(g[1] + g[3] for g in glyphs)
    ink_px = int(ink_band[y0:y1, x0:x1].sum())
    red_px = int(red_band[y0:y1, x0:x1].sum())
    red_fraction = red_px / max(1, ink_px)
    (ox, oy) = origin
    return CostLine(value = int(text), bbox = (ox + x0, oy + y0, x1 - x0, y1 - y0),
                    red = red_fraction >= _RED_INK_FRACTION, red_fraction = red_fraction)


def read_cost_lines(frame, region, min_digits = 4):
    '''All grouped numbers inside ``region`` (x, y, w, h), top to bottom.'''
    if frame is None or frame.size == 0:
        return []
    (fh, fw) = frame.shape[:2]
    (x, y, w, h) = region
    x = max(0, int(x))
    y = max(0, int(y))
    w = min(fw - x, int(w))
    h = min(fh - y, int(h))
    if w <= 4 or h <= 4:
        return []
    roi = frame[y:y + h, x:x + w]
    (ink, red) = ink_masks(roi)
    min_h = max(6, round(fh * 0.009))  # cost glyphs are ~0.015 h tall
    out = []
    for (a, b) in _line_bands(ink, max(3, round(fw * 0.002)), min_h):
        a2 = max(0, a - 2)
        b2 = min(h, b + 2)
        line = read_number_band(roi[a2:b2], ink[a2:b2], red[a2:b2], origin = (x, y + a2), min_digits = min_digits)
        if line is not None:
            out.append(line)
    return out


def extract_band_glyphs(frame, region):
    '''Debug/tooling helper: [(band_y_center, [normalized glyph, ...]), ...].'''
    (fh, fw) = frame.shape[:2]
    (x, y, w, h) = region
    roi = frame[y:y + h, x:x + w]
    (ink, _red) = ink_masks(roi)
    out = []
    for (a, b) in _line_bands(ink, max(3, round(fw * 0.002)), max(6, round(fh * 0.009))):
        a2 = max(0, a - 2)
        b2 = min(h, b + 2)
        band = ink[a2:b2]
        boxes = line_glyphs(band)
        boxes = _rightmost_cluster(boxes) if boxes else boxes
        glyphs = [normalize_glyph(band[gy:gy + gh, gx:gx + gw]) for (gx, gy, gw, gh) in boxes]
        out.append((y + (a + b) // 2, glyphs))
    return out
