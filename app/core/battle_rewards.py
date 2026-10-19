"""Timed-event "Pick a Reward!" overlay (33/66/100%): pick the right-hand card.

The overlay only exists while the event runs; when it never appears ``handle``
simply returns False and the battle goes on untouched."""
from functools import lru_cache
import random
import time
import cv2
from app.utils.common import get_resource_path
from app.utils.logger import setup_logger

logger = setup_logger('BattleRewards')


@lru_cache(maxsize=1)
def _header():
    return cv2.imread(str(get_resource_path('templates/events/reward_header.png')), 0)


def reward_visible(frame):
    if frame is None:
        return False
    art = _header()
    if art is None:
        return False
    h, w = frame.shape[:2]
    scale = h / 1440
    art = cv2.resize(art, (max(1, round(art.shape[1]*scale)), max(1, round(art.shape[0]*scale))))
    roi = cv2.cvtColor(frame[round(h*.04):round(h*.32), round(w*.15):round(w*.85)], cv2.COLOR_BGR2GRAY)
    if roi.shape[0] < art.shape[0] or roi.shape[1] < art.shape[1]:
        return False
    return cv2.minMaxLoc(cv2.matchTemplate(roi, art, cv2.TM_CCOEFF_NORMED))[1] >= .84


# Right-hand (bigger, gold or grey) card, as a fraction of the frame. The card spans
# x .62-.78, y .31-.74 at 16:9; clicks stay in the inner part of it.
_RIGHT_CARD_X = (.672, .733)
_RIGHT_CARD_Y = (.40, .65)
_CARD_SETTLE = (.6, 1.2)    # cards slide in: wait before the first click
_CARD_RETRY_AFTER = 2.5     # still open after this long → click the card once more


class BattleRewards:
    def __init__(self, window, input_service, stop_event):
        self.window, self.input, self.stop_event = window, input_service, stop_event

    def handle(self, frame):
        if self.stop_event.is_set():
            raise InterruptedError('Bot stopped by user')
        if not reward_visible(frame):
            return False
        self.input.mouse_up(0, 0)
        if self.stop_event.wait(random.uniform(*_CARD_SETTLE)):
            raise InterruptedError('Bot stopped by user')
        logger.info('Event reward: picking the right-hand card')
        clicks = 0
        next_click = time.monotonic()
        deadline = time.monotonic() + 40
        clear = 0
        while time.monotonic() < deadline:
            fresh = self.window.screenshot()
            if fresh is not None and not reward_visible(fresh):
                clear += 1
                if clear >= 2:
                    logger.info('Event reward closed; resuming battle')
                    return True
            else:
                clear = 0
                if fresh is not None and clicks < 2 and time.monotonic() >= next_click:
                    self._click_right_card(fresh)
                    clicks += 1
                    next_click = time.monotonic() + _CARD_RETRY_AFTER
                    if clicks == 2:
                        logger.info('Event reward: still open after the click, retrying once')
            if self.stop_event.wait(.15):
                raise InterruptedError('Bot stopped by user')
        raise RuntimeError('Event reward remained open for 40 seconds')

    def _click_right_card(self, frame):
        h, w = frame.shape[:2]
        x = round(w * random.uniform(*_RIGHT_CARD_X))
        y = round(h * random.uniform(*_RIGHT_CARD_Y))
        self.input.click_at(x, y)
