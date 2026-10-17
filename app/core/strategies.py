import math
import time
import random
import cv2
from typing import Any, List, Optional, Tuple
from app.services.input import InputService
from app.services.vision import VisionService
from app.config import ASPECT_16_9, Config
from app.utils.logger import setup_logger
from app.utils.profile_settings_store import EARTHQUAKE_METHOD_CURVE, EARTHQUAKE_METHOD_RANDOM
logger = setup_logger('Strategies')
_EARTHQUAKE_REGION_ARC_SAMPLES = 49
_EARTHQUAKE_RANDOM_LINE_FROM_BOTTOM = (4, 10)
_EDRAG_COUNT = 12
_EDRAG_DELAY = 0.2
_EDRAG_CORNER_MARGIN = 100
_DIAMOND_EDGES = (('left', 'top'), ('top', 'right'))
_MAP_TILES = 44  # tiles along one edge of the village diamond (the left/top/right/bottom points)
# Troop drag: instead of a straight glide corner to corner, wander between random
# points of a band _DRAG_BAND_TILES thick centred on the old path. Every waypoint
# takes an independent sideways offset; the path through them is only half-smoothed
# (_DRAG_SMOOTHNESS: 0 = straight hops, 1 = full Catmull-Rom wave).
_DRAG_BAND_TILES = 3.5
_DRAG_WAYPOINT_TILES = (1.5, 3.0)  # spacing of the random waypoints along an edge
_DRAG_SMOOTHNESS = 0.55
# The path is sampled at irregular sub-tile steps (and irregular positions inside
# each step), so the cursor never paces a regular grid: troops drop between tiles.
_DRAG_SAMPLE_TILES = (0.2, 0.45)
_DRAG_SPEED_JITTER = 0.3  # each hop between two waypoints: its own pace, ±30%
# Near each corner the drag speeds up: two edges meet there, so the same pace would
# drop a double-thick clump of troops.
# The extra speed (+40%) itself varies ±30% at every corner (→ +28%..+52%), so the
# corners are not all thinned out the same way.
_DRAG_CORNER_TILES = 4.0
_DRAG_CORNER_SPEEDUP = 1.4
_DRAG_CORNER_SPEEDUP_JITTER = 0.3
# Heroes: random point anywhere on the diamond (corners avoided), pushed up to
# _HERO_OUTWARD_TILES outside it, inside the safe part of the screen.
_HERO_CORNER_MARGIN_TILES = 3.0
_HERO_OUTWARD_TILES = 1.5
_HERO_SAFE_Y_FRAC = (0.08, 0.76)  # above the troop bar, below the top HUD
_HERO_SAFE_X_FRAC = (0.02, 0.98)
_HERO_ABILITY_DELAY = (0.0, 10.0)  # seconds after each hero's own deployment

class AttackStrategy:
    '''Base class for attack strategies.'''
    
    def __init__(self, input_service, vision_service, config, stop_event = None, earthquake_method = EARTHQUAKE_METHOD_CURVE):
        self.input = input_service
        self.vision = vision_service
        self.config = config
        self.stop_event = stop_event
        self.earthquake_method = earthquake_method
        self.event_handler = None
        self.CORNER_ORDER = [
            'left',
            'top',
            'right',
            'bottom']

    
    def execute(self, frame, stop_event = None):
        raise NotImplementedError

    
    def _expand_loc(self, x, y):
        return (x + random.randint(-10, 10), y + random.randint(-10, 10))

    
    def _sync_frame_size(self, frame):
        self.config.set_target_size_from_frame(frame)

    def _reward_checkpoint(self, frame=None, selected=None):
        """Clear event overlays before input; reselect a displaced troop/spell.

        Return a current frame and whether a choice interrupted deployment.
        A missing capture or a stuck overlay must stop further battle clicks.
        """
        if self.stop_event and self.stop_event.is_set():
            raise InterruptedError('Bot stopped by user')
        if self.event_handler is None:
            return frame, False
        # Callers may retain a frame from before a previous deployment/choice.
        frame = self.input.window_service.screenshot()
        if frame is None:
            raise RuntimeError('Game capture unavailable during deployment')
        handled = self.event_handler.handle(frame)
        if handled:
            frame = self.input.window_service.screenshot()
            if frame is None:
                raise RuntimeError('Game capture unavailable after event choice')
            self._sync_frame_size(frame)
            if selected:
                roi = self.vision.bottom_half_region(frame)
                x, y = self.vision.find_template(frame, selected, region=roi)
                if x is None:
                    return None, True  # The previously selected troop is exhausted.
                self.input.click(x, y, pause=0.2, rand=False)
        return frame, handled

    
    def _point(self, key):
        return self.config.get_point(key)

    
    def _scaled_deployment_data(self):
        return { key: self._point(key) for key in self.CORNER_ORDER }
        key = None

    
    def deploy_heroes(self, frame):
        frame, _ = self._reward_checkpoint(frame)
        self._sync_frame_size(frame)
        heroes = [
            'queen',
            'warden',
            'RC',
            'king',
            'prince',
            'dragonduke']
        random.shuffle(heroes)
        deployed_heroes = []
        self._pending_abilities = []
        roi = self.vision.bottom_half_region(frame)
        (ix, iy) = self.vision.find_template(frame, 'loglauncher.png', threshold = 0.7, region = roi)
        if not ix:
            (ix, iy) = self.vision.find_template(frame, 'siegebarracks.png', threshold = 0.7, region = roi)
        if ix:
            deploy_point = self._random_hero_point(frame)
            self.input.click(ix, iy, pause = 0.2, rand = False)
            self.input.click(pause = 0.2, *deploy_point)
        for hero in heroes:
            fresh, interrupted = self._reward_checkpoint()
            if fresh is not None:
                frame = fresh
                roi = self.vision.bottom_half_region(frame)
            if interrupted:
                deployed_heroes = self._relocate_abilities(deployed_heroes, frame)
                self._pending_abilities = self._relocate_pending(self._pending_abilities, frame)
            (bx, by) = self.vision.find_template(frame, f'''{hero}.png''', threshold = 0.7, region = roi)
            if not bx:
                continue
            deploy_point = self._random_hero_point(frame)
            self.input.click(bx, by, pause = 0.2, rand = False)
            self.input.click(pause = 0.2, *deploy_point)
            # Remember the live, deployed appearance only for relocation after
            # a reward shifts the bar. Normal ability clicks retain main's slots.
            live = self.input.window_service.screenshot() if self.event_handler else frame
            radius = max(8, round(frame.shape[0]*.025))
            tile = None
            if live is not None and bx >= radius and by >= radius:
                tile = live[by-radius:by+radius, bx-radius:bx+radius].copy()
            deployed_heroes.append((bx, by, tile))
            # Each ability fires on its own clock: 0-10 s after THIS hero landed.
            due = time.monotonic() + random.uniform(*_HERO_ABILITY_DELAY)
            self._pending_abilities.append((due, bx, by, tile))

    def activate_hero_abilities(self):
        '''Fire the abilities scheduled by :meth:`deploy_heroes` when each one is due
        (spells go down meanwhile — call this after them). Same event-overlay
        handling as before: a reward that shifts the bar relocates the portraits.'''
        pending = sorted(getattr(self, '_pending_abilities', []), key = (lambda p: p[0]))
        self._pending_abilities = []
        while pending:
            wait = pending[0][0] - time.monotonic()
            if wait > 0:
                # Short naps so a stop or an event overlay is noticed while waiting.
                if self.stop_event:
                    if self.stop_event.wait(min(wait, 0.5)):
                        return
                else:
                    time.sleep(min(wait, 0.5))
                continue
            fresh, interrupted = self._reward_checkpoint()
            if interrupted:
                pending = self._relocate_pending(pending, fresh)
                if not pending:
                    break
                continue  # positions changed: re-check what is due
            (_due, hx, hy, _tile) = pending.pop(0)
            self.input.click(hx, hy, pause = 0.2)
            logger.info('Hero ability clicked at %d,%d', hx, hy)

    def _relocate_pending(self, pending, frame):
        '''Relocate scheduled abilities one by one so each keeps its own due time.'''
        out = []
        for (due, x, y, tile) in pending:
            moved = self._relocate_abilities([(x, y, tile)], frame)
            if moved:
                out.append((due,) + moved[0])
        return out

    def _relocate_abilities(self, heroes, frame):
        """Match cached live portraits only when an event actually moved slots."""
        if frame is None:
            return []
        top = frame.shape[0]//2
        roi = cv2.cvtColor(frame[top:], cv2.COLOR_BGR2GRAY)
        relocated = []
        for x, y, tile in heroes:
            if tile is None or not tile.size:
                continue
            gray = cv2.cvtColor(tile, cv2.COLOR_BGR2GRAY)
            _, score, _, loc = cv2.minMaxLoc(cv2.matchTemplate(roi, gray, cv2.TM_CCOEFF_NORMED))
            if score >= .65:
                relocated.append((loc[0]+tile.shape[1]//2, top+loc[1]+tile.shape[0]//2, tile))
            else:
                logger.info('Hero no longer recognizable after reward; skipping stale slot')
        return relocated

    
    def _hero_corner_xy(self, corner):
        '''Corner used when building hero deploy lines; on ``16_9``, ``top`` is nudge-scaled.'''
        (px, py) = self.config.get_point(corner)
        if self.config.aspect_key == ASPECT_16_9 and corner == 'top':
            py -= self.config.scale_scalar(70)
        return (int(px), int(py))

    
    @staticmethod
    def _quantize_deploy_to_frame(px, py, fw, fh):
        '''Clamp to ``[0, fw-1]`` x ``[0, fh-1]``, round to nearest pixels.'''
        if fw <= 0 or fh <= 0:
            return (int(round(px)), int(round(py)))
        cx = max(0, min(float(fw - 1), float(px)))
        cy = max(0, min(float(fh - 1), float(py)))
        return (int(round(cx)), int(round(cy)))

    
    def _get_hero_deploy_point(self, frame = None):
        c_name = random.choice([
            'top',
            'right',
            'left'])
        (c1x, c1y) = self._hero_corner_xy(c_name)
        if c_name in ('left', 'right'):
            (c2x, c2y) = self._hero_corner_xy('top')
        else:
            corner = random.choice([
                'left',
                'right'])
            (c2x, c2y) = self._hero_corner_xy(corner)
        t = random.uniform(0, 1)
        xf = c1x + (c2x - c1x) * t
        yf = c1y + (c2y - c1y) * t
        if frame is not None and getattr(frame, 'size', 0):  # [recovered: decompiler dropped the `not`]
            (fh, fw) = frame.shape[:2]
            return self._quantize_deploy_to_frame(xf, yf, fw, fh)
        return (int(round(xf)), int(round(yf)))

    
    @staticmethod
    def _earthquake_anchor_triplet(data, offset):
        '''Left / top / right drop anchors (same nudge as legacy earthquake logic).'''
        (lx, ly) = data['left']
        lx += int(offset * 1.3)
        (tx, ty) = data['top']
        ty += int(offset)
        (rx, ry) = data['right']
        rx -= int(offset * 1.3)
        return ((float(lx), float(ly)), (float(tx), float(ty)), (float(rx), float(ry)))

    
    @staticmethod
    def _sample_arc_through_three(ltr, n):
        '''
``n`` points along a circular arc from L to R that passes through T.
If L,T,R are collinear, uses a quadratic Bezier with control point chosen so t=0.5 hits T.
'''
        (L, T, R) = ltr
        (ax, ay) = L
        (bx, by) = T
        (cx, cy) = R
        d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        if n < 2:
            return [
                (int(round(L[0])), int(round(L[1])))]
        if abs(d) < 1e-06:
            p1x = 2 * bx - 0.5 * ax - 0.5 * cx
            p1y = 2 * by - 0.5 * ay - 0.5 * cy
            out = []
            for i in range(n):
                t = i / (n - 1)
                u = 1 - t
                x = u * u * ax + 2 * u * t * p1x + t * t * cx
                y = u * u * ay + 2 * u * t * p1y + t * t * cy
                out.append((int(round(x)), int(round(y))))
            return out
        a2 = ax * ax + ay * ay
        b2 = bx * bx + by * by
        c2 = cx * cx + cy * cy
        ox = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
        oy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
        r = math.hypot(ax - ox, ay - oy)
        
        def ang(p):
            return math.atan2(p[1] - oy, p[0] - ox)

        phi_r = ang(R)
        phi_t = ang(T)
        phi_l = ang(L)
        two_pi = 2 * math.pi
        ccw_span = (phi_r - phi_l) % two_pi
        t_ccw = (phi_t - phi_l) % two_pi
        if t_ccw <= ccw_span:
            sweep = ccw_span
        else:
            sweep = ccw_span - two_pi
        out = []
        for i in range(n):
            t = i / (n - 1)
            phi = phi_l + t * sweep
            x = ox + r * math.cos(phi)
            y = oy + r * math.sin(phi)
            out.append((int(round(x)), int(round(y))))
        return out

    
    @staticmethod
    def _earthquake_horizontal_y(frame_h, from_bottom_num, from_bottom_den):
        '''Row ``y`` for a line ``from_bottom_num/from_bottom_den`` of the way from bottom to top.'''
        if frame_h <= 0:
            return 0
        h = frame_h
        f = from_bottom_num / float(from_bottom_den)
        return int(round((h - 1) * (1 - f)))

    
    @staticmethod
    def _earthquake_fill_polygon(arc_pts, y_line):
        '''Closed polygon: arc polyline (left→right) then segment along ``y=y_line`` back to start.'''
        if len(arc_pts) < 2:
            return list(arc_pts)
        (x0, y0) = arc_pts[0]
        (x1, y1) = arc_pts[-1]
        return list(arc_pts) + [
            (x1, y_line),
            (x0, y_line)]

    
    @staticmethod
    def _polygon_double_area(poly):
        if len(poly) < 3:
            return 0
        a = 0
        n = len(poly)
        for i in range(n):
            (x1, y1) = poly[i]
            (x2, y2) = poly[(i + 1) % n]
            a += x1 * y2 - x2 * y1
        return a

    
    @staticmethod
    def _point_in_polygon(px, py, poly):
        '''Even-odd ray test; ``poly`` closed implicitly (last vertex → first not repeated).'''
        n = len(poly)
        if n < 3:
            return False
        inside = False
        j = n - 1
        for i in range(n):
            (ix, iy) = poly[i]
            (jx, jy) = poly[j]
            if (iy > py) != (jy > py):
                x_at = (jx - ix) * (py - iy) / (jy - iy) + ix
                if px < x_at:
                    inside = not inside
            j = i
        return inside

    
    @staticmethod
    def _random_points_in_polygon(poly, frame_w, frame_h, n_points):
        xs = [ p[0] for p in poly ]
        ys = [ p[1] for p in poly ]
        min_x = max(0, min(xs))
        max_x = min(frame_w - 1, max(xs))
        min_y = max(0, min(ys))
        max_y = min(frame_h - 1, max(ys))
        out = []
        if max_x < min_x or max_y < min_y:
            return out
        for _ in range(n_points):
            for _try in range(1000):
                rx = random.randint(min_x, max_x)
                ry = random.randint(min_y, max_y)
                if not AttackStrategy._point_in_polygon(rx, ry, poly):
                    continue
                out.append((rx, ry))
                break  # [recovered: decompiler dropped this break — every in-polygon sample was appended]
            else:
                (ax, ay) = poly[max(1, len(poly) // 4)]
                out.append((max(0, min(frame_w - 1, ax)), max(0, min(frame_h - 1, ay))))
        return out

    
    def _earthquake_curve_points_with_jitter(self, ltr):
        points = self._sample_arc_through_three(ltr, 11)
        if random.choice((True, False)):
            points.reverse()
        jitter_px = 100
        return [ (cx + random.randint(-jitter_px, jitter_px), cy + random.randint(-jitter_px, jitter_px)) for cx, cy in points ]
        cy = None
        cx = None

    
    # ---- humanized geometry ----

    def _tile_px(self):
        '''Length of one tile along a diamond edge, in current screen pixels.'''
        (lx, ly) = self._point('left')
        (tx, ty) = self._point('top')
        return max(4.0, math.hypot(tx - lx, ty - ly) / _MAP_TILES)

    def _diamond_center(self):
        pts = [self._point(c) for c in self.CORNER_ORDER]
        return (sum(p[0] for p in pts) / 4.0, sum(p[1] for p in pts) / 4.0)

    def _band_segment(self, start, a, b, offset, tile):
        '''Path from ``start`` (where the mouse is) toward corner ``b`` of edge a→b,
        through random points of the band, half-smoothed and sampled at irregular
        sub-tile steps. ``offset`` is the current sideways offset (pixels, + = outward);
        returns (dense path, end point, final offset, one speed factor per path span —
        each hop ±30%, faster within _DRAG_CORNER_TILES of either corner).'''
        (ax, ay) = a
        (bx, by) = b
        length = math.hypot(bx - ax, by - ay) or 1.0
        (ux, uy) = ((bx - ax) / length, (by - ay) / length)
        (nx, ny) = (-uy, ux)
        (cx, cy) = self._diamond_center()
        if nx * (ax - cx) + ny * (ay - cy) < 0:
            (nx, ny) = (-nx, -ny)  # normal points away from the village
        half = _DRAG_BAND_TILES * tile / 2.0
        waypoints = [start]
        along = [0.0]  # distance of each waypoint along the edge
        d = random.uniform(*_DRAG_WAYPOINT_TILES) * tile
        while d < length - _DRAG_WAYPOINT_TILES[0] * tile:
            offset = random.uniform(-half, half)
            waypoints.append((ax + ux * d + nx * offset, ay + uy * d + ny * offset))
            along.append(d)
            d += random.uniform(*_DRAG_WAYPOINT_TILES) * tile
        offset = random.uniform(-half, half)
        end = (bx + nx * offset, by + ny * offset)
        waypoints.append(end)
        along.append(length)
        corner = _DRAG_CORNER_TILES * tile
        boost = [1.0 + (_DRAG_CORNER_SPEEDUP - 1.0) * random.uniform(1 - _DRAG_CORNER_SPEEDUP_JITTER, 1 + _DRAG_CORNER_SPEEDUP_JITTER)
                 for _ in range(2)]  # start corner, end corner: each its own extra speed
        hop_speeds = []
        for (d1, d2) in zip(along, along[1:]):
            mid = (d1 + d2) / 2.0
            base = boost[0] if mid < corner else boost[1] if mid > length - corner else 1.0
            hop_speeds.append(base * random.uniform(1 - _DRAG_SPEED_JITTER, 1 + _DRAG_SPEED_JITTER))
        # Half-smoothed curve through the waypoints, sampled at irregular sub-tile steps.
        padded = [waypoints[0]] + waypoints + [waypoints[-1]]
        path = [start]
        speeds = []
        for k in range(len(waypoints) - 1):
            (p0, p1, p2, p3) = padded[k:k + 4]
            hop = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            n = max(2, int(round(hop / (random.uniform(*_DRAG_SAMPLE_TILES) * tile))))
            for j in range(1, n + 1):
                t = 1.0 if j == n else (j + random.uniform(-0.35, 0.35)) / n
                (cx_, cy_) = self._catmull_rom(p0, p1, p2, p3, t)
                (lx_, ly_) = (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)
                (qx, qy) = (lx_ + (cx_ - lx_) * _DRAG_SMOOTHNESS, ly_ + (cy_ - ly_) * _DRAG_SMOOTHNESS)
                # Keep the curve's small overshoot inside the band.
                side = (qx - ax) * nx + (qy - ay) * ny
                if abs(side) > half:
                    excess = side - math.copysign(half, side)
                    (qx, qy) = (qx - nx * excess, qy - ny * excess)
                path.append((qx, qy))
                speeds.append(hop_speeds[k])
        path[-1] = end
        return (path, end, offset, speeds)

    @staticmethod
    def _catmull_rom(p0, p1, p2, p3, t):
        '''Uniform Catmull-Rom point between p1 and p2 (t in 0..1).'''
        t2 = t * t
        t3 = t2 * t
        return tuple(0.5 * (2 * p1[i] + (p2[i] - p0[i]) * t + (2 * p0[i] - 5 * p1[i] + 4 * p2[i] - p3[i]) * t2
                            + (3 * p1[i] - p0[i] - 3 * p2[i] + p3[i]) * t3) for i in range(2))

    def _random_hero_point(self, frame):
        '''Anywhere on the diamond's perimeter (not near a corner), pushed 0-1.5 tiles
        outward, inside the safe screen area; falls back to the old edge pick.'''
        (fh, fw) = frame.shape[:2]
        tile = self._tile_px()
        edges = [(self.CORNER_ORDER[i], self.CORNER_ORDER[(i + 1) % 4]) for i in range(4)]
        (cx, cy) = self._diamond_center()
        for _ in range(25):
            (c1, c2) = random.choice(edges)
            (x1, y1) = self._point(c1)
            (x2, y2) = self._point(c2)
            length = math.hypot(x2 - x1, y2 - y1)
            margin = _HERO_CORNER_MARGIN_TILES * tile
            if length <= 2 * margin:
                continue
            t = random.uniform(margin / length, 1 - margin / length)
            (px, py) = (x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
            (vx, vy) = (px - cx, py - cy)
            norm = math.hypot(vx, vy) or 1.0
            push = random.uniform(0, _HERO_OUTWARD_TILES) * tile
            (px, py) = (px + vx / norm * push, py + vy / norm * push)
            if (fw * _HERO_SAFE_X_FRAC[0] <= px <= fw * _HERO_SAFE_X_FRAC[1]
                    and fh * _HERO_SAFE_Y_FRAC[0] <= py <= fh * _HERO_SAFE_Y_FRAC[1]):
                return self._quantize_deploy_to_frame(px, py, fw, fh)
        return self._get_hero_deploy_point(frame)

    def _random_diamond_perimeter_point(self, frame):
        (c1, c2) = random.choice(_DIAMOND_EDGES)
        (x1, y1) = self._point(c1)
        (x2, y2) = self._point(c2)
        edge_len = math.hypot(x2 - x1, y2 - y1)
        if edge_len <= 2 * _EDRAG_CORNER_MARGIN:
            t = 0.5
        else:
            t_min = _EDRAG_CORNER_MARGIN / edge_len
            t_max = 1 - t_min
            t = random.uniform(t_min, t_max)
        xf = x1 + (x2 - x1) * t
        yf = y1 + (y2 - y1) * t
        (fh, fw) = frame.shape[:2]
        return self._quantize_deploy_to_frame(xf, yf, fw, fh)

    
    @staticmethod
    def _point_on_polyline_at_distance(vertices, distance):
        '''Point ``distance`` pixels along a polyline from the first vertex.'''
        if not vertices:
            return (0, 0)
        if len(vertices) == 1:
            return (float(vertices[0][0]), float(vertices[0][1]))
        remaining = max(0, float(distance))
        # [recovered: pycdc reversed every dual-store here, transposing x/y mid-walk — verified against bytecode]
        (x0, y0) = (float(vertices[0][0]), float(vertices[0][1]))
        for i in range(len(vertices) - 1):
            (x1, y1) = (float(vertices[i + 1][0]), float(vertices[i + 1][1]))
            seg_len = math.hypot(x1 - x0, y1 - y0)
            if seg_len <= 0:
                (x0, y0) = (x1, y1)
                continue
            if remaining <= seg_len:
                t = remaining / seg_len
                return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
            remaining -= seg_len
            (x0, y0) = (x1, y1)
        return (x0, y0)

    
    def _even_diamond_top_perimeter_points(self, frame, count, *, deviation_frac = 0.1, reserve_top_corner_slot = False):
        '''
Evenly spaced deploy clicks along left→top→right diamond edges (Edrag front),
with ±``deviation_frac`` jitter per slot and corner margin clamping.

When ``reserve_top_corner_slot`` is set, spacing uses ``count + 1`` slots and the
slot nearest the top vertex is left empty (virtual troop at the apex).
'''
        if count <= 0:
            return []
        vertices = [ tuple(self._point(corner)) for corner in ('left', 'top', 'right') ]
        seg_lens = [ math.hypot(vertices[i + 1][0] - vertices[i][0], vertices[i + 1][1] - vertices[i][1]) for i in range(len(vertices) - 1) ]
        total_len = sum(seg_lens)
        margin = float(self.config.scale_scalar(_EDRAG_CORNER_MARGIN))
        start_d = margin
        end_d = total_len - margin
        span = end_d - start_d
        (fh, fw) = frame.shape[:2]
        if span <= 0:
            mid = self._point_on_polyline_at_distance(vertices, total_len / 2)
            return [
                self._quantize_deploy_to_frame(mid[0], mid[1], fw, fh)]
        slot_count = count + 1 if reserve_top_corner_slot else count
        spacing = span / slot_count
        slot_distances = []
        for i in range(slot_count):
            d = start_d + (i + 0.5) * spacing
            d += random.uniform(-deviation_frac, deviation_frac) * spacing
            d = max(start_d, min(end_d, d))
            slot_distances.append(d)
        skip_idx = None
        if reserve_top_corner_slot and slot_count > 1:
            top_d = seg_lens[0]
            skip_idx = min(range(slot_count), key = (lambda i: abs(slot_distances[i] - top_d)))
        out = []
        for i, d in enumerate(slot_distances):
            if i == skip_idx:
                continue
            (xf, yf) = self._point_on_polyline_at_distance(vertices, d)
            out.append(self._quantize_deploy_to_frame(xf, yf, fw, fh))
        return out
        corner = None
        i = None

    
    def _deploy_diamond_perimeter_troop(self, frame, template_name, stop_event = None, *, count = _EDRAG_COUNT, delay = _EDRAG_DELAY):
        '''Select troop in the bottom bar and click ``count`` points on the diamond perimeter.'''
        ev = stop_event or self.stop_event
        frame, _ = self._reward_checkpoint(frame)
        roi = self.vision.bottom_half_region(frame)
        (tx, ty) = self.vision.find_template(frame, template_name, region = roi)
        if tx is None:
            return False
        self.input.click(tx, ty, pause = 0.3, rand = False)
        if ev and ev.wait(0.2):
            return True
        for _ in range(count):
            if ev and ev.is_set():
                range(count)
                return True
            fresh, handled = self._reward_checkpoint(selected=template_name)
            if handled and fresh is None:
                break
            if fresh is not None:
                frame = fresh
            (px, py) = self._random_diamond_perimeter_point(frame)
            self.input.click(px, py, pause = delay, rand = False)
        return True

    
    def deploy_golden_drags_if_present(self, frame, stop_event = None):
        '''Optional Super Dragon deploy after main troops, before heroes.'''
        ev = stop_event or self.stop_event
        if self._deploy_diamond_perimeter_troop(frame, 'goldendrag.png', ev):
            logger.info('Deployed golden dragons')
        return bool(ev and ev.is_set())

    
    def deploy_spells(self, frame):
        frame, _ = self._reward_checkpoint(frame)
        self._sync_frame_size(frame)
        roi = self.vision.bottom_half_region(frame)
        (bx, by) = self.vision.find_template(frame, 'earthquake.png', region = roi)
        if bx:  # [recovered: decompiler turned `if` into `while`, causing endless earthquake spam after spells ran out]
            self.input.click(bx, by, pause = 0.2)
            offset = int(self.config.get_scaled('earthquake', 400))
            ltr = self._earthquake_anchor_triplet(self._scaled_deployment_data(), offset)
            (fh, fw) = frame.shape[:2]
            (num, den) = _EARTHQUAKE_RANDOM_LINE_FROM_BOTTOM
            y_line = self._earthquake_horizontal_y(fh, num, den)
            if self.earthquake_method == EARTHQUAKE_METHOD_RANDOM:
                arc_dense = self._sample_arc_through_three(ltr, _EARTHQUAKE_REGION_ARC_SAMPLES)
                if random.choice((True, False)):
                    arc_dense = arc_dense[::-1]
                poly = self._earthquake_fill_polygon(arc_dense, y_line)
                if abs(self._polygon_double_area(poly)) < 2:
                    logger.warning('Earthquake random region degenerate; using curve placement with jitter.')
                    points = self._earthquake_curve_points_with_jitter(ltr)
                else:
                    points = self._random_points_in_polygon(poly, fw, fh, 11)
            else:
                points = self._earthquake_curve_points_with_jitter(ltr)
            for cx, cy in points:
                fresh, handled = self._reward_checkpoint(selected='earthquake.png')
                if handled and fresh is None:
                    break
                jx = max(0, min(fw - 1, cx))
                jy = max(0, min(fh - 1, cy))
                self.input.click_at(jx, jy, rand = False)
                delay = random.uniform(0.1, 0.3)
                if self.stop_event:
                    self.stop_event.wait(delay)
                else:  # [recovered: decompiler dropped the else — both waits ran, doubling every spell delay]
                    time.sleep(delay)
        return None



class TroopSpamStrategy(AttackStrategy):
    
    def __init__(self, input_service, vision_service, config, stop_event, troop_name, duration, status_callback = None, earthquake_method = EARTHQUAKE_METHOD_CURVE):
        super().__init__(input_service, vision_service, config, stop_event, earthquake_method = earthquake_method)
        self.troop_name = troop_name
        self.duration = duration
        self.status_callback = status_callback

    
    def execute(self, frame, stop_event = None):
        ev = stop_event or self.stop_event
        frame, _ = self._reward_checkpoint(frame)
        self._sync_frame_size(frame)
        logger.info(f'''Executing {self.troop_name} strategy''')
        roi = self.vision.bottom_half_region(frame)
        (tx, ty) = self.vision.find_template(frame, f'''{self.troop_name}.png''', region = roi)
        if tx is None:
            msg = f'''Troop {self.troop_name} not found!'''
            logger.warning(msg)
            if self.status_callback:
                self.status_callback(msg)
            return False
        self.input.click(tx, ty, pause = 0.3, rand = False)
        if ev and ev.wait(0.2):
            return True
        corners = [
            'top',
            'right',
            'bottom',
            'left']
        if self.config.aspect_key == ASPECT_16_9:
            start_idx = random.choice([
                1,
                3])
        else:
            start_idx = random.choice([
                0,
                1,
                3])
        direction = random.choice([
            1,
            -1])
        ordered_corners = []
        for i in range(5):
            idx = (start_idx + i * direction) % 4
            ordered_corners.append(corners[idx])
        start_corner = ordered_corners[0]
        (curr_x, curr_y) = self._expand_loc(*self._point(start_corner))
        self.input.mouse_down(curr_x, curr_y)
        if ev and ev.wait(0.65):
            self.input.mouse_up(curr_x, curr_y)
            return True
        
        try:
            # A (min, max) duration is drawn again for every attack.
            total_duration = random.uniform(*self.duration) if isinstance(self.duration, tuple) else self.duration
            segment_duration = total_duration / 4
            tile = self._tile_px()
            offset = 0.0  # sideways position inside the band, carried across corners
            for i in range(len(ordered_corners) - 1):
                if ev and ev.is_set():
                    break  # [recovered: decompiler dropped this break]
                fresh, handled = self._reward_checkpoint(selected=f'{self.troop_name}.png')
                if handled:
                    if fresh is None:
                        break
                    self.input.mouse_down(curr_x, curr_y)
                a = self._point(ordered_corners[i])
                b = self._expand_loc(*self._point(ordered_corners[i + 1]))
                # Wander inside the band around the old corner-to-corner line, along a
                # half-smoothed random curve, each hop at its own pace (faster at corners).
                (path, end, offset, speeds) = self._band_segment((curr_x, curr_y), a, b, offset, tile)
                duration = random.uniform(segment_duration * 0.9, segment_duration * 1.1)
                self.input.drag_path(path, duration = duration, speed_jitter = 0.0, speeds = speeds)
                (curr_x, curr_y) = (int(end[0]), int(end[1]))
            self.input.mouse_up(curr_x, curr_y)
            if ev and ev.is_set():
                return True
            frame = self.input.window_service.screenshot()
            if not frame is None:
                self._sync_frame_size(frame)
                if self.deploy_golden_drags_if_present(frame, ev):
                    return True
                self.deploy_heroes(frame)
                if ev and ev.is_set():
                    return True
                frame = self.input.window_service.screenshot()
                if not frame is None:
                    self._sync_frame_size(frame)
                    self.deploy_spells(frame)
                self.activate_hero_abilities()
            return True
        finally:
            self.input.mouse_up(curr_x, curr_y)




class EdragStrategy(AttackStrategy):
    
    def __init__(self, input_service, vision_service, config, stop_event, status_callback = None, earthquake_method = EARTHQUAKE_METHOD_CURVE):
        super().__init__(input_service, vision_service, config, stop_event, earthquake_method = earthquake_method)
        self.status_callback = status_callback

    
    def execute(self, frame, stop_event = None):
        ev = stop_event or self.stop_event
        self._sync_frame_size(frame)
        logger.info('Executing edrag strategy')
        if not self._deploy_diamond_perimeter_troop(frame, 'edrag.png', ev):
            msg = 'Troop edrag not found!'
            logger.warning(msg)
            if self.status_callback:
                self.status_callback(msg)
            return False
        if ev and ev.is_set():
            return True
        frame = self.input.window_service.screenshot()
        if not frame is None:
            self._sync_frame_size(frame)
            if self.deploy_golden_drags_if_present(frame, ev):
                return True
            self.deploy_heroes(frame)
            if ev and ev.is_set():
                return True
            frame = self.input.window_service.screenshot()
            if not frame is None:
                self._sync_frame_size(frame)
                self.deploy_spells(frame)
            self.activate_hero_abilities()
        return True


