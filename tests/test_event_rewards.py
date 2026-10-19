import _testenv  # noqa: F401 — must precede the app imports (test log folder)
import unittest
from unittest.mock import Mock, patch
import numpy as np
from app.core.battle_rewards import BattleRewards
from app.core.bot import Bot
from app.core.strategies import AttackStrategy


class EventTests(unittest.TestCase):
    def setUp(self):
        self.window, self.input, self.stop = Mock(), Mock(), Mock()
        self.stop.is_set.return_value = False
        self.stop.wait.return_value = False
        self.event = BattleRewards(self.window, self.input, self.stop)
        self.frame = np.zeros((1440, 2560, 3), dtype=np.uint8)
        self.window.screenshot.return_value = self.frame

    @patch('app.core.battle_rewards.reward_visible')
    def test_right_card_is_clicked_once(self, visible):
        visible.side_effect = [True, True, False, False]
        self.assertTrue(self.event.handle(self.frame))
        self.input.mouse_up.assert_called_once()
        self.input.click_at.assert_called_once()
        x, y = self.input.click_at.call_args.args
        self.assertTrue(.62 * 2560 < x < .78 * 2560 and .31 * 1440 < y < .74 * 1440)

    @patch('app.core.battle_rewards._CARD_RETRY_AFTER', 0)
    @patch('app.core.battle_rewards.reward_visible')
    def test_card_click_is_retried_only_once(self, visible):
        visible.side_effect = [True] * 6 + [False, False]
        self.assertTrue(self.event.handle(self.frame))
        self.assertEqual(self.input.click_at.call_count, 2)

    @patch('app.core.battle_rewards.reward_visible')
    def test_overlay_gone_before_click_needs_no_click(self, visible):
        visible.side_effect = [True, False, False]
        self.assertTrue(self.event.handle(self.frame))
        self.input.click_at.assert_not_called()

    @patch('app.core.battle_rewards.reward_visible')
    def test_already_expired_screen_continues(self, visible):
        visible.return_value = False
        self.assertFalse(self.event.handle(self.frame))
        self.input.mouse_up.assert_not_called()
        self.input.click_at.assert_not_called()

    @patch('app.core.battle_rewards.reward_visible')
    def test_stop_interrupts_countdown(self, visible):
        visible.return_value = True
        self.stop.wait.return_value = True
        with self.assertRaises(InterruptedError):
            self.event.handle(self.frame)
        self.input.click_at.assert_not_called()

    @patch('app.core.battle_rewards.reward_visible')
    def test_missing_capture_is_not_dismissal(self, visible):
        visible.side_effect = [True, False, False]
        self.window.screenshot.side_effect = [None, self.frame, self.frame]
        self.assertTrue(self.event.handle(self.frame))
        self.assertEqual(self.window.screenshot.call_count, 3)
        self.input.click_at.assert_not_called()

    @patch('app.core.battle_rewards.reward_visible')
    def test_all_milestones_are_repeatable(self, visible):
        for _ in (33, 66, 100):
            visible.side_effect = [True, True, False, False]
            self.assertTrue(self.event.handle(self.frame))
        self.assertEqual(self.input.click_at.call_count, 3)

    def test_ability_clicks_do_not_redetect_undeployed_templates(self):
        frame = np.zeros((731, 1299, 3), dtype=np.uint8)
        vision, config = Mock(), Mock()
        positions = {'queen.png': (450, 660), 'king.png': (550, 660)}
        vision.find_template.side_effect = lambda frame, name, **kw: positions.get(name, (None, None))
        strategy = AttackStrategy(self.input, vision, config, self.stop)
        strategy._random_hero_point = Mock(return_value=(800, 300))
        with patch('app.core.strategies._HERO_ABILITY_DELAY', (0.0, 0.0)):
            strategy.deploy_heroes(frame)
            strategy.activate_hero_abilities()
        ability_clicks = [c.args for c in self.input.click.call_args_list[-2:]]
        self.assertCountEqual(ability_clicks, list(positions.values()))
        self.assertEqual(sum(c.args[1]=='queen.png' for c in vision.find_template.call_args_list), 1)

    def test_exit_immediately_after_reward_clears(self):
        bot = Bot.__new__(Bot)
        bot.stop_event, bot.input, bot.window = self.stop, self.input, self.window
        bot.vision = Mock()
        bot.vision.find_template.return_value = (40, 570)
        bot._update_config_size = Mock()
        bot._search_region_for_template = Mock(return_value=None)
        bot._battle_rewards = Mock()
        bot._battle_rewards.handle.side_effect = [True, False]
        bot._wait_for_battle_end(False)
        self.input.click.assert_called_once_with(40, 570, pause=.1)
        bot.vision.find_template.assert_called_once()

    def test_shifted_ability_uses_live_portrait(self):
        frame = np.zeros((731, 1299, 3), dtype=np.uint8)
        tile = np.random.default_rng(7).integers(0, 255, (36, 36, 3), dtype=np.uint8)
        frame[640:676, 500:536] = tile
        strategy = AttackStrategy(self.input, Mock(), Mock(), self.stop)
        relocated = strategy._relocate_abilities([(450, 658, tile)], frame)
        self.assertEqual(relocated[0][:2], (518, 658))

    def test_unavailable_ability_after_reward_does_not_crash(self):
        frame = np.zeros((731, 1299, 3), dtype=np.uint8)
        vision = Mock()
        vision.find_template.side_effect = lambda f, name, **kw: (450, 660) if name=='queen.png' else (None,None)
        strategy = AttackStrategy(self.input, vision, Mock(), self.stop)
        strategy._random_hero_point = Mock(return_value=(800,300))
        strategy._reward_checkpoint = Mock(side_effect=[(frame,False)]*7+[(frame,True)])
        strategy._relocate_abilities = Mock(return_value=[])
        with patch('app.core.strategies._HERO_ABILITY_DELAY', (0.0, 0.0)):
            strategy.deploy_heroes(frame)
            strategy.activate_hero_abilities()
        self.assertEqual(self.input.click.call_count, 2)


if __name__ == '__main__':
    unittest.main()
