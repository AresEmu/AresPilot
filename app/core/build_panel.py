'''Build panel + upgrade dialog navigation (UI ottobre 2026, 16:9).

The October 2026 UI replaced the builder-portrait popup with a "Build" button
(bottom-right, ``build.png``) that slides in the "Buildings & Heroes" panel on the
right (closed by its own X, ``buildpanel_x.png``). Clicking a row opens the upgrade
dialog directly ("Upgrade <name> to Level N?") whose green Confirm button carries the
price: yellow when affordable, red when not. Confirming a red price opens the
"You need more Gold/Elixir" gem dialog (``needgold_x.png``) — the bot never buys
resources with gems, so it only ever closes that one.

Walls keep their bottom selection bar (Upgrade More / Add Wall / Remove Wall), but its
resource buttons now lead to the same Confirm dialog instead of an Okay popup.

Shared by the auto-upgrader and the wall flow: ``owner`` is any object exposing
``window``, ``input``, ``vision``, ``config`` and ``stop_event`` (UpgradeAdvisor, Bot).
'''
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2

from app.core.cost_reader import read_cost_lines
from app.core.upgrade_menu import RESOURCE_DARK, RESOURCE_ELIXIR, RESOURCE_GOLD
from app.services.vision import VisionService
from app.utils.logger import setup_logger

logger = setup_logger('BuildPanel')

BUILD_BUTTON = 'build.png'
PANEL_CLOSE = 'buildpanel_x.png'
DIALOG_CLOSE = 'exit.png'
GEM_DIALOG_CLOSE = 'needgold_x.png'
# Multi-wall batches still confirm through the old "Upgrade Walls" popup: "Do you
# really want to upgrade the selected Walls for 8000000 Gold?" + Cancel / Okay.
WALLS_OKAY = 'okay.png'
WALLS_CANCEL = 'cancel.png'
_WALLS_DIALOG_TEXT_FRAC = (0.31, 0.41, 0.38, 0.095)  # the question line(s)

_PANEL_SCROLL_POINT_FRAC = (0.865, 0.50)  # wheel target inside the panel list
_PANEL_OPEN_POLLS = 8
# The panel may reopen at its last scroll position: wheel up in bursts until a burst
# moves nothing (at most _RESET_MAX_BURSTS x _RESET_BURST_CLICKS = the old 30 clicks).
_RESET_BURST_CLICKS = 10
_RESET_MAX_BURSTS = 3
_PANEL_WHEEL_PAUSE = (0.03, 0.08)  # s between wheel clicks inside the panel (input default 0.05-0.2)
# "List is still" detection, replacing fixed 0.6-1.0 s sleeps after each nudge.
_PANEL_LIST_FRAC = (0.74, 0.07, 0.25, 0.82)
_LIST_SIGNATURE_SIZE = (48, 96)  # w, h of the grey thumbnail compared
_LIST_STILL_DIFF = 2.0  # mean abs grey difference; ticking timers stay well below it
_LIST_SETTLE_FIRST_WAIT = 0.2
_LIST_SETTLE_INTERVAL = 0.12
_LIST_SETTLE_TIMEOUT = 1.2

# Upgrade dialog, green Confirm (fractions of the frame, measured on 2558x1438 for
# buildings, heroes and walls). The grey "Confirm — Hammer of Building" button sits
# LEFT of it (x < 0.61) and is never a click target: the x fence keeps it out.
_CONFIRM_BUTTON_FRAC = (0.625, 0.815, 0.153, 0.115)  # x, y, w, h
# Two Confirm layouts, depending on the account's Gold Pass:
# - GOLD PASS ACTIVE: discounted price at y 0.857-0.880, the struck-through full price
#   below it (row_building: 6 800 000 over ~~8 500 000~~).
# - NO GOLD PASS: a yellow "With the Gold Pass you could save up to…" banner above the
#   button, no struck price, and the price sits lower at y 0.875-0.896
#   (wallconfirm_from_build: 4 000 000 — read in the first box it was cut off, so the
#   Confirm was never found and the single wall never bought).
# The banner picks the layout; the other box is the fallback.
LAYOUT_GOLD_PASS = 'gold_pass'
LAYOUT_NO_GOLD_PASS = 'no_gold_pass'
_CONFIRM_PRICE_FRAC = {
    LAYOUT_GOLD_PASS: (0.625, 0.848, 0.125, 0.040),
    LAYOUT_NO_GOLD_PASS: (0.625, 0.866, 0.125, 0.040)}
_GOLD_PASS_BANNER_FRAC = (0.47, 0.69, 0.43, 0.11)
_GOLD_PASS_BANNER_MIN_YELLOW = 0.5  # measured 0.85 with the banner, 0.00 without
_CONFIRM_ICON_FRAC = (0.745, 0.86, 0.03, 0.055)
_CONFIRM_CLICK_FRAC = (0.70, 0.835)  # the "Confirm" word
_CONFIRM_MIN_GREEN = 0.35  # measured 0.59-0.70 on the button


@dataclass(frozen = True)
class WallsOkayDialog:
    okay: Tuple[int, int]
    cancel: Tuple[int, int]
    price: Optional[int]  # from the question text; None when it did not read
    resource: Optional[str]


@dataclass(frozen = True)
class ConfirmButton:
    center: Tuple[int, int]
    price: int
    red: bool  # the game marks the price red: not enough resources (click → gem dialog)
    resource: Optional[str]  # RESOURCE_* from the icon right of the price
    layout: str = LAYOUT_GOLD_PASS  # which price layout read (LAYOUT_*)


def _frac_region(frame, frac):
    (fh, fw) = frame.shape[:2]
    (x, y, w, h) = frac
    return (round(fw * x), round(fh * y), round(fw * w), round(fh * h))


def _crop(frame, frac):
    (x, y, w, h) = _frac_region(frame, frac)
    return frame[y:y + h, x:x + w]


def _confirm_icon_resource(frame):
    patch = _crop(frame, _CONFIRM_ICON_FRAC)
    if patch.size == 0:
        return None
    yellow = VisionService.yellow_fraction(patch)
    pink = VisionService.pink_fraction(patch, val_floor = 170)
    dark = float((patch.max(axis = 2) < 70).mean())
    # Measured: gold yellow 0.60-0.68; elixir pink 0.36; dark-elixir dark 0.38 (yellow 0.19).
    if yellow >= 0.40:
        return RESOURCE_GOLD
    if pink >= 0.15:
        return RESOURCE_ELIXIR
    if dark >= 0.25:
        return RESOURCE_DARK
    return None


def read_confirm_button(frame):
    '''Green Confirm of the upgrade dialog → :class:`ConfirmButton`, or None when the
    dialog is not up (or dimmed by the gem dialog on top of it).'''
    if frame is None or frame.size == 0:
        return None
    button = _crop(frame, _CONFIRM_BUTTON_FRAC)
    if button.size == 0:
        return None
    hsv = cv2.cvtColor(button, cv2.COLOR_BGR2HSV)
    green = float(((hsv[:, :, 0] >= 30) & (hsv[:, :, 0] <= 85) & (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 90)).mean())
    if green < _CONFIRM_MIN_GREEN:
        return None
    # Green alone is not proof — village grass fills this box on the home screen. The
    # price line is: no readable price, no button (this also rejects the Confirm
    # dimmed behind the gem dialog).
    banner = VisionService.yellow_fraction(_crop(frame, _GOLD_PASS_BANNER_FRAC)) >= _GOLD_PASS_BANNER_MIN_YELLOW
    order = (LAYOUT_NO_GOLD_PASS, LAYOUT_GOLD_PASS) if banner else (LAYOUT_GOLD_PASS, LAYOUT_NO_GOLD_PASS)
    for layout in order:
        price_line = _read_price_in_box(frame, _CONFIRM_PRICE_FRAC[layout])
        if price_line is not None:
            break
    else:
        return None
    (fh, fw) = frame.shape[:2]
    center = (round(fw * _CONFIRM_CLICK_FRAC[0]), round(fh * _CONFIRM_CLICK_FRAC[1]))
    return ConfirmButton(
        center = center,
        price = price_line.value,
        red = price_line.red,
        resource = _confirm_icon_resource(frame),
        layout = layout)


def _read_price_in_box(frame, frac):
    '''Topmost price fully inside the box — a line touching the box edge is a price
    of the OTHER layout cut in half, never trusted.'''
    region = _frac_region(frame, frac)
    (_x, y0, _w, h) = region
    lines = [c for c in read_cost_lines(frame, region, min_digits = 4)
             if c.bbox[1] > y0 + 1 and c.bbox[1] + c.bbox[3] < y0 + h - 1]
    return min(lines, key = (lambda c: c.bbox[1])) if lines else None


_WALL_TITLE_FRAC = (0.10, 0.68, 0.70, 0.07)  # "Wall (Level 15)x 2" above the selection bar


def read_wall_bar_title(frame):
    '''"Wall (Level N)x K" above the wall selection bar → (level, count); either may
    be None (count is absent for a single wall; OCR misses ~1 frame in 5). Only used
    for the run summary — never for a decision. The title is cream (~R230 G230
    B160-190), so it is isolated by colour, cropped to its longest letter run (the
    village around it is noisy) and read by Tesseract.'''
    try:
        import re
        import numpy as np
        import pytesseract
        (fh, fw) = frame.shape[:2]
        (x, y, w, h) = _frac_region(frame, _WALL_TITLE_FRAC)
        roi = frame[y:y + h, x:x + w]
        b = roi[:, :, 0].astype(int)
        g = roi[:, :, 1].astype(int)
        r = roi[:, :, 2].astype(int)
        mask = ((r >= 205) & (g >= 205) & (b >= 120) & (b <= 225)).astype(np.uint8)
        (n, _lab, stats, _c) = cv2.connectedComponentsWithStats(mask, connectivity = 8)
        comps = sorted(tuple(int(v) for v in stats[i]) for i in range(1, n)
                       if fh * 0.012 <= stats[i][3] <= fh * 0.035 and stats[i][4] >= 15 and stats[i][2] <= stats[i][3] * 1.6)
        if not comps:
            return (None, None)
        med_h = sorted(c[3] for c in comps)[len(comps) // 2]
        runs = [[comps[0]]]
        for c in comps[1:]:
            p = runs[-1][-1]
            if c[0] - (p[0] + p[2]) <= 1.5 * med_h and abs((c[1] + c[3] / 2) - (p[1] + p[3] / 2)) <= med_h:
                runs[-1].append(c)
            else:
                runs.append([c])
        run = max(runs, key = len)
        x0 = max(0, min(c[0] for c in run) - 10)
        x1 = max(c[0] + c[2] for c in run) + 10
        y0 = max(0, min(c[1] for c in run) - 8)
        y1 = max(c[1] + c[3] for c in run) + 8
        crop = cv2.copyMakeBorder(255 - mask[y0:y1, x0:x1] * 255, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value = 255)
        text = pytesseract.image_to_string(crop, config = '--psm 7').strip().lower()
        m = re.search(r'level\s*(\d{1,2})\s*\)?\s*(?:x\s*(\d{1,3}))?', text)
        if not m:
            logger.debug('wall bar title unread: %r', text)
            return (None, None)
        return (int(m.group(1)), int(m.group(2)) if m.group(2) else None)
    except Exception:
        logger.debug('wall bar title read failed', exc_info = True)
        return (None, None)


class BuildPanel:

    def __init__(self, owner):
        self.owner = owner

    # ---- plumbing ----

    def frame(self):
        frame = self.owner.window.screenshot()
        if frame is None or frame.size == 0:
            return None
        self.owner.config.set_target_size_from_frame(frame)
        return frame

    def _wait(self, seconds):
        '''True when stop was requested.'''
        return self.owner.stop_event.wait(seconds)

    def _find(self, frame, name, region = None, threshold = 0.8):
        # Panel, dialogs and popups always render full size — only the wall selection
        # bar shrinks beside the open panel. The wall flow runs its whole batch under
        # VisionService.set_ui_scale(0.90), which made the full-size "Upgrade Walls"
        # popup unmatchable (okay 0.92 → 0.70, cancel 1.00 → 0.67): walls never
        # confirmed. Every template here is matched at 1.0, whatever the caller set.
        previous = VisionService.set_ui_scale(1.0)
        try:
            return self.owner.vision.find_template(frame, name, threshold = threshold, region = region)
        finally:
            VisionService.set_ui_scale(previous)

    def scroll_point(self, frame = None):
        frame = frame if frame is not None else self.frame()
        if frame is None:
            return (0, 0)
        (fh, fw) = frame.shape[:2]
        return (round(fw * _PANEL_SCROLL_POINT_FRAC[0]), round(fh * _PANEL_SCROLL_POINT_FRAC[1]))

    def scroll(self, clicks, upward = False):
        frame = self.frame()
        # Remembered so wait_list_settled can tell "still easing" from "not moved yet".
        self._pre_scroll_signature = self._list_signature(frame) if frame is not None else None
        point = self.scroll_point(frame) if frame is not None else self.scroll_point()
        self.owner.input.scroll(*point, clicks, upward = upward, pause = _PANEL_WHEEL_PAUSE)

    @staticmethod
    def _list_signature(frame):
        '''Tiny grey thumbnail of the panel list: two equal ones = the list is still.'''
        (x, y, w, h) = _frac_region(frame, _PANEL_LIST_FRAC)
        roi = frame[y:y + h, x:x + w]
        if roi.size == 0:
            return None
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        return cv2.resize(gray, _LIST_SIGNATURE_SIZE, interpolation = cv2.INTER_AREA).astype('float32')

    @staticmethod
    def _same_list(a, b):
        return a is not None and b is not None and float(abs(a - b).mean()) < _LIST_STILL_DIFF

    def wait_list_settled(self, timeout = _LIST_SETTLE_TIMEOUT):
        '''After a wheel nudge: return as soon as the list has MOVED and then stopped
        easing (two equal thumbnails in a row) instead of sleeping a fixed 0.6-1.0 s.
        A list that never moves (end or top reached) returns at ``timeout``. Two equal
        thumbnails before the wheel took effect used to count as "settled" (live
        repro: the upgrade scan read 12 of 33 rows and stopped, thinking it had
        reached the end). Returns the last frame (None on stop).'''
        if self._wait(_LIST_SETTLE_FIRST_WAIT):
            return None
        before = getattr(self, '_pre_scroll_signature', None)
        moved = before is None
        previous = None
        frame = None
        waited = _LIST_SETTLE_FIRST_WAIT
        while waited < timeout:
            frame = self.frame()
            signature = self._list_signature(frame) if frame is not None else None
            if not moved and signature is not None and not self._same_list(before, signature):
                moved = True
            if moved and self._same_list(previous, signature):
                return frame
            previous = signature
            if self._wait(_LIST_SETTLE_INTERVAL):
                return None
            waited += _LIST_SETTLE_INTERVAL
        return frame

    def reset_to_top(self):
        '''Wheel the list up in short bursts until it stops moving. The panel reopens
        at its last position; 30 fixed clicks (≈4 s) were spent even when it was
        already at the top.'''
        frame = self.frame()
        before = self._list_signature(frame) if frame is not None else None
        for _ in range(_RESET_MAX_BURSTS):
            self.scroll(_RESET_BURST_CLICKS, upward = True)
            frame = self.wait_list_settled()
            if frame is None:
                return False
            after = self._list_signature(frame)
            if self._same_list(before, after):
                return True  # the burst moved nothing: already at the top
            before = after
        return True

    # ---- state ----

    def is_home(self, frame):
        (ax, _ay) = self._find(frame, 'attack.png', region = VisionService.bottom_half_region(frame))
        return bool(ax)

    def is_open(self, frame):
        (fh, fw) = frame.shape[:2]
        (x, _y) = self._find(frame, PANEL_CLOSE, region = (fw * 3 // 4, 0, fw - fw * 3 // 4, fh // 8))
        return bool(x)

    def find_build_button(self, frame):
        return self._find(frame, BUILD_BUTTON, region = VisionService.bottom_right_quadrant_region(frame))

    # ---- actions ----

    def open(self, reset_to_top = True):
        '''Home screen → click Build → wait for the panel. True when it is open.'''
        frame = self.frame()
        if frame is None:
            return False
        (bx, by) = self.find_build_button(frame)
        if not bx:
            logger.info('Build panel: Build button not found — skipping')
            return False
        self.owner.input.click(bx, by, pause = 0.4)
        for _ in range(_PANEL_OPEN_POLLS):
            if self._wait(0.3):
                return False
            frame = self.frame()
            if frame is not None and self.is_open(frame):
                break
        else:
            logger.info('Build panel: panel did not open after the Build click')
            return False
        if reset_to_top and not self.reset_to_top():
            return False
        return True

    def close_all(self, max_steps = 6):
        '''Back out to the home screen: gem dialog X, dialog X, walls-popup Cancel,
        panel X, in that order (an open dialog also shows the panel X behind it).
        Never clicks a confirm or an Okay.
        True when the home screen is reached.'''
        for _ in range(max_steps):
            frame = self.frame()
            if frame is None:
                return False
            (x, y) = self._find(frame, GEM_DIALOG_CLOSE)
            if not x:
                (x, y) = self._find(frame, DIALOG_CLOSE)
            (fh, fw) = frame.shape[:2]
            if not x:
                # "Upgrade Walls" popup has no X — Cancel backs out of it (never Okay).
                (x, y) = self._find(frame, WALLS_CANCEL, region = (fw // 4, fh // 4, fw // 2, fh // 2))
            if not x and self.is_open(frame):
                (x, y) = self._find(frame, PANEL_CLOSE, region = (fw * 3 // 4, 0, fw - fw * 3 // 4, fh // 8))
            if not x:
                if self.is_home(frame):
                    return True
                # Screen-level X's (Hero Hall behind a hero dialog: 0.64 while dimmed)
                # live in the top-right corner — accept a weaker match only there, and
                # only off the home screen (the HUD bars sit in that corner).
                (x, y) = self._find(frame, DIALOG_CLOSE, region = (round(fw * 0.85), 0, fw - round(fw * 0.85), round(fh * 0.2)), threshold = 0.6)
            if not x:
                # Selection bar (wall) or an unknown overlay: tap empty ground.
                (x, y) = self.owner.config.get_point('empty')
            self.owner.input.click(x, y, pause = 0.3)
            if self._wait(0.4):
                return False
        frame = self.frame()
        return frame is not None and self.is_home(frame)

    def wait_confirm_button(self, polls = 8, interval = 0.4):
        '''Poll for the upgrade dialog's Confirm → (frame, ConfirmButton) or (frame, None).'''
        frame = None
        for _ in range(polls):
            frame = self.frame()
            if frame is not None:
                button = read_confirm_button(frame)
                if button is not None:
                    return (frame, button)
            if self._wait(interval):
                break
        return (frame, None)

    def read_walls_okay_dialog(self, frame):
        '''The "Upgrade Walls" Okay popup → :class:`WallsOkayDialog`, or None. Okay is a
        generic template, so it only counts next to Cancel AND with "Walls" in the
        question — an unknown dialog's Okay is never pressed.'''
        (fh, fw) = frame.shape[:2]
        middle = (fw // 4, fh // 4, fw // 2, fh // 2)
        (ox, oy) = self._find(frame, WALLS_OKAY, region = middle)
        (cx, cy) = self._find(frame, WALLS_CANCEL, region = middle)
        if not ox or not cx or abs(oy - cy) > fh * 0.03 or cx >= ox:
            return None
        words = self.owner.vision.find_words_ocr(
            frame, region = _frac_region(frame, _WALLS_DIALOG_TEXT_FRAC), tesseract_config = '--psm 6') or []
        texts = [''.join(ch for ch in w.text.lower() if ch.isalnum()) for w in words]
        if 'walls' not in texts:
            return None
        price = next((int(t) for t in texts if t.isdigit() and len(t) >= 4), None)
        resource = None
        if any(t.startswith('gold') for t in texts):
            resource = RESOURCE_GOLD
        elif any(t.startswith('elixir') for t in texts):
            resource = RESOURCE_ELIXIR
        return WallsOkayDialog(okay = (ox, oy), cancel = (cx, cy), price = price, resource = resource)

    def click_walls_okay_and_check(self, dialog, settle_polls = 6):
        '''Same outcomes as :meth:`click_confirm_and_check` for the walls Okay popup.'''
        self.owner.input.click(*dialog.okay, pause = 0.5)
        for _ in range(settle_polls):
            if self._wait(0.5):
                return 'stuck'
            frame = self.frame()
            if frame is None:
                continue
            if self.gem_dialog_visible(frame):
                logger.warning('Walls dialog: the game asks for gems (not enough resources) — closing without paying')
                (x, y) = self._find(frame, GEM_DIALOG_CLOSE)
                self.owner.input.click(x, y, pause = 0.4)
                return 'gems'
            (fh, fw) = frame.shape[:2]
            (cx, _cy) = self._find(frame, WALLS_CANCEL, region = (fw // 4, fh // 4, fw // 2, fh // 2))
            if not cx:
                return 'ok'
        return 'stuck'

    def gem_dialog_visible(self, frame):
        (x, _y) = self._find(frame, GEM_DIALOG_CLOSE)
        return bool(x)

    def click_confirm_and_check(self, button, settle_polls = 6):
        '''Click a verified Confirm, then watch the result. Returns 'ok' when the
        dialog closed, 'gems' when the gem dialog came up (closed again here — never
        paid), 'stuck' when the Confirm is still showing.'''
        self.owner.input.click(*button.center, pause = 0.5)
        for _ in range(settle_polls):
            if self._wait(0.5):
                return 'stuck'
            frame = self.frame()
            if frame is None:
                continue
            if self.gem_dialog_visible(frame):
                logger.warning('Upgrade dialog: the game asks for gems (not enough resources) — closing without paying')
                (x, y) = self._find(frame, GEM_DIALOG_CLOSE)
                self.owner.input.click(x, y, pause = 0.4)
                return 'gems'
            if read_confirm_button(frame) is None:
                return 'ok'
        return 'stuck'
