'''Reward chests of the November 2026 update: the end-of-battle chest (Claim Reward instead
of Return Home) and the Star Bonus chests (after 2 stars, and the 5-star "Star Bonus
Received!" popup). Each is Claim -> tap the chest open -> Continue on the reward screen.'''
import _testenv  # noqa: F401 — must precede the app imports (test log folder)
import unittest
from unittest.mock import Mock, patch

# Which templates each fake screen shows.
SCREENS = {
    'battle_end_chest': {'chestclaim.png'},
    'chest_room': {'chestroom.png'},
    'reward': {'chestcontinue.png'},
    'star_chest': {'starbonuschest.png'},
    'star_reward': {'starbonuscontinue.png'},
    'star_claim': {'starbonusclaim.png'},
    'home': set(),
}
POS = (1300, 1250)


class Frame:

    def __init__(self, label):
        self.label = label
        self.shape = (1440, 2560, 3)
        self.size = 1


class ChestFlowTests(unittest.TestCase):

    def bot(self, screens):
        '''A Bot whose game shows ``screens`` one capture at a time, then stays on the last.'''
        from app.config import Config
        from app.core.bot import Bot
        bot = Bot.__new__(Bot)
        bot.config = Config()
        bot.stop_event = Mock()
        bot.stop_event.is_set.return_value = False
        bot.stop_event.wait.return_value = False
        queue = [Frame(s) for s in screens]
        bot.window = Mock()
        bot.window.screenshot.side_effect = lambda: queue.pop(0) if len(queue) > 1 else queue[0]
        bot._update_config_size = Mock()
        bot.vision = Mock()
        bot.vision.find_template.side_effect = lambda frame, name, **kw: POS if name in SCREENS[frame.label] else (None, None)
        bot.input = Mock()
        bot._status_callback = None
        return bot

    def setUp(self):
        # The "more rewards?" watch after a Continue runs on wall-clock time: keep it short.
        p = patch('app.core.bot._CHEST_AFTER_CONTINUE_SECONDS', 0.05)
        p.start()
        self.addCleanup(p.stop)

    def clicked(self, bot):
        return [c.args[:2] for c in bot.input.click.call_args_list]

    def test_end_of_battle_chest_is_claimed_opened_and_continued(self):
        bot = self.bot(['battle_end_chest', 'chest_room', 'chest_room', 'chest_room', 'reward', 'home'])
        bot._wait_for_image = Mock(return_value = (None, None))  # no Okay before the result screen
        bot._battle_rewards = Mock()
        bot._battle_rewards.handle.return_value = False
        bot._return_home()
        self.assertEqual(self.clicked(bot), [POS, POS])  # Claim Reward, then Continue
        self.assertEqual(bot.input.click_at.call_count, 3)  # one tap per chest-room capture

    def test_star_bonus_two_star_chest_is_opened_from_recovery(self):
        bot = self.bot(['star_chest', 'star_chest', 'star_chest', 'star_chest', 'star_reward', 'home'])
        self.assertTrue(bot._handle_chest_screens(bot.window.screenshot()))
        self.assertEqual(bot.input.click_at.call_count, 3)  # the first capture only recognised it
        self.assertEqual(self.clicked(bot), [POS])  # Continue only

    def test_star_bonus_five_star_popup_is_claimed(self):
        bot = self.bot(['star_claim', 'star_chest', 'star_chest', 'star_reward', 'home'])
        self.assertTrue(bot._handle_chest_screens(bot.window.screenshot()))
        self.assertEqual(self.clicked(bot), [POS, POS])  # Claim, then Continue
        self.assertEqual(bot.input.click_at.call_count, 2)

    def test_more_reward_screens_after_continue_are_continued_too(self):
        bot = self.bot(['star_reward', 'star_reward', 'reward', 'home'])
        self.assertTrue(bot._handle_chest_screens(bot.window.screenshot()))
        self.assertEqual(self.clicked(bot), [POS, POS, POS])
        bot.input.click_at.assert_not_called()  # never a blind tap once the rewards are flowing

    def test_home_screen_is_not_a_chest_screen(self):
        bot = self.bot(['home'])
        self.assertFalse(bot._handle_chest_screens(bot.window.screenshot()))
        bot.input.click.assert_not_called()
        bot.input.click_at.assert_not_called()

    def test_chest_that_never_opens_gives_up(self):
        bot = self.bot(['chest_room'])
        with patch('app.core.bot._CHEST_TAP_TIMEOUT', 0.05), self.assertLogs('BotCore', level = 'WARNING'):
            self.assertFalse(bot._open_chest_until_continue())
        bot.input.click.assert_not_called()

    def test_chest_templates_are_in_the_16_9_profile(self):
        from app.core.bot import Bot, _CHEST_CLAIM_TEMPLATES, _CHEST_CONTINUE_TEMPLATES, _CHEST_SCREEN_TEMPLATES
        bot = self.bot(['home'])
        bot.config.set_target_size_from_frame(Mock(shape = (1440, 2560, 3)))
        names = _CHEST_CLAIM_TEMPLATES + _CHEST_CONTINUE_TEMPLATES + _CHEST_SCREEN_TEMPLATES
        self.assertEqual(Bot._available_templates(names), list(names))


if __name__ == '__main__':
    unittest.main()
