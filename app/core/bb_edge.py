'''Builder Base deploy geometry: the red "no deploy" border around the enemy village and the
six drop zones just outside it (Baby Dragon strategy, both stages of a battle).

The border is a thin red line made of straight segments along the two isometric grid
directions. It is found as red-dominant pixels (red minus max(green, blue)) → Hough
segments → only isometric slopes kept → convex hull. Measured on the October 2026 UI at
2560x1440, full zoom-out: one tile is ~50 px wide (0.0195 of the frame width).
'''
from __future__ import annotations
import math
import random
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

# Pixels whose red channel beats green and blue by this much (the stage-2 border is a dull
# red-brown on green grass, the stage-1 one a bright red on grey stone).
_RED_MARGIN = 30
# Isometric grid lines on screen: |dy/dx| measured 0.6-0.8.
_SLOPE_RANGE = (0.5, 0.9)
_MIN_SEGMENT_FRAC = 0.02      # Hough: segment >= 2% of the frame width
_MAX_GAP_FRAC = 0.004
_MIN_SEGMENTS = 6             # fewer = no border on screen
# Battlefield only: HUD on top, troop bar at the bottom, End Battle / Boost Army bottom left.
_FIELD_TOP = 0.12
_FIELD_BOTTOM = 0.83
_BUTTON_BOX = (0.0, 0.66, 0.20, 1.0)   # x0, y0, x1, y1
# "Overall Damage" panel bottom right: its gold stars are red-dominant and, lit from stage 2
# on (damage >= 100%), stretched the hull to the corner.
_DAMAGE_PANEL_BOX = (0.84, 0.70, 1.0, 1.0)
# A real border at full zoom-out spans >= 0.29 x 0.41 of the frame (measured); fire and the
# wooden walls of a village under attack, with no border shown, ~0.15 x 0.25.
_MIN_BORDER_SIZE = (0.20, 0.28)
# Drop points must stay clear of the HUD and the troop bar.
_SAFE_X = (0.04, 0.96)
_SAFE_Y = (0.14, 0.81)
# Playable floor at full zoom-out: left, top, right, bottom corners (frame fractions) of a
# diamond that stays on the floor in both villages (measured; the cliffs, forest and water
# around it take no troops). Up to 8 tiles out would otherwise reach them.
_FIELD_CORNERS = ((0.14, 0.52), (0.52, 0.11), (0.80, 0.52), (0.50, 0.95))
# Six zones around the village (screen angles, y down): left, upper-left, upper-right,
# right, lower-right, lower-left — the pattern of placexample.png.
ZONE_ANGLES = (180, 240, 300, 0, 60, 120)
_ZONE_JITTER_DEG = 10
# A blocked zone slides along the border by these angles (first free spot wins).
_ZONE_SLIDES = (0, 12, -12, 24, -24, 36, -36, 48, -48)
TILE_FRAC = 0.0195            # tile width / frame width at full zoom-out
_TILE_STEP_FRAC = 0.016       # one tile outward from the border, along a ray, on screen
DISTANCE_TILES = (2.0, 8.0)


def red_edge_mask(frame):
    '''Binary mask of red-dominant pixels on the battlefield.'''
    (h, w) = frame.shape[:2]
    (b, g, r) = [frame[:, :, i].astype(np.int16) for i in range(3)]
    mask = ((r - np.maximum(g, b)) >= _RED_MARGIN).astype(np.uint8) * 255
    mask[:int(_FIELD_TOP * h)] = 0
    mask[int(_FIELD_BOTTOM * h):] = 0
    for (x0, y0, x1, y1) in (_BUTTON_BOX, _DAMAGE_PANEL_BOX):
        mask[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)] = 0
    return mask


def border_segments(frame):
    '''Red isometric segments (x1, y1, x2, y2) on the frame.'''
    (h, w) = frame.shape[:2]
    mask = red_edge_mask(frame)
    lines = cv2.HoughLinesP(mask, 1, np.pi / 360, threshold = 30,
                            minLineLength = max(10, int(w * _MIN_SEGMENT_FRAC)),
                            maxLineGap = max(2, int(w * _MAX_GAP_FRAC)))
    if lines is None:
        return []
    keep = []
    for (x1, y1, x2, y2) in lines.reshape(-1, 4).tolist():
        if x1 == x2:
            continue
        slope = abs((y2 - y1) / (x2 - x1))
        if _SLOPE_RANGE[0] <= slope <= _SLOPE_RANGE[1]:
            keep.append((x1, y1, x2, y2))
    return keep


def border_hull(frame):
    '''Convex hull (N x 1 x 2 int32) of the red border, or None when no border is on screen.'''
    segments = border_segments(frame)
    if len(segments) < _MIN_SEGMENTS:
        return None
    points = np.array([[x1, y1] for (x1, y1, _x2, _y2) in segments] + [[x2, y2] for (_x1, _y1, x2, y2) in segments], dtype = np.int32)
    hull = cv2.convexHull(points)
    (_x, _y, bw, bh) = cv2.boundingRect(hull)
    (h, w) = frame.shape[:2]
    if bw < _MIN_BORDER_SIZE[0] * w or bh < _MIN_BORDER_SIZE[1] * h:
        return None  # red strokes on the village (fire, walls, a banner), not its border
    return hull


def hull_centre(hull):
    m = cv2.moments(hull)
    if m['m00']:
        return (m['m10'] / m['m00'], m['m01'] / m['m00'])
    pts = hull.reshape(-1, 2)
    return (float(pts[:, 0].mean()), float(pts[:, 1].mean()))


def synthetic_hull(centre, frame):
    '''Fallback border: a diamond around ``centre`` sized like a mid-level village.'''
    (h, w) = frame.shape[:2]
    (cx, cy) = centre
    (rx, ry) = (0.14 * w, 0.17 * h)
    pts = np.array([[cx - rx, cy], [cx, cy - ry], [cx + rx, cy], [cx, cy + ry]], dtype = np.int32)
    return pts.reshape(-1, 1, 2)


def village_centre(frame):
    '''Centre of the enemy village: the densest edges (buildings) in the central window —
    the empty field is uniform, the forest along the map border is outside the window.'''
    (h, w) = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 160).astype(np.float32)
    window = np.zeros_like(edges)
    window[int(0.22 * h):int(0.72 * h), int(0.30 * w):int(0.78 * w)] = 1
    k = int(w * 0.09) | 1
    density = cv2.blur(edges * window, (k, k)) * window
    (y, x) = np.unravel_index(int(np.argmax(density)), density.shape)
    return (int(x), int(y))


def _in_safe_area(x, y, w, h):
    if not (_SAFE_X[0] * w <= x <= _SAFE_X[1] * w and _SAFE_Y[0] * h <= y <= _SAFE_Y[1] * h):
        return False
    field = np.array([[fx * w, fy * h] for (fx, fy) in _FIELD_CORNERS], dtype = np.float32).reshape(-1, 1, 2)
    if cv2.pointPolygonTest(field, (float(x), float(y)), False) < 0:
        return False
    (bx0, by0, bx1, by1) = _BUTTON_BOX
    return not (bx0 * w <= x <= bx1 * w and by0 * h <= y <= by1 * h)


def _border_distance_along(hull, centre, angle_rad, limit):
    '''Distance from ``centre`` to the hull edge along ``angle_rad`` (first point outside).'''
    (cx, cy) = centre
    (dx, dy) = (math.cos(angle_rad), math.sin(angle_rad))
    contour = hull.reshape(-1, 1, 2).astype(np.float32)
    t = 0.0
    while t < limit:
        if cv2.pointPolygonTest(contour, (cx + dx * t, cy + dy * t), False) < 0:
            return t
        t += 2.0
    return None


def zone_points(frame, hull, rng = random, distance = DISTANCE_TILES):
    '''One drop point per zone (ZONE_ANGLES order): on the ray from the village centre, past
    the border by a random 2-8 tiles. A zone that would land off the floor, on the HUD, the
    troop bar or the bottom-left buttons first comes closer (never under 2 tiles), then slides
    along the border (up to +-48 degrees) to the nearest free spot; skipped only if none is
    free. ``distance`` overrides the 2-8 tile range (retries come closer to the border).'''
    (h, w) = frame.shape[:2]
    centre = hull_centre(hull)
    step = _TILE_STEP_FRAC * w
    points = []
    for base in ZONE_ANGLES:
        jitter = rng.uniform(-_ZONE_JITTER_DEG, _ZONE_JITTER_DEG)
        tiles_wanted = rng.uniform(*distance)
        placed = None
        for slide in _ZONE_SLIDES:
            angle = math.radians(base + jitter + slide)
            border = _border_distance_along(hull, centre, angle, limit = 2 * max(w, h))
            if border is None:
                continue
            tiles = tiles_wanted
            while tiles >= distance[0] - 1e-6:
                d = border + tiles * step
                (x, y) = (centre[0] + math.cos(angle) * d, centre[1] + math.sin(angle) * d)
                if _in_safe_area(x, y, w, h):
                    placed = (int(x), int(y))
                    break
                tiles -= 0.5
            if placed is not None:
                break
        if placed is not None:
            points.append(placed)
    return points


def spread_over_zones(points, count, rng = random):
    '''``count`` drop points over the zones: one per zone round-robin from a random zone,
    with a few pixels of scatter when a zone gets more than one troop.'''
    if not points or count <= 0:
        return []
    start = rng.randrange(len(points))
    out = []
    for i in range(count):
        (x, y) = points[(start + i) % len(points)]
        if i >= len(points):
            (x, y) = (x + rng.randint(-14, 14), y + rng.randint(-10, 10))
        out.append((int(x), int(y)))
    return out


def outside_distance_tiles(hull, point, frame_width):
    '''How far ``point`` lies outside the hull, in tiles (negative = inside).'''
    contour = hull.reshape(-1, 1, 2).astype(np.float32)
    px = cv2.pointPolygonTest(contour, (float(point[0]), float(point[1])), True)
    return -px / (_TILE_STEP_FRAC * frame_width)
