'''Builder Base deploy geometry: the red "no deploy" border around the enemy village and the
the drop points just outside it, spread apart (Baby Dragon strategy, both stages of a battle).

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
TILE_FRAC = 0.0195            # tile width / frame width at full zoom-out
_TILE_STEP_FRAC = 0.016       # one tile outward from the border, along a ray, on screen
DISTANCE_TILES = (2.0, 8.0)
_DISTANCE_STEP_TILES = 0.5
# Free spots are looked for on rays from the village centre every few degrees; the drops are
# spread evenly over the rays that have room (all around a small village; the open sides
# only when the village fills the floor on one side).
_RAY_STEP_DEG = 3
# Drops stay at least this many tiles apart: Baby Dragons dropped on the same spot fly and
# fight as one clump. On a crowded floor the gap shrinks step by step; past the last step a
# drop takes the free spot farthest from the others, so two drops never share a spot.
SEPARATION_TILES = 5.0
_SEPARATION_STEPS = (1.0, 0.8, 0.65, 0.5)


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


def free_spots(hull, centre, w, h, distance = DISTANCE_TILES):
    '''Every free drop spot past the border, ray by ray: a list of (angle_deg, [(tiles,
    (x, y)), ...]) for the rays that have at least one spot on the floor, off the HUD, the
    troop bar and the bottom-left buttons, ``distance`` tiles past the border.'''
    step = _TILE_STEP_FRAC * w
    tiles_grid = np.arange(distance[0], distance[1] + 1e-6, _DISTANCE_STEP_TILES).tolist()
    rays = []
    for deg in range(0, 360, _RAY_STEP_DEG):
        angle = math.radians(deg)
        border = _border_distance_along(hull, centre, angle, limit = 2 * max(w, h))
        if border is None:
            continue
        spots = []
        for tiles in tiles_grid:
            d = border + tiles * step
            (x, y) = (centre[0] + math.cos(angle) * d, centre[1] + math.sin(angle) * d)
            if _in_safe_area(x, y, w, h):
                spots.append((tiles, (int(x), int(y))))
        if spots:
            rays.append((deg, spots))
    return rays


def drop_points(frame, hull, count, rng = random, distance = DISTANCE_TILES, avoid = ()):
    '''``count`` drop points around the village, one per troop, spread evenly over the rays
    that have room (all around a small village, the open sides only when the village fills the
    floor on one side), from a random ray. Each point lies a random 2-8 tiles past the border
    (``distance`` overrides the range: retries come closer to the border), or the nearest free
    distance on that ray, or on a ray close by.

    Every point stays SEPARATION_TILES from the others and from ``avoid`` (troops already
    dropped); a crowded floor shrinks that gap step by step, and past the last step the free
    spot farthest from the others is used, so two drops never share a spot. Empty when no
    spot is free at all.'''
    if count <= 0:
        return []
    (h, w) = frame.shape[:2]
    rays = free_spots(hull, hull_centre(hull), w, h, distance)
    if not rays:
        return []
    tile = TILE_FRAC * w
    n = len(rays)
    start = rng.randrange(n)
    reach = max(1, n // (2 * count))  # rays a drop may move to either side, half the spacing
    every_spot = [p for (_deg, spots) in rays for (_t, p) in spots]
    taken = [(float(x), float(y)) for (x, y) in avoid]
    points = []
    for i in range(count):
        k = (start + round(i * n / count)) % n
        wanted = rng.uniform(*distance)
        candidates = []
        for off in [0] + [s * j for j in range(1, reach + 1) for s in (1, -1)]:
            spots = rays[(k + off) % n][1]
            candidates += [p for (_t, p) in sorted(spots, key = lambda s: abs(s[0] - wanted))]
        placed = None
        for factor in _SEPARATION_STEPS:
            gap = SEPARATION_TILES * factor * tile
            placed = next((p for p in candidates if all(math.dist(p, q) >= gap for q in taken)), None)
            if placed is not None:
                break
        if placed is None:
            pool = every_spot if taken else candidates
            placed = max(pool, key = lambda p: min((math.dist(p, q) for q in taken), default = 0.0))
        points.append(placed)
        taken.append(placed)
    return points


def min_separation_tiles(points, frame_width):
    '''Smallest distance between two of ``points``, in tiles (inf for fewer than two).'''
    tile = TILE_FRAC * frame_width
    best = math.inf
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            best = min(best, math.dist(points[i], points[j]) / tile)
    return best


def outside_distance_tiles(hull, point, frame_width):
    '''How far ``point`` lies outside the hull, in tiles (negative = inside).'''
    contour = hull.reshape(-1, 1, 2).astype(np.float32)
    px = cv2.pointPolygonTest(contour, (float(point[0]), float(point[1])), True)
    return -px / (_TILE_STEP_FRAC * frame_width)
