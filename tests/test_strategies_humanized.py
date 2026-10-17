'''Humanized deployment: troop drag band, random hero points, delayed abilities.'''
import _testenv  # noqa: F401 — must precede the app imports (test log folder)
import math
import random
import threading
import time
import unittest
from unittest.mock import Mock

import numpy as np

from app.config import Config
from app.core import strategies as st
from app.core.strategies import TroopSpamStrategy


def strategy():
    cfg = Config()
    frame = np.zeros((1440, 2560, 3), np.uint8)
    cfg.set_target_size_from_frame(frame)
    s = TroopSpamStrategy(Mock(), Mock(), cfg, None, 'valkyrie', 5.5)
    return s, frame


def distance_to_segment(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    (dx, dy) = (bx - ax, by - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


class DragBandTests(unittest.TestCase):

    def test_path_is_a_gentle_curve_inside_the_band(self):
        (s, _frame) = strategy()
        tile = s._tile_px()
        half = st._DRAG_BAND_TILES * tile / 2
        random.seed(7)
        for _ in range(30):
            (a, b) = (s._point('right'), s._point('top'))
            (path, end, offset, speeds) = s._band_segment(a, a, b, 0.0, tile)
            self.assertLessEqual(abs(offset), half + 1e-6)
            for p in path:
                self.assertLessEqual(distance_to_segment(p, a, b), half + 1e-6)
            self.assertEqual(path[-1], end)
            self.assertEqual(len(speeds), len(path) - 1)
            steps = [math.hypot(q[0] - p[0], q[1] - p[1]) / tile for p, q in zip(path[1:], path[2:])]
            self.assertGreater(len(path), 40)  # dense, a curve not a few straight hops
            self.assertLess(max(steps), 1.0)
            # Irregular sub-tile steps: the cursor does not pace a tile grid.
            mean = sum(steps) / len(steps)
            spread = math.sqrt(sum((x - mean) ** 2 for x in steps) / len(steps))
            self.assertGreater(spread / mean, 0.15)

    def test_corners_are_faster_by_a_varying_amount(self):
        (s, _frame) = strategy()
        tile = s._tile_px()
        (a, b) = (s._point('left'), s._point('top'))
        random.seed(5)
        corner, middle = [], []
        for _ in range(200):
            speeds = s._band_segment(a, a, b, 0.0, tile)[3]
            corner += [speeds[0], speeds[-1]]
            middle.append(speeds[len(speeds) // 2])
        lo = (1 + (st._DRAG_CORNER_SPEEDUP - 1) * (1 - st._DRAG_CORNER_SPEEDUP_JITTER)) * (1 - st._DRAG_SPEED_JITTER)
        hi = (1 + (st._DRAG_CORNER_SPEEDUP - 1) * (1 + st._DRAG_CORNER_SPEEDUP_JITTER)) * (1 + st._DRAG_SPEED_JITTER)
        self.assertTrue(all(lo - 1e-9 <= v <= hi + 1e-9 for v in corner))
        self.assertGreater(sum(corner) / len(corner), sum(middle) / len(middle) * 1.25)
        self.assertGreater(len({round(v, 4) for v in corner}), 300)  # never one fixed corner speed

    def test_paths_differ_run_to_run(self):
        (s, _frame) = strategy()
        tile = s._tile_px()
        (a, b) = (s._point('left'), s._point('top'))
        random.seed(1)
        p1 = s._band_segment(a, a, b, 0.0, tile)[0]
        p2 = s._band_segment(a, a, b, 0.0, tile)[0]
        self.assertNotEqual([tuple(map(round, p)) for p in p1[:10]], [tuple(map(round, p)) for p in p2[:10]])


class HeroPointTests(unittest.TestCase):

    def test_points_are_spread_and_safe(self):
        (s, frame) = strategy()
        (fh, fw) = frame.shape[:2]
        random.seed(3)
        points = [s._random_hero_point(frame) for _ in range(200)]
        for (x, y) in points:
            self.assertTrue(fh * st._HERO_SAFE_Y_FRAC[0] <= y <= fh * st._HERO_SAFE_Y_FRAC[1], (x, y))
            self.assertTrue(fw * st._HERO_SAFE_X_FRAC[0] <= x <= fw * st._HERO_SAFE_X_FRAC[1], (x, y))
        # Not two fixed edges any more: points on both halves of the map, left and right of center.
        self.assertTrue(any(x < fw * 0.3 for x, _ in points) and any(x > fw * 0.7 for x, _ in points))
        self.assertTrue(any(y > fh * 0.55 for _, y in points))  # lower edges used too
        self.assertGreater(len(set(points)), 150)


class AbilityDelayTests(unittest.TestCase):

    def test_abilities_fire_on_their_own_clock(self):
        (s, _frame) = strategy()
        stop = threading.Event()
        s.stop_event = stop
        clicks = []
        s.input.click.side_effect = lambda x, y, pause = 0: clicks.append((time.monotonic(), x))
        now = time.monotonic()
        s._pending_abilities = [(now + 0.6, 2, 0, None), (now + 0.0, 1, 0, None), (now + 0.3, 3, 0, None)]
        s.activate_hero_abilities()
        self.assertEqual([x for _t, x in clicks], [1, 3, 2])  # in due order, not deploy order
        self.assertGreaterEqual(clicks[-1][0] - now, 0.55)

    def test_delays_within_0_10_seconds(self):
        self.assertEqual(st._HERO_ABILITY_DELAY, (0.0, 10.0))

    def test_stop_interrupts_the_wait(self):
        (s, _frame) = strategy()
        stop = threading.Event()
        stop.set()
        s.stop_event = stop
        s._pending_abilities = [(time.monotonic() + 5, 1, 0, None)]
        started = time.monotonic()
        s.activate_hero_abilities()
        self.assertLess(time.monotonic() - started, 1.0)
        s.input.click.assert_not_called()


if __name__ == '__main__':
    unittest.main()
