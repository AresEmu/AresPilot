'''UI ottobre 2026 (16:9): Build panel parser, Confirm dialog reader and the upgrade
confirm flow, against real screenshots in screens/ (skipped when they are missing —
screens/ is git-ignored because it shows the account name).'''
import _testenv  # noqa: F401 — must precede the app imports (test log folder)
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

import cv2

ROOT = Path(__file__).resolve().parent.parent
SCREENS = ROOT / 'screens'
NEEDED = ('build_top.png', 'build_mid.png', 'build_bottom.png', 'build_wall.png', 'home.png',
          'row_building.png', 'row_building_redgold_dontupgrade.png', 'row_building_red_denygems.png',
          'row_hero.png', 'wall_confirm_gold.png', 'wall_confirm_elexir.png')
HAVE_SCREENS = all((SCREENS / n).exists() for n in NEEDED)


def shot(name):
    return cv2.imread(str(SCREENS / name))


@unittest.skipUnless(HAVE_SCREENS, 'screens/ with the October 2026 UI captures not available')
class BuildPanelReadTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from app.utils.tesseract_env import configure_tesseract
        configure_tesseract()

    def rows(self, name):
        from app.core.upgrade_menu import parse_builder_menu
        return parse_builder_menu(shot(name))

    def assertRows(self, name, expected):
        from app.core.upgrade_menu import _normalize_label
        got = [(r.cost, r.resource, r.affordable) for r in self.rows(name)]
        self.assertEqual(got, [e[1:] for e in expected], name)
        labels = [_normalize_label(r.label).replace(' ', '') for r in self.rows(name)]
        for (label, (want, *_rest)) in zip(labels, expected):
            self.assertIn(want, label, name)

    def test_top_of_list(self):
        self.assertRows('build_top.png', [
            ('barbarianking', 144000, 'dark_elixir', True),
            ('goldmine', 6400000, 'elixir', True),
            ('elixircollector', 6400000, 'gold', True),
            ('monolit', 208000, 'dark_elixir', True),
            ('champ', 176000, 'dark_elixir', True),
            ('minionprince', 120000, 'dark_elixir', True),
            ('craftingstation', 64000, 'dark_elixir', True)])

    def test_red_rows_are_unaffordable(self):
        self.assertRows('build_mid.png', [
            ('pethouse', 9600000, 'elixir', False),
            ('darkelixirdrill', 9600000, 'elixir', False),
            ('blacksm', 8800000, 'elixir', False),
            ('work', 8800000, 'elixir', False),
            ('darkelixirstorage', 8000000, 'elixir', False),
            ('craftingstation', 7200000, 'elixir', False),
            ('bombtower', 6800000, 'gold', True),
            ('hiddentesla', 6560000, 'gold', True),
            ("builder'shut", 6400000, 'gold', True),
            ('wizardtower', 6400000, 'gold', True)])

    def test_clipped_town_hall_row_is_dropped(self):
        # The Town Hall card is under the panel title: its junk label must not
        # become a row (it would dodge the maxer's Town Hall exclusion).
        rows = self.rows('build_bottom.png')
        self.assertNotIn(12800000, [r.cost for r in rows])
        self.assertEqual([r.cost for r in rows], [11200000, 10400000, 10400000, 9600000, 8800000, 7600000, 7200000])

    def test_wall_row(self):
        from app.core.upgrade_menu import is_wall_row
        walls = [r for r in self.rows('build_wall.png') if is_wall_row(r)]
        self.assertEqual(len(walls), 1)
        self.assertEqual((walls[0].cost, walls[0].resource, walls[0].affordable), (4000000, 'gold', True))

    def test_confirm_button(self):
        from app.core.build_panel import read_confirm_button
        cases = {
            'row_building.png': (6800000, False, 'gold'),
            'row_building_redgold_dontupgrade.png': (7600000, True, 'gold'),
            'row_hero.png': (176000, False, 'dark_elixir'),
            'wall_confirm_gold.png': (4000000, True, 'gold'),
            'wall_confirm_elexir.png': (4000000, False, 'elixir')}
        for (name, (price, red, resource)) in cases.items():
            button = read_confirm_button(shot(name))
            self.assertIsNotNone(button, name)
            self.assertEqual((button.price, button.red, button.resource), (price, red, resource), name)
            self.assertEqual(button.layout, 'gold_pass', name)  # discounted price over a struck one
        if (SCREENS / 'wallconfirm_from_build.png').exists():
            # Account without Gold Pass: yellow banner, no struck price, price lower.
            button = read_confirm_button(shot('wallconfirm_from_build.png'))
            self.assertIsNotNone(button)
            self.assertEqual((button.price, button.red, button.resource, button.layout),
                             (4000000, False, 'gold', 'no_gold_pass'))
        # Gem dialog on top dims the dialog: no Confirm to click.
        self.assertIsNone(read_confirm_button(shot('row_building_red_denygems.png')))
        self.assertIsNone(read_confirm_button(shot('home.png')))


@unittest.skipUnless(HAVE_SCREENS, 'screens/ with the October 2026 UI captures not available')
class HudReadTests(unittest.TestCase):

    def test_hud_triplet(self):
        from app.core.village_state import read_hud_triplet
        cases = {
            'home.png': (7185173, 6477630, 298693),
            'build_top.png': (7185173, 6477630, 298693),  # Build panel open: HUD shifted left
            'build_wall.png': (7185173, 6477630, 298726),
            'wall_selected.png': (3795022, 6487493, 298726),
            'wall_multi.png': (3795022, 6487493, 298726)}
        if (SCREENS / 'wall_selected_panel.jpg').exists():
            cases['wall_selected_panel.jpg'] = (4415896, 177282, 322900)
        for (name, expected) in cases.items():
            self.assertEqual(read_hud_triplet(shot(name)), expected, name)

    def test_covered_hud_reads_nothing_rather_than_garbage(self):
        from app.core.village_state import read_hud_triplet
        for name in ('row_building.png', 'row_hero.png', 'row_building_red_denygems.png', 'wall_confirm_gold.png'):
            self.assertIsNone(read_hud_triplet(shot(name)), name)


@unittest.skipUnless(HAVE_SCREENS, 'screens/ with the October 2026 UI captures not available')
class ListSettleTests(unittest.TestCase):

    def panel(self, frames):
        from app.config import Config
        from app.core.build_panel import BuildPanel
        owner = Mock()
        owner.config = Config()
        owner.window = _FakeWindow(frames)
        owner.stop_event = threading.Event()
        owner.stop_event.wait = lambda *_a, **_k: False
        return BuildPanel(owner)

    def test_waits_for_the_list_to_move_before_calling_it_settled(self):
        # Live bug: two frames equal to the pre-scroll one (wheel not applied yet)
        # counted as "settled", the scan re-read the same rows and stopped at 12/33.
        panel = self.panel(['build_top.png', 'build_top.png', 'build_top.png', 'build_mid.png', 'build_mid.png'])
        panel.scroll(2)
        frame = panel.wait_list_settled()
        self.assertTrue((frame == shot('build_mid.png')).all())

    def test_list_that_never_moves_returns_at_timeout(self):
        panel = self.panel(['build_bottom.png'])
        panel.scroll(2)
        frame = panel.wait_list_settled()
        self.assertTrue((frame == shot('build_bottom.png')).all())


class _FakeWindow:
    '''Serves frames in order; the last one repeats.'''

    def __init__(self, names):
        self.frames = [shot(n) for n in names]
        self.i = 0

    def screenshot(self):
        frame = self.frames[min(self.i, len(self.frames) - 1)]
        self.i += 1
        return frame.copy()


@unittest.skipUnless(HAVE_SCREENS, 'screens/ with the October 2026 UI captures not available')
class ConfirmFlowTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from app.utils.tesseract_env import configure_tesseract
        configure_tesseract()

    def setUp(self):
        # Keep test runs out of the user's real debug folder.
        from unittest.mock import patch
        patcher = patch('app.core.upgrader._dump_debug_frame')
        patcher.start()
        self.addCleanup(patcher.stop)

    def advisor(self, frames):
        from app.config import Config
        from app.core.upgrader import UpgradeAdvisor
        from app.services.vision import VisionService
        stop = threading.Event()
        stop.wait = lambda *_a, **_k: False  # no real sleeping in tests
        adv = UpgradeAdvisor(_FakeWindow(frames), Mock(), VisionService(), Config(), stop)
        adv.config.set_target_size_from_frame(shot('home.png'))
        return adv

    def pick(self, label, cost, resource):
        from app.core.upgrade_menu import SECTION_OTHER, UpgradeRow
        return UpgradeRow(label, SECTION_OTHER, cost, resource, True, (2095, 823), 823)

    def test_confirms_matching_building(self):
        adv = self.advisor(['row_building.png', 'row_building.png', 'home.png'])
        self.assertTrue(adv._confirm_upgrade_dialog(self.pick('Bomb Tower', 6800000, 'gold')))
        (x, y) = adv.input.click.call_args[0][:2]
        (fh, fw) = shot('home.png').shape[:2]
        # The green Confirm, never the grey Hammer-of-Building one left of it.
        self.assertGreater(x, fw * 0.62)
        self.assertGreater(y, fh * 0.80)

    def test_confirms_hero(self):
        adv = self.advisor(['row_hero.png', 'row_hero.png', 'home.png'])
        self.assertTrue(adv._confirm_upgrade_dialog(self.pick('Royal Champion', 176000, 'dark_elixir')))

    def test_red_price_is_never_clicked(self):
        adv = self.advisor(['row_building_redgold_dontupgrade.png'])
        self.assertFalse(adv._confirm_upgrade_dialog(self.pick('X-Bow', 7600000, 'gold')))
        adv.input.click.assert_not_called()

    def test_price_mismatch_is_never_clicked(self):
        adv = self.advisor(['row_building.png'])
        self.assertFalse(adv._confirm_upgrade_dialog(self.pick('Bomb Tower', 6400000, 'gold')))
        adv.input.click.assert_not_called()

    def test_wrong_building_is_never_clicked(self):
        adv = self.advisor(['row_building.png'])
        self.assertFalse(adv._confirm_upgrade_dialog(self.pick('Hidden Tesla', 6800000, 'gold')))
        adv.input.click.assert_not_called()

    def test_gem_dialog_is_closed_not_paid(self):
        adv = self.advisor(['row_building.png', 'row_building.png', 'row_building_red_denygems.png'])
        self.assertFalse(adv._confirm_upgrade_dialog(self.pick('Bomb Tower', 6800000, 'gold')))
        # Second click = the gem dialog's X (top-right of that dialog), not its green gem button.
        (x, y) = adv.input.click.call_args_list[-1][0][:2]
        (fh, fw) = shot('home.png').shape[:2]
        self.assertGreater(x, fw * 0.62)
        self.assertLess(y, fh * 0.40)


@unittest.skipUnless(HAVE_SCREENS and (SCREENS / 'wall_selected_panel.jpg').exists(), 'wall bar captures not available')
class WallBarTests(unittest.TestCase):

    def bot(self):
        from app.config import Config
        from app.core.bot import Bot
        bot = Bot.__new__(Bot)  # no window / threads: only the vision helpers are used
        bot.config = Config()
        return bot

    def test_upgrade_more_found_at_bar_scale(self):
        bot = self.bot()
        # Wall row clicked from the Build panel: panel stays open, bar renders ~0.9x.
        frame = shot('wall_selected_panel.jpg')
        bot.config.set_target_size_from_frame(frame)
        (x, y, scale) = bot._find_upgrade_more(frame)
        self.assertIsNotNone(x)
        self.assertLess(scale, 1.0)
        (fh, fw) = frame.shape[:2]
        self.assertTrue(0.33 * fw < x < 0.40 * fw and y > 0.78 * fh, (x, y))
        # Plain map selection: full size.
        frame = shot('wall_selected.png')
        bot.config.set_target_size_from_frame(frame)
        (x, _y, scale) = bot._find_upgrade_more(frame)
        self.assertIsNotNone(x)
        self.assertEqual(scale, 1.0)

    def test_multi_bar_buttons_found_inside_the_bar(self):
        from app.services.vision import VisionService
        bot = self.bot()
        for name in ('wall_multi.png', 'wall_notfrombuidl.png'):
            if not (SCREENS / name).exists():
                continue
            frame = shot(name)
            bot.config.set_target_size_from_frame(frame)
            (fh, fw) = frame.shape[:2]
            # The bar is full size here: a leftover 0.90 scale must not stick.
            previous = VisionService.set_ui_scale(0.9)
            try:
                (scale, pair) = bot._read_multi_bar(frame)
            finally:
                VisionService.set_ui_scale(previous)
            self.assertEqual(scale, 1.0, name)
            self.assertIsNotNone(pair, name)
            (x, y, w, h) = bot._wall_bar_roi(frame, pair, scale)
            self.assertLess(x + w, pair.gold.center[0], name)  # strictly left of the payment buttons
            self.assertLess(x + w, fw * 0.62, name)  # never reaches the panel's layout-edit button
            (ax, ay) = bot._find_in_bar(VisionService.find_active_addwall, frame, pair, scale)
            (rx, ry) = bot._find_in_bar(VisionService.find_active_removewall, frame, pair, scale)
            self.assertIsNotNone(rx, name)
            self.assertLess(rx, pair.gold.center[0], name)
            if name == 'wall_notfrombuidl.png':
                # "Add Wall" is drawn red there (no loot for one more wall): never clicked.
                self.assertIsNone(ax, name)
            else:
                self.assertIsNotNone(ax, name)
                self.assertTrue(rx < ax < pair.gold.center[0], (name, rx, ax))
            self.assertEqual(VisionService._ui_scale, previous)

    def test_ui_scale_is_restored(self):
        from app.services.vision import VisionService
        bot = self.bot()
        frame = shot('wall_selected_panel.jpg')
        bot.config.set_target_size_from_frame(frame)
        bot._find_upgrade_more(frame)
        self.assertEqual(VisionService._ui_scale, 1.0)


@unittest.skipUnless(HAVE_SCREENS and (SCREENS / 'wall_confirm_multi.png').exists(), 'walls Okay popup capture not available')
class WallsOkayDialogTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from app.utils.tesseract_env import configure_tesseract
        configure_tesseract()

    def bot(self, frames):
        from app.config import Config
        from app.core.bot import Bot
        from app.services.vision import VisionService
        bot = Bot.__new__(Bot)
        bot.config = Config()
        bot.vision = VisionService()
        bot.window = _FakeWindow(frames)
        bot.input = Mock()
        bot.stop_event = threading.Event()
        bot.stop_event.wait = lambda *_a, **_k: False
        bot.config.set_target_size_from_frame(shot('home.png'))
        return bot

    def okay_cancel_points(self):
        from app.core.build_panel import BuildPanel
        bot = self.bot(['wall_confirm_multi.png'])
        dialog = BuildPanel(bot).read_walls_okay_dialog(shot('wall_confirm_multi.png'))
        return dialog

    def test_reads_batch_popup(self):
        dialog = self.okay_cancel_points()
        self.assertIsNotNone(dialog)
        self.assertEqual((dialog.price, dialog.resource), (8000000, 'gold'))
        self.assertGreater(dialog.okay[0], dialog.cancel[0])

    def test_batch_popup_found_while_bar_scale_is_active(self):
        # Live bug: the wall batch runs under the bar's 0.90x scale and the full-size
        # popup stopped matching — walls were never confirmed.
        from app.core.build_panel import BuildPanel
        from app.services.vision import VisionService
        for name in ('wall_confirm_multi.png', 'wall_confirmokay_frombuild.png', 'wall_confirm_build_close.png'):
            if not (SCREENS / name).exists():
                continue
            bot = self.bot([name])
            previous = VisionService.set_ui_scale(0.9)
            try:
                dialog = BuildPanel(bot).read_walls_okay_dialog(shot(name))
            finally:
                VisionService.set_ui_scale(previous)
            self.assertIsNotNone(dialog, name)
            self.assertEqual((dialog.price, dialog.resource), (8000000, 'gold'), name)
            self.assertEqual(VisionService._ui_scale, previous)

    def test_no_dialog_saves_a_debug_frame(self):
        from unittest.mock import patch
        bot = self.bot(['wall_selected.png'])
        bot._wall_upgrade_confirmed = False
        with patch('app.core.upgrader._dump_debug_frame') as dump:
            bot._confirm_wall_dialog('gold')
        self.assertFalse(bot._wall_upgrade_confirmed)
        self.assertEqual(dump.call_args[0][1], 'wallconfirm')

    def test_other_dialogs_are_not_the_batch_popup(self):
        from app.core.build_panel import BuildPanel
        bot = self.bot(['home.png'])
        for name in ('home.png', 'row_building.png', 'wall_confirm_gold.png'):
            self.assertIsNone(BuildPanel(bot).read_walls_okay_dialog(shot(name)), name)

    def test_batch_confirmed_with_okay(self):
        bot = self.bot(['wall_confirm_multi.png', 'home.png'])
        bot._wall_upgrade_confirmed = False
        bot._confirm_wall_dialog('gold')
        self.assertTrue(bot._wall_upgrade_confirmed)
        okay = self.okay_cancel_points().okay
        self.assertEqual(bot.input.click.call_args_list[0][0][:2], okay)

    def test_wrong_resource_is_cancelled(self):
        bot = self.bot(['wall_confirm_multi.png', 'wall_confirm_multi.png', 'home.png'])
        bot._wall_upgrade_confirmed = False
        bot._confirm_wall_dialog('elixir')
        self.assertFalse(bot._wall_upgrade_confirmed)
        cancel = self.okay_cancel_points().cancel
        clicked = [c[0][:2] for c in bot.input.click.call_args_list]
        self.assertIn(cancel, clicked)
        self.assertNotIn(self.okay_cancel_points().okay, clicked)

    def test_close_all_never_presses_okay(self):
        from app.core.build_panel import BuildPanel
        bot = self.bot(['wall_confirm_multi.png', 'home.png'])
        self.assertTrue(BuildPanel(bot).close_all())
        dialog = self.okay_cancel_points()
        self.assertEqual(bot.input.click.call_args_list[0][0][:2], dialog.cancel)


class WallPriceTests(unittest.TestCase):
    '''Saved wall-level prices gate the panel walk and the second wall round.'''

    def bot(self):
        from app.config import Config
        from app.core.bot import Bot
        bot = Bot.__new__(Bot)
        bot.config = Config()
        return bot

    def test_any_level_payable(self):
        bot = self.bot()
        self.assertIsNone(bot._can_pay_any_wall((9000000, 0, 0)))  # nothing saved yet → unknown
        bot._wall_costs = {4000000, 3000000, 2000000}
        self.assertTrue(bot._can_pay_any_wall((2100000, 0, 0)))  # cheapest level, gold
        self.assertTrue(bot._can_pay_any_wall((0, 2000000, 0)))  # elixir pays walls too
        self.assertFalse(bot._can_pay_any_wall((2020000, 1999999, 0)))  # gold keeps the 50k attack buffer
        self.assertIsNone(bot._can_pay_any_wall(None))  # HUD unread → unknown, not "no"

    def test_scan_rows_add_prices(self):
        from app.core.upgrade_menu import UpgradeRow
        bot = self.bot()
        bot._wall_costs = {4000000}
        rows = [UpgradeRow('Wall', 'other', 2000000, 'gold', True, (0, 0), 0),
                UpgradeRow('Cannon', 'other', 1800000, 'gold', True, (0, 0), 0)]
        bot._remember_wall_costs(rows)
        self.assertEqual(bot._wall_costs, {4000000, 2000000})

    def round_bot(self, hud_after_first):
        from unittest.mock import Mock
        bot = self.bot()
        bot._wall_costs = {4000000}
        bot._should_upgrade_walls = Mock(return_value = True)
        bot._loot_snapshot_before_attack = Mock()
        bot._check_stop = Mock()
        bot._deselect_wall_ui = Mock()
        bot._read_hud_triplet_stable = Mock(return_value = hud_after_first)

        def buys():
            bot._wall_upgrade_confirmed = True
        bot._upgrade_walls = Mock(side_effect = buys)
        return bot

    def test_second_round_skipped_when_rest_pays_no_wall(self):
        bot = self.round_bot((1000000, 1000000, 0))
        bot._maybe_upgrade_walls(True)
        self.assertEqual(bot._upgrade_walls.call_count, 1)

    def test_second_round_runs_when_rest_pays_a_wall(self):
        bot = self.round_bot((1000000, 4500000, 0))
        bot._maybe_upgrade_walls(True)
        self.assertEqual(bot._upgrade_walls.call_count, 2)


class LootTrackerTests(unittest.TestCase):

    def bot(self, prev, reads):
        from app.core.bot import Bot
        bot = Bot.__new__(Bot)
        bot.stop_event = threading.Event()
        bot.stop_event.wait = Mock(return_value = False)
        bot._reset_loot_session()
        bot._emit_loot_update = Mock()
        bot._loot_prev_resources = prev
        bot._read_hud_triplet_stable = Mock(side_effect = list(reads))
        return bot

    def test_elixir_collapse_keeps_the_baseline_for_one_cycle(self):
        # Live 16/10 13:05: elixir 979299 → "6" twice, then +2.1M counted next battle.
        bot = self.bot((2875500, 979299, 283991), [(3211889, 6, 289884), (3211889, 6, 289884), (3700000, 2141638, 297807)])
        bot._loot_snapshot_before_attack()
        self.assertEqual(bot._loot_totals, (336389, 0, 5893))
        self.assertEqual(bot._loot_prev_resources, (3211889, 979299, 289884))
        bot._loot_snapshot_before_attack()
        self.assertEqual(bot._loot_totals, (824500, 1162339, 13816))

    def test_reread_fixes_the_collapse(self):
        bot = self.bot((2875500, 979299, 283991), [(3211889, 6, 289884), (3211889, 1430000, 289884)])
        bot._loot_snapshot_before_attack()
        self.assertEqual(bot._loot_totals, (336389, 450701, 5893))

    def test_small_spend_still_counts_the_other_gains(self):
        # Live 15:55: gold -1400 (entry fee) used to drop the whole battle.
        bot = self.bot((7796629, 8120903, 310000), [(7795229, 8125523, 310000)])
        bot._loot_snapshot_before_attack()
        self.assertEqual(bot._loot_totals, (0, 4620, 0))
        self.assertEqual(bot._loot_prev_resources, (7795229, 8125523, 310000))

    def test_a_collapse_seen_twice_is_a_real_spend(self):
        bot = self.bot((2000000, 1000000, 0), [(2100000, 5000, 0), (2100000, 5000, 0), (2200000, 6000, 0)])
        bot._loot_snapshot_before_attack()
        bot._loot_snapshot_before_attack()
        self.assertEqual(bot._loot_prev_resources, (2200000, 6000, 0))
        self.assertEqual(bot._loot_totals, (200000, 0, 0))


class RunSummaryTests(unittest.TestCase):

    def bot(self):
        from app.config import Config
        from app.core.bot import Bot
        bot = Bot.__new__(Bot)
        bot.config = Config()
        bot._reset_run_stats()
        bot._loot_totals = (14426918, 14128038, 0)
        return bot

    def test_wall_cost_comes_from_the_hud_drop(self):
        bot = self.bot()
        bot._wall_pick_cost = 4000000
        bot._wall_pending = {'from_level': 15, 'count': None, 'hud_before': (8125828, 6464296, 322900)}
        bot._read_hud_triplet_stable = Mock(return_value = (125828, 6464296, 322900))
        bot._record_wall_upgrade('gold', 2000000)  # misread dialog price must lose
        self.assertEqual(bot._walls_upgraded, [{'count': 2, 'from_level': 15, 'cost': 8000000, 'resource': 'gold', 'per_wall': 4000000}])

    def test_wall_count_ignores_a_title_misread(self):
        # Live 16/10 15:35: "4 wall(s) added", the bar title OCR read 48.
        bot = self.bot()
        bot._wall_pick_cost = 2000000
        bot._wall_batch_count = 4
        bot._wall_pending = {'from_level': 13, 'count': 48, 'hud_before': (9796629, 1120903, 310000)}
        bot._read_hud_triplet_stable = Mock(return_value = (1796629, 1120903, 310000))
        bot._record_wall_upgrade('gold', 8000000)
        self.assertEqual(bot._walls_upgraded[0]['count'], 4)
        self.assertIsNone(bot._wall_batch_count)

    def test_wall_count_falls_back_to_the_batch(self):
        bot = self.bot()
        bot._wall_pick_cost = 2000000
        bot._wall_batch_count = 3
        bot._wall_pending = {'from_level': None, 'count': 48, 'hud_before': None}
        bot._read_hud_triplet_stable = Mock(return_value = None)
        bot._record_wall_upgrade('elixir', None)
        self.assertEqual(bot._walls_upgraded[0]['count'], 3)

    def test_dialog_price_is_the_fallback(self):
        bot = self.bot()
        bot._wall_pick_cost = 3000000
        bot._wall_pending = {'from_level': None, 'count': 1, 'hud_before': None}
        bot._read_hud_triplet_stable = Mock(return_value = None)
        bot._record_wall_upgrade('elixir', 3000000)
        self.assertEqual(bot._walls_upgraded[0]['cost'], 3000000)

    def test_summary_groups_by_level_and_fills_unread_levels(self):
        bot = self.bot()
        bot._attacks_done = 19

        def wall(level, cost, resource):
            return {'count': 1, 'from_level': level, 'cost': cost, 'resource': resource, 'per_wall': cost}
        # The 15:05-15:25 run: 10 single walls, 3 titles unread.
        bot._walls_upgraded = [
            wall(None, 2000000, 'elixir'), wall(13, 2000000, 'gold'), wall(None, 3000000, 'elixir'),
            wall(13, 2000000, 'gold'), wall(13, 2000000, 'elixir'), wall(None, 2000000, 'gold'),
            wall(13, 2000000, 'elixir'), wall(13, 2000000, 'gold'), wall(12, 1500000, 'elixir'),
            wall(13, 2000000, 'gold')]
        text = bot._build_run_summary()
        self.assertIn('Attacchi: 19', text)
        self.assertIn('Muri migliorati: 10', text)
        self.assertIn('1 muro liv. 12 → 13: 1.500.000 elisir', text)
        # Both unread 2M walls join level 13 (2M was read as 13 → 14 elsewhere in the run).
        self.assertIn('8 muri liv. 13 → 14: 10.000.000 oro + 6.000.000 elisir', text)
        # 3M never had a level read: stays unknown rather than guessed.
        self.assertIn('1 muro livello ?: 3.000.000 elisir', text)
        self.assertIn('Speso in muri: elisir 10.500.000 | oro 10.000.000', text)
        lines = text.splitlines()
        self.assertLess(lines.index('  - 1 muro liv. 12 → 13: 1.500.000 elisir'),
                        lines.index('  - 1 muro livello ?: 3.000.000 elisir'))

    def test_ambiguous_price_fills_nothing(self):
        bot = self.bot()
        bot._walls_upgraded = [
            {'count': 1, 'from_level': 13, 'cost': 2000000, 'resource': 'gold'},
            {'count': 1, 'from_level': 14, 'cost': 2000000, 'resource': 'gold'},
            {'count': 1, 'from_level': None, 'cost': 2000000, 'resource': 'gold'}]
        self.assertIn('1 muro livello ?: 2.000.000 oro', bot._build_run_summary())


@unittest.skipUnless(HAVE_SCREENS, 'screens/ with the October 2026 UI captures not available')
class WallTitleTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from app.utils.tesseract_env import configure_tesseract
        configure_tesseract()

    def test_title(self):
        from app.core.build_panel import read_wall_bar_title
        self.assertEqual(read_wall_bar_title(shot('wall_multi.png')), (16, 4))
        self.assertEqual(read_wall_bar_title(shot('wall_selected.png')), (16, None))
        self.assertEqual(read_wall_bar_title(shot('home.png')), (None, None))


@unittest.skipUnless(HAVE_SCREENS, 'screens/ with the October 2026 UI captures not available')
class WallWalkTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from app.utils.tesseract_env import configure_tesseract
        configure_tesseract()

    def test_walk_picks_payable_level_and_saves_prices(self):
        from app.config import Config
        from app.core.bot import Bot
        from app.services.vision import VisionService
        bot = Bot.__new__(Bot)
        bot.config = Config()
        bot.vision = VisionService()
        bot.input = Mock()
        bot.stop_event = threading.Event()
        bot.stop_event.wait = lambda *_a, **_k: False
        bot._check_stop = lambda: None
        # HUD on home (gold 7.18M) → Build → panel already showing the Wall row (4M, gold).
        bot.window = _FakeWindow(['home.png', 'home.png', 'home.png', 'build_wall.png'])
        bot.config.set_target_size_from_frame(shot('home.png'))
        point = bot._find_wall_row_build_panel()
        self.assertIsNotNone(point)
        (fh, fw) = shot('build_wall.png').shape[:2]
        self.assertGreater(point[0], fw * 0.75)  # inside the panel
        self.assertIn(4000000, bot._wall_costs)

    def test_cheapest_order_walks_to_the_end_then_picks(self):
        from app.config import Config
        from app.core.bot import Bot
        from app.services.vision import VisionService
        bot = Bot.__new__(Bot)
        bot.config = Config()
        bot.vision = VisionService()
        bot.input = Mock()
        bot.stop_event = threading.Event()
        bot.stop_event.wait = lambda *_a, **_k: False
        bot._check_stop = lambda: None
        bot._upgrade_order = 'cheapest'
        # Same Wall frame twice = the wheel no longer moves the list → end reached.
        bot.window = _FakeWindow(['home.png', 'home.png', 'home.png', 'build_wall.png'])
        bot.config.set_target_size_from_frame(shot('home.png'))
        point = bot._find_cheapest_wall_row(__import__('app.core.build_panel', fromlist = ['BuildPanel']).BuildPanel(bot),
                                            (7185173, 6477630, 298693))
        self.assertIsNotNone(point)
        self.assertEqual(bot._wall_pick_cost, 4000000)
        self.assertEqual(bot._wall_costs, {4000000})  # whole list seen: replaced, not merged


if __name__ == '__main__':
    unittest.main()
