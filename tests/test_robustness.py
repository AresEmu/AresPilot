'''Run-time robustness: one shared log file handler, a lost game window searched again,
and a Builder Base battle without Baby Dragons left at once instead of blocking the loop.'''
import _testenv  # noqa: F401 — must precede the app imports (test log folder)
import unittest
from unittest.mock import Mock, patch


class SharedLogHandlerTests(unittest.TestCase):

    def test_named_loggers_share_one_file_handler(self):
        from logging.handlers import RotatingFileHandler
        from app.utils.logger import setup_logger
        handlers = set()
        for name in ('BotCore', 'Strategies', 'WindowService', 'RobustnessTestLogger'):
            log = setup_logger(name)
            handlers |= {id(h) for h in log.handlers if isinstance(h, RotatingFileHandler)}
        self.assertEqual(len(handlers), 1)


class LostWindowTests(unittest.TestCase):

    def service(self):
        from app.services.window import WindowService
        ws = WindowService.__new__(WindowService)
        ws.hwnd = 1234
        ws._last_find_attempt = 0.0
        ws.user32 = Mock()
        ws.find_window = Mock(return_value = False)
        return ws

    def test_dead_handle_is_searched_again(self):
        ws = self.service()
        ws.user32.IsWindow.return_value = 0
        with self.assertLogs('WindowService', level = 'WARNING'):
            self.assertFalse(ws._ensure_hwnd())
        self.assertEqual(ws.hwnd, 0)
        ws.find_window.assert_called_once()

    def test_live_handle_is_kept(self):
        ws = self.service()
        ws.user32.IsWindow.return_value = 1
        self.assertTrue(ws._ensure_hwnd())
        ws.find_window.assert_not_called()

    def test_failed_search_is_not_repeated_every_capture(self):
        ws = self.service()
        ws.hwnd = 0
        for _ in range(5):
            ws._ensure_hwnd()
        ws.find_window.assert_called_once()


class BuilderBaseNoDragonTests(unittest.TestCase):

    def bot(self):
        from app.config import Config
        from app.core.bot import Bot
        bot = Bot.__new__(Bot)
        bot.config = Config()
        bot.stop_event = Mock()
        bot.stop_event.is_set.return_value = False
        bot.stop_event.wait.return_value = False
        bot.window = Mock()
        bot.window.screenshot.return_value = Mock(shape = (1440, 2560, 3), size = 1)
        bot._update_config_size = Mock()
        bot.vision = Mock()
        bot.input = Mock()
        bot._status_callback = None
        return bot

    def test_battle_with_end_battle_only_is_left(self):
        from app.core.bot import _BB_RETURN_HOME_TEMPLATE
        bot = self.bot()
        bot.vision.find_template.side_effect = lambda frame, name, **kw: (10, 20) if name == 'endbattle.png' else (None, None)
        bot._bb_surrender_and_return_home = Mock()
        self.assertTrue(bot._bb_recover_from_battle())
        bot._bb_surrender_and_return_home.assert_called_once_with('endbattle.png')
        bot.input.click.assert_not_called()  # no empty-ground tap: it could drop a card
        self.assertIn(_BB_RETURN_HOME_TEMPLATE, [c.args[1] for c in bot.vision.find_template.call_args_list])

    def test_timed_run_stops_after_the_failure_limit(self):
        from app.core.bot import _TROOP_FAILURE_LIMIT
        bot = self.bot()
        bot._bb_recover_from_battle = Mock(return_value = True)
        for failures in range(1, _TROOP_FAILURE_LIMIT):
            self.assertFalse(bot._bb_handle_no_dragon(failures, 600))
        with self.assertLogs('BotCore', level = 'WARNING'):
            self.assertTrue(bot._bb_handle_no_dragon(_TROOP_FAILURE_LIMIT, 600))
        self.assertEqual(bot._bb_recover_from_battle.call_count, _TROOP_FAILURE_LIMIT)

    def test_run_until_maxed_backs_off_instead_of_stopping(self):
        from app.core.bot import _IDLE_RECHECK_SECONDS, _TROOP_FAILURE_LIMIT
        bot = self.bot()
        bot._bb_recover_from_battle = Mock(return_value = True)
        with self.assertLogs('BotCore', level = 'WARNING'):
            self.assertFalse(bot._bb_handle_no_dragon(_TROOP_FAILURE_LIMIT, 0))
        bot.stop_event.wait.assert_called_with(_IDLE_RECHECK_SECONDS)

    def test_surrender_helper_falls_back_to_end_battle(self):
        bot = self.bot()
        bot._wait_for_image = Mock(side_effect = lambda name, **kw: (5, 6) if name == 'endbattle.png' else (None, None))
        bot._bb_dismiss_okay_and_return_home = Mock()
        bot._bb_surrender_and_return_home()
        bot.input.click.assert_called_once_with(5, 6, pause = 0.15)
        bot._bb_dismiss_okay_and_return_home.assert_called_once_with(retry_battle_template = 'endbattle.png')


class WaitLoopTests(unittest.TestCase):

    def test_missing_capture_pauses_instead_of_spinning(self):
        from app.core.bot import Bot
        bot = Bot.__new__(Bot)
        bot.stop_event = Mock()
        bot.stop_event.is_set.return_value = False
        bot.stop_event.wait.return_value = True  # the pause is where the stop lands
        bot.window = Mock()
        bot.window.screenshot.return_value = None
        self.assertEqual(bot._wait_for_image('attack.png', timeout = 5), (None, None))
        self.assertEqual(bot.window.screenshot.call_count, 1)
        bot.stop_event.wait.assert_called_once_with(0.5)


if __name__ == '__main__':
    unittest.main()
