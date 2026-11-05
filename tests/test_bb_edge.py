'''Baby Dragon edge deploy (Builder Base, both stages): red border → six zones 2-8 tiles
outside it, against real captures in screens/ (git-ignored: they show player names).'''
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

    def test_zones_two_to_eight_tiles_outside_the_border_on_the_floor(self):
        '''Full zoom-out only (the deploy always zooms out first): the floor limit is measured
        there. A zone with no room for 2 tiles before the floor edge / troop bar is skipped.'''
        from app.core import bb_edge
        for name in ('firstattackzoomout', 'secondattackzoomout', '2ndvillage'):
            frame = shot(name)
            (h, w) = frame.shape[:2]
            hull = bb_edge.border_hull(frame)
            field = np.array([[fx * w, fy * h] for (fx, fy) in bb_edge._FIELD_CORNERS], dtype = np.float32).reshape(-1, 1, 2)
            for seed in range(5):
                points = bb_edge.zone_points(frame, hull, random.Random(seed))
                self.assertGreaterEqual(len(points), 5, f'{name} seed {seed}')
                for p in points:
                    self.assertGreaterEqual(cv2.pointPolygonTest(field, (float(p[0]), float(p[1])), True), -2, f'{name} {p} off the floor')  # int rounding
                    tiles = bb_edge.outside_distance_tiles(hull, p, w)
                    self.assertGreaterEqual(tiles, 1.5, f'{name} {p}')
                    self.assertLessEqual(tiles, 8.5, f'{name} {p}')
                    self.assertTrue(0.14 * h <= p[1] <= 0.81 * h, f'{name} {p} on the HUD / troop bar')
                    self.assertFalse(p[0] < 0.20 * w and p[1] > 0.66 * h, f'{name} {p} on the buttons')

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

    def test_one_dragon_per_zone_then_shared(self):
        from app.core import bb_edge
        zones = [(100 * i, 50) for i in range(6)]
        self.assertEqual(sorted(bb_edge.spread_over_zones(zones, 6, random.Random(1))), sorted(zones))
        drops = bb_edge.spread_over_zones(zones, 8, random.Random(1))
        self.assertEqual(len(drops), 8)
        self.assertEqual(len({min(range(6), key = lambda i: abs(zones[i][0] - x)) for (x, _y) in drops}), 6)


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

    def test_stage_one_drops_six_dragons_on_the_zones(self):
        from app.core import bb_edge
        frame = shot('firstattackzoomout')
        bot = self.bot(frame)
        self.assertTrue(bot._deploy_bb_baby_dragons(frame))
        clicks = [c.args[:2] for c in bot.input.click.call_args_list]
        self.assertEqual(len(clicks), 12)  # card + drop, six times
        hull = bb_edge.border_hull(frame)
        for (x, y) in clicks[1::2]:
            self.assertGreater(bb_edge.outside_distance_tiles(hull, (x, y), frame.shape[1]), 0.5)
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

    def test_elixir_mode_skips_abilities(self):
        frame = shot('firstattackzoomout')
        bot = self.bot(frame)
        bot._loot_prioritise = 'elixir'
        bot._deploy_bb_baby_dragons(frame)
        bot._bb_activate_abilities.assert_not_called()


if __name__ == '__main__':
    unittest.main()
