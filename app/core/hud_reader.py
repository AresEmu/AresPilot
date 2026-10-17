'''Top-right HUD resources (gold, elixir, dark elixir) via the cost glyph reader.

UI ottobre 2026 (16:9). Tesseract on the HUD adds and drops digits (live repros:
elixir 1 363 409 → 71363409, gold 9 25x xxx → 925768, gold → 66590553) and every
consumer — loot tracker, wall threshold, one-wall cost pre-check, upgrade policy —
then decides on garbage. The HUD digits use the same font as the Build-panel prices,
so they go through :mod:`app.core.cost_reader` too.

Digits are white with a dark outline over the resource bars (whose yellow / pink fill
sits right behind them), so only near-white ink counts here. Instead of slicing rows
by projection (the storage icons and bar highlights bridge rows), every component is
classified on its own: digit-sized + digit-shaped components are grouped into lines,
lines are checked against the thousands grouping, and each resource is the number at
its row's fixed height.
'''
from typing import List, Optional, Tuple

import cv2
import numpy as np

from app.core.cost_reader import _group_digits, classify_glyph, normalize_glyph
from app.utils.logger import setup_logger

logger = setup_logger('HudReader')

# Fractions of the frame, measured on 2558x1438 / 2560x1440 home frames.
_HUD_REGION_FRAC = (0.40, 0.0, 0.575, 0.20)  # x, y, w, h (the bars move left when the Build panel is open)
_HUD_ROW_Y_FRAC = {'gold': 0.043, 'elixir': 0.099, 'dark': 0.157}
_HUD_ROW_TOL_FRAC = 0.022
_DIGIT_H_FRAC = (0.012, 0.030)  # HUD digit height range
_MIN_GLYPH_SCORE = 0.80


def _white_mask(bgr):
    b = bgr[:, :, 0]
    g = bgr[:, :, 1]
    r = bgr[:, :, 2]
    return (b >= 185) & (g >= 185) & (r >= 185)


def _digit_components(mask, fh):
    '''(x, y, w, h, digit) for every component that is digit-sized and digit-shaped.'''
    (n, _lab, stats, _c) = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity = 8)
    (h_lo, h_hi) = (fh * _DIGIT_H_FRAC[0], fh * _DIGIT_H_FRAC[1])
    out = []
    for i in range(1, n):
        (x, y, w, h, area) = (int(v) for v in stats[i])
        if not h_lo <= h <= h_hi or w > 1.1 * h or area < 12:
            continue
        (digit, score) = classify_glyph(normalize_glyph(mask[y:y + h, x:x + w]))
        if digit and score >= _MIN_GLYPH_SCORE:
            out.append((x, y, w, h, digit))
    return out


def _lines(comps):
    '''Group digit components into text lines (similar height, overlapping rows).'''
    lines = []
    for comp in sorted(comps, key = (lambda c: c[1] + c[3] / 2)):
        cy = comp[1] + comp[3] / 2
        for line in lines:
            ref = line[0]
            if abs(cy - (ref[1] + ref[3] / 2)) <= 0.4 * ref[3] and 0.75 <= comp[3] / ref[3] <= 1.33:
                line.append(comp)
                break
        else:
            lines.append([comp])
    return lines


def _numbers_in_line(line):
    '''A line may hold more than one number (or digit-shaped noise): split on wide
    gaps, keep each run that passes the thousands grouping.'''
    line = sorted(line, key = (lambda c: c[0]))
    widths = sorted(c[2] for c in line)
    med_w = max(1, widths[len(widths) // 2])
    runs = [[line[0]]]
    for prev, cur in zip(line, line[1:]):
        if cur[0] - (prev[0] + prev[2]) > 1.1 * med_w:
            runs.append([])
        runs[-1].append(cur)
    numbers = []
    for run in runs:
        groups = _group_digits([c[:4] for c in run])
        if not 1 <= len(groups[0]) <= 3 or any(len(g) != 3 for g in groups[1:]):
            continue
        text = ''.join(c[4] for c in run)
        if len(text) > 1 and text[0] == '0':
            continue
        x0 = min(c[0] for c in run)
        y0 = min(c[1] for c in run)
        x1 = max(c[0] + c[2] for c in run)
        y1 = max(c[1] + c[3] for c in run)
        numbers.append((int(text), (x0, y0, x1 - x0, y1 - y0)))
    return numbers


def read_hud_numbers(frame):
    '''All grouped numbers in the top-right HUD area → [(value, (x, y, w, h)), ...].'''
    if frame is None or frame.size == 0:
        return []
    (fh, fw) = frame.shape[:2]
    (rx, ry, rw, rh) = _HUD_REGION_FRAC
    (x, y, w, h) = (round(fw * rx), round(fh * ry), round(fw * rw), round(fh * rh))
    roi = frame[y:y + h, x:x + w]
    mask = _white_mask(roi)
    out = []
    for line in _lines(_digit_components(mask, fh)):
        for (value, (bx, by, bw, bh)) in _numbers_in_line(line):
            out.append((value, (x + bx, y + by, bw, bh)))
    return out


def read_hud_triplet(frame):
    '''(gold, elixir, dark) from one frame, or None when any of the three is missing.
    Each resource is the longest number whose center sits at its row's height.'''
    numbers = read_hud_numbers(frame)
    if not numbers:
        return None
    fh = frame.shape[0]
    values = []
    for key in ('gold', 'elixir', 'dark'):
        row_y = fh * _HUD_ROW_Y_FRAC[key]
        at_row = [(v, b) for (v, b) in numbers if abs(b[1] + b[3] / 2 - row_y) <= fh * _HUD_ROW_TOL_FRAC]
        if not at_row:
            logger.debug('HUD %s row unread (numbers: %s)', key, numbers)
            return None
        # Several candidates: the real amount is the widest run (noise is 1-2 glyphs).
        values.append(max(at_row, key = (lambda vb: vb[1][2]))[0])
    return tuple(values)
