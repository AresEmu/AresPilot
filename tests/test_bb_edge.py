'''Baby Dragon edge deploy (Builder Base, both stages): red border → one drop per dragon 2-8
tiles outside it, spread apart, against real captures in screens/ (git-ignored: they show
player names) and synthetic frames.'''
import _testenv  # noqa: F401 — must precede the app imports (test log folder)
import random
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
import numpy as np

SCREENS = Path(__file__).resolve().parent.parent / 'screens'
NAMES = ('firstattacknozoom', 'firstattackzoomout', 'secondattacknozoom', 'secondattackzoomout', '2ndvillage')
HAVE_SCREENS = all((SCREENS / f'bb_edge_{n}.png').exists() for n in NAMES)


def shot(name):
    return cv2.imread(str(SCREENS / f'bb_edge_{name}.png'))


@unittest.skipUnless(HAVE_SCREENS, 'screens/ with the Builder Base edge captures not available')
class BorderTests(unittest.TestCase):

    def test_border_found_in_both_stages(self):
        from app.core import bb_edge
        for name in NAMES:
            frame = shot(name)
            hull = bb_edge.border_hull(frame)
            self.assertIsNotNone(hull, name)
            (_x, _y, bw, bh) = cv2.boundingRect(hull)
            (h, w) = frame.shape[:2]
            self.assertGreater(bw, 0.15 * w, name)
            self.assertGreater(bh, 0.25 * h, name)

    def test_drops_two_to_eight_tiles_outside_the_border_on_the_floor(self):
        '''Full zoom-out only (the deploy always zooms out first): the floor limit is measured
        there.'''
        from app.core import bb_edge
        for name in ('firstattackzoomout', 'secondattackzoomout', '2ndvillage'):
            frame = shot(name)
            (h, w) = frame.shape[:2]
            hull = bb_edge.border_hull(frame)
            field = np.array([[fx * w, fy * h] for (fx, fy) in bb_edge._FIELD_CORNERS], dtype = np.float32).reshape(-1, 1, 2)
            for seed in range(5):
                points = bb_edge.drop_points(frame, hull, 6, random.Random(seed))
                self.assertEqual(len(points), 6, f'{name} seed {seed}')
                for p in points:
                    self.assertGreaterEqual(cv2.pointPolygonTest(field, (float(p[0]), float(p[1])), True), -2, f'{name} {p} off the floor')  # int rounding
                    tiles = bb_edge.outside_distance_tiles(hull, p, w)
                    self.assertGreaterEqual(tiles, 1.5, f'{name} {p}')
                    self.assertLessEqual(tiles, 8.5, f'{name} {p}')
                    self.assertTrue(0.14 * h <= p[1] <= 0.81 * h, f'{name} {p} on the HUD / troop bar')
                    self.assertFalse(p[0] < 0.20 * w and p[1] > 0.66 * h, f'{name} {p} on the buttons')

    def test_dragons_are_never_stacked_on_real_villages(self):
        '''Live bug: two dragons on the same spot (a zone with no room slid onto its neighbour,
        or more dragons than free zones). Big villages leave room on some sides only.'''
        from app.core import bb_edge
        for name in ('firstattackzoomout', 'secondattackzoomout', '2ndvillage'):
            frame = shot(name)
            hull = bb_edge.border_hull(frame)
            for (count, at_least) in ((6, 5.0), (8, 3.0)):
                for seed in range(30):
                    points = bb_edge.drop_points(frame, hull, count, random.Random(seed))
                    self.assertEqual(len(points), count)
                    sep = bb_edge.min_separation_tiles(points, frame.shape[1])
                    self.assertGreaterEqual(sep, at_least, f'{name} {count} dragons seed {seed}')

    @unittest.skipUnless((SCREENS / 'bb_stage2_missed.png').exists(), 'stage-2 capture without border not available')
    def test_fire_walls_and_damage_stars_are_not_a_border(self):
        '''Stage 2 mid-battle, no border shown: fire, wooden walls and the lit Overall Damage
        stars are red too — they once made a hull that sent the drops inside the village.'''
        from app.core import bb_edge
        frame = cv2.imread(str(SCREENS / 'bb_stage2_missed.png'))
        self.assertIsNone(bb_edge.border_hull(frame))

    def test_village_centre_is_on_the_village(self):
        from app.core import bb_edge
        for name in ('2ndvillage', 'firstattackzoomout', 'secondattackzoomout'):
            frame = shot(name)
            hull = bb_edge.border_hull(frame)
            centre = bb_edge.village_centre(frame)
            inside = cv2.pointPolygonTest(hull.astype(np.float32), (float(centre[0]), float(centre[1])), False)
            self.assertGreater(inside, 0, name)


class SpreadTests(unittest.TestCase):
    '''Synthetic 2560x1440 frame: a village of the usual size in the middle of the floor.'''

    def setUp(self):
        from app.core import bb_edge
        self.frame = np.zeros((1440, 2560, 3), dtype = np.uint8)
        self.hull = bb_edge.synthetic_hull((1220, 700), self.frame)
        self.w = self.frame.shape[1]

    def test_six_dragons_spread_all_around_and_apart(self):
        from app.core import bb_edge
        centre = bb_edge.hull_centre(self.hull)
        for seed in range(20):
            points = bb_edge.drop_points(self.frame, self.hull, 6, random.Random(seed))
            self.assertEqual(len(points), 6)
            self.assertGreaterEqual(bb_edge.min_separation_tiles(points, self.w), bb_edge.SEPARATION_TILES, seed)
            angles = sorted(float(np.degrees(np.arctan2(y - centre[1], x - centre[0]))) % 360 for (x, y) in points)
            gaps = np.diff(angles + [angles[0] + 360])
            self.assertLess(max(gaps), 120, f'seed {seed}: a side left empty {angles}')

    def test_more_dragons_than_room_still_never_share_a_spot(self):
        from app.core import bb_edge
        points = bb_edge.drop_points(self.frame, self.hull, 11, random.Random(4))
        self.assertEqual(len(points), 11)
        self.assertGreaterEqual(bb_edge.min_separation_tiles(points, self.w), 2.0)

    def test_retry_drops_keep_away_from_the_first_ones(self):
        from app.core import bb_edge
        first = bb_edge.drop_points(self.frame, self.hull, 6, random.Random(1))
        retry = bb_edge.drop_points(self.frame, self.hull, 2, random.Random(2), distance = (2.0, 3.0), avoid = first)
        self.assertEqual(len(retry), 2)
        self.assertGreaterEqual(bb_edge.min_separation_tiles(first + retry, self.w), 3.0)
        for p in retry:
            self.assertLessEqual(bb_edge.outside_distance_tiles(self.hull, p, self.w), 3.5)

    def test_no_free_spot_gives_no_drop(self):
        from app.core import bb_edge
        whole = np.array([[0, 0], [2559, 0], [2559, 1439], [0, 1439]], dtype = np.int32).reshape(-1, 1, 2)
        self.assertEqual(bb_edge.drop_points(self.frame, whole, 6, random.Random(0)), [])


@unittest.skipUnless(HAVE_SCREENS, 'screens/ with the Builder Base edge captures not available')
class DeployTests(unittest.TestCase):

    def bot(self, frame):
        from app.config import Config
        from app.core.bot import Bot
        bot = Bot.__new__(Bot)
        bot.config = Config()
        bot.config.set_target_size_from_frame(frame)
        bot.stop_event = Mock()
        bot.stop_event.is_set.return_value = False
        bot.stop_event.wait.return_value = False
        bot.window = Mock()
        bot.window.screenshot.return_value = frame
        bot._update_config_size = Mock()
        bot.vision = Mock()
        bot.vision.find_template.return_value = (None, None)  # no machine on these bars
        bot.input = Mock()
        bot._loot_prioritise = 'both'
        bot._bb_activate_abilities = Mock()
        bot._bb_undeployed_slots = Mock(return_value = [])  # every drop taken by the game
        return bot

    def test_stage_one_drops_six_dragons_apart(self):
        from app.core import bb_edge
        frame = shot('firstattackzoomout')
        bot = self.bot(frame)
        self.assertTrue(bot._deploy_bb_baby_dragons(frame))
        clicks = [c.args[:2] for c in bot.input.click.call_args_list]
        self.assertEqual(len(clicks), 12)  # card + drop, six times
        hull = bb_edge.border_hull(frame)
        for (x, y) in clicks[1::2]:
            self.assertGreater(bb_edge.outside_distance_tiles(hull, (x, y), frame.shape[1]), 0.5)
        self.assertGreaterEqual(bb_edge.min_separation_tiles(clicks[1::2], frame.shape[1]), 4.0)
        bot._bb_activate_abilities.assert_called_once()

    def test_stage_two_uses_survivors_and_fresh_cards_only(self):
        frame = shot('2ndvillage')
        bot = self.bot(frame)
        (cards, machine) = bot._bb_dragon_cards(frame)
        self.assertEqual(len(cards), 5)  # cards 2, 3, 6 alive + 7, 8 fresh; 1, 4, 5 dead
        self.assertIsNone(machine)
        self.assertEqual(bot._bb_trophy_deploy_stage2(frame), 5)
        clicks = [c.args[:2] for c in bot.input.click.call_args_list]
        self.assertEqual(len(clicks), 2 + 10)  # reveal tap (card + village) + card/drop x5

    def test_switch_button_marks_the_cards_not_deployed_yet(self):
        from app.core.bot import Bot
        self.assertEqual(len(Bot._bb_undeployed_slots(shot('firstattackzoomout'))), 6)
        # Stage 2: survivors 2, 3, 6 and dead 1, 4, 5 have no switch; fresh 7, 8 do.
        fresh = Bot._bb_undeployed_slots(shot('2ndvillage'))
        (cards, _machine) = self.bot(shot('2ndvillage'))._bb_dragon_cards(shot('2ndvillage'))
        self.assertEqual(fresh, cards[-2:])

    def test_missed_dragon_is_dropped_again_closer_to_the_border(self):
        from app.core import bb_edge
        frame = shot('firstattackzoomout')
        bot = self.bot(frame)
        (cards, _machine) = bot._bb_dragon_cards(frame)
        bot._bb_undeployed_slots = Mock(side_effect = [[cards[2]], [cards[2]], []])
        self.assertTrue(bot._deploy_bb_baby_dragons(frame))
        clicks = [c.args[:2] for c in bot.input.click.call_args_list]
        self.assertEqual(len(clicks), 12 + 2 + 2)  # six dragons, then card 3 retried twice
        self.assertEqual(clicks[12], cards[2])
        self.assertEqual(clicks[14], cards[2])
        hull = bb_edge.border_hull(frame)
        for drop in (clicks[13], clicks[15]):
            self.assertLessEqual(bb_edge.outside_distance_tiles(hull, drop, frame.shape[1]), 3.5)
        # The retries land away from the six first drops and from each other.
        self.assertGreaterEqual(bb_edge.min_separation_tiles(clicks[1:12:2] + [clicks[13], clicks[15]], frame.shape[1]), 2.0)

    def test_retries_stop_after_the_limit(self):
        from app.core.bot import _BB_DEPLOY_RETRIES
        frame = shot('firstattackzoomout')
        bot = self.bot(frame)
        (cards, _machine) = bot._bb_dragon_cards(frame)
        bot._bb_undeployed_slots = Mock(return_value = [cards[0]])
        with self.assertLogs('BotCore', level = 'WARNING'):
            bot._deploy_bb_baby_dragons(frame)
        self.assertEqual(bot.input.click.call_count, 12 + 2 * _BB_DEPLOY_RETRIES)

    def test_cards_tapped_above_the_switch_button(self):
        for name in ('firstattackzoomout', '2ndvillage'):
            frame = shot(name)
            h = frame.shape[0]
            (cards, _machine) = self.bot(frame)._bb_dragon_cards(frame)
            self.assertTrue(cards, name)
            for (_x, y) in cards:
                self.assertTrue(0.88 * h <= y <= 0.92 * h, f'{name}: card tapped at y {y / h:.3f}')

    def test_abilities_fire_between_10_and_20_seconds(self):
        from app.core import bot as botmod
        self.assertEqual(botmod._BB_ABILITY_DELAY, (10.0, 20.0))
        frame = shot('firstattackzoomout')
        bot = self.bot(frame)
        del bot._bb_activate_abilities
        with patch('app.core.bot.random.uniform', return_value = 13.0) as uniform:
            bot._bb_activate_abilities([(10, 10), (20, 10)], (30, 10))
        uniform.assert_called_once_with(10.0, 20.0)
        bot.stop_event.wait.assert_called_once_with(13.0)
        self.assertEqual(bot.input.click.call_count, 3)

    def test_elixir_mode_skips_abilities(self):
        frame = shot('firstattackzoomout')
        bot = self.bot(frame)
        bot._loot_prioritise = 'elixir'
        bot._deploy_bb_baby_dragons(frame)
        bot._bb_activate_abilities.assert_not_called()


if __name__ == '__main__':
    unittest.main()
