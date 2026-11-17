'''Wall row walk in the Build panel (UI October 2026, list re-sorted by the November 2026
update): the game sorts the list by what the loot can pay, so the Wall row can sit
anywhere — the walk goes down to the end of the list instead of a fixed 14 nudges.'''
import _testenv  # noqa: F401 — must precede the app imports (test log folder)
import unittest
from unittest.mock import Mock, patch

WALL_PRICE = 6000000


class Frame:

    def __init__(self, pos):
        self.pos = pos


class FakePanel:
    '''A list ``length`` nudges long; the wheel moves it one position per nudge (except the
    nudges listed in ``lost``, whose wheel event the game dropped).'''

    def __init__(self, length, lost = ()):
        self.length = length
        self.lost = set(lost)
        self.pos = 0
        self.scrolls = 0
        self.closed = False
        self.last_scroll_moved = None

    def open(self, reset_to_top = True):
        return True

    def frame(self):
        return Frame(self.pos)

    def scroll(self, clicks, upward = False):
        self.scrolls += 1
        self._before = self.pos
        if self.scrolls not in self.lost:
            self.pos = min(self.length, self.pos + 1)

    def wait_list_settled(self):
        self.last_scroll_moved = self.pos != self._before
        return self.frame()

    def close_all(self):
        self.closed = True


def rows_at(wall_at, price = WALL_PRICE):
    from app.core.upgrade_menu import SECTION_OTHER, UpgradeRow
    def parse(frame, initial_section = ''):
        rows = [UpgradeRow('Cannon', SECTION_OTHER, 9000000, 'gold', True, (2100, 400), 400)]
        if frame.pos == wall_at:
            rows.append(UpgradeRow('Wall', SECTION_OTHER, price, 'gold', True, (2030, 900), 900))
        return rows
    return parse


class WallWalkTests(unittest.TestCase):

    def walk(self, panel, wall_at, price = WALL_PRICE, hud = (20000000, 2400000, 0)):
        from app.config import Config
        from app.core.bot import Bot
        bot = Bot.__new__(Bot)
        bot.config = Config()
        bot.stop_event = Mock()
        bot.stop_event.is_set.return_value = False
        bot.stop_event.wait.return_value = False
        bot._check_stop = lambda: None
        bot._read_hud_triplet_stable = Mock(return_value = hud)
        bot._wall_costs = {WALL_PRICE}
        with patch('app.core.bot.BuildPanel', return_value = panel), patch('app.core.bot.parse_builder_menu', side_effect = rows_at(wall_at, price)):
            point = bot._find_wall_row_build_panel()
        return (bot, point)

    def test_wall_row_past_the_old_14_nudges_is_found(self):
        # Live 17/11/2026: with 14M gold + 2.4M elixir the Wall row sat past nudge 14 and
        # the walk gave up for an hour.
        panel = FakePanel(length = 30)
        (_bot, point) = self.walk(panel, wall_at = 20)
        self.assertEqual(point, (2030, 900))
        self.assertEqual(panel.scrolls, 20)
        self.assertFalse(panel.closed)

    def test_walk_stops_at_the_end_of_the_list(self):
        panel = FakePanel(length = 18)
        with self.assertLogs('BotCore', level = 'INFO') as logs:
            (bot, point) = self.walk(panel, wall_at = None)
        self.assertIsNone(point)
        self.assertTrue(panel.closed)
        self.assertEqual(panel.scrolls, 18 + 2)  # two nudges that move nothing = the end
        self.assertTrue(any('end of the list' in line for line in logs.output))
        self.assertEqual(bot._wall_costs, {WALL_PRICE})  # nothing seen: saved prices kept
        self.assertTrue(bot._wall_walk_reached_end)  # the Builder Base first look relies on it

    def test_one_lost_wheel_event_is_not_the_end(self):
        panel = FakePanel(length = 30, lost = (5,))
        (_bot, point) = self.walk(panel, wall_at = 12)
        self.assertEqual(point, (2030, 900))

    def test_whole_list_seen_replaces_the_saved_prices(self):
        panel = FakePanel(length = 25)
        (bot, point) = self.walk(panel, wall_at = 22, price = 30000000, hud = (20000000, 2400000, 0))
        self.assertIsNone(point)  # 30M per wall: not payable
        self.assertEqual(bot._wall_costs, {30000000})

    def test_safety_cap(self):
        from app.core.bot import _WALL_PANEL_MAX_NUDGES
        panel = FakePanel(length = 500)
        (bot, point) = self.walk(panel, wall_at = None)
        self.assertIsNone(point)
        self.assertEqual(panel.scrolls, _WALL_PANEL_MAX_NUDGES)
        self.assertEqual(bot._wall_costs, {WALL_PRICE})  # end not reached: prices not replaced
        self.assertFalse(bot._wall_walk_reached_end)


if __name__ == '__main__':
    unittest.main()
