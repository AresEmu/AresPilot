'''Builder Base "Trophy" prioritise: play stage 1 to 100%, attack the second village with
the ready cards, press Return Home on the result screen — never End Battle / Surrender.'''
import _testenv  # noqa: F401 — must precede the app imports (test log folder)
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
import numpy as np

SCREENS = Path(__file__).resolve().parent.parent / 'screens'
STAGE2 = SCREENS / 'bb_trophy_stage2.png'    # 2nd village: 8 cards, card 4 dead, "106%"
RESULT = SCREENS / 'bb_trophy_result.png'    # "Total damage 200%" + Return Home
HAVE_SCREENS = STAGE2.exists() and RESULT.exists()


@unittest.skipUnless(HAVE_SCREENS, 'screens/ with the Builder Base trophy captures not available')
class TrophyScreenTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from app.config import Config
        from app.utils.tesseract_env import configure_tesseract
        configure_tesseract()
        cls.stage2 = cv2.imread(str(STAGE2))
        cls.result = cv2.imread(str(RESULT))
        Config().set_target_size_from_frame(cls.stage2)  # 16:9 template folder

    def test_reads_the_overall_damage_percent(self):
        from app.core.bot import Bot
        self.assertEqual(Bot._bb_overall_damage_percent(self.stage2), 106)

    def test_ready_cards_skip_the_dead_one_and_empty_slots(self):
        from app.core.bot import Bot
        cards = Bot._bb_ready_card_slots(self.stage2)
        self.assertEqual(len(cards), 7)  # 8 cards, card 4 grey; slots 9-11 empty
        xs = [x for (x, _y) in cards]
        self.assertNotIn(True, [abs(x - 948) < 30 for x in xs])

    def test_result_screen_shows_return_home(self):
        from app.core.bot import _BB_RETURN_HOME_TEMPLATE
        from app.services.vision import VisionService
        self.assertIsNotNone(VisionService.find_template(self.result, _BB_RETURN_HOME_TEMPLATE)[0])
        self.assertIsNone(VisionService.find_template(self.stage2, _BB_RETURN_HOME_TEMPLATE)[0])


class TrophyFlowTests(unittest.TestCase):

    def bot(self, percents, over_after):
        '''Bot reading ``percents`` from successive frames; the result screen shows from
        screenshot number ``over_after`` on.'''
        from app.config import Config
        from app.core.bot import Bot
        bot = Bot.__new__(Bot)
        bot.config = Config()
        bot.stop_event = Mock()
        bot.stop_event.is_set.return_value = False
        bot.stop_event.wait.return_value = False
        self.count = 0
        frame = np.zeros((1440, 2560, 3), dtype = np.uint8)

        def screenshot():
            self.count += 1
            return frame
        bot.window = Mock()
        bot.window.screenshot.side_effect = screenshot
        bot._update_config_size = Mock()
        bot.vision = Mock()
        bot.vision.find_template.return_value = (None, None)
        bot.input = Mock()
        reads = iter(percents + [percents[-1]] * 100)
        bot._bb_overall_damage_percent = Mock(side_effect = lambda _f: next(reads))
        bot._bb_trophy_return_home = Mock(side_effect = lambda _f: self.count >= over_after)
        bot._bb_trophy_deploy_stage2 = Mock(return_value = 7)
        bot._bb_dismiss_okay_and_return_home = Mock()
        bot._bb_surrender_and_return_home = Mock()
        return bot

    def run_flow(self, bot):
        clock = iter(range(0, 100000, 5))  # every time.time() call: +5 s
        with patch('app.core.bot.time.time', side_effect = lambda: next(clock)):
            bot._bb_trophy_play_both_stages_and_return_home()

    def test_deploys_in_the_second_village_after_100_percent(self):
        bot = self.bot([40, 80, 100, 100], over_after = 12)
        self.run_flow(bot)
        bot._bb_trophy_deploy_stage2.assert_called()
        bot._bb_trophy_return_home.assert_called()
        bot._bb_surrender_and_return_home.assert_not_called()

    def test_no_deploy_while_stage_one_is_below_100(self):
        bot = self.bot([30, 60, 95, 99], over_after = 8)
        self.run_flow(bot)
        bot._bb_trophy_deploy_stage2.assert_not_called()

    def test_one_stray_100_read_is_not_enough(self):
        bot = self.bot([50, 100, 60, 70, 80], over_after = 7)
        self.run_flow(bot)
        bot._bb_trophy_deploy_stage2.assert_not_called()

    def test_never_ends_or_surrenders_before_the_result_screen(self):
        bot = self.bot([20, 50], over_after = 5)
        self.run_flow(bot)
        bot._bb_surrender_and_return_home.assert_not_called()
        bot.input.click.assert_not_called()


if __name__ == '__main__':
    unittest.main()
