import time
from app.core.battle_rewards import BattleRewards
from app.core import bb_edge
import random
import threading
from typing import Callable, List, Optional, Tuple
from app.config import ASPECT_16_10, ASPECT_16_9, Config
from app.core.strategies import AttackStrategy, EdragStrategy, TroopSpamStrategy, _EDRAG_DELAY
from app.core.build_panel import BuildPanel, read_confirm_button, read_wall_bar_title
from app.core.upgrade_menu import is_wall_row, parse_builder_menu
from app.core.upgrader import AUTO_UPGRADE_MODES, LIVE_UPGRADE_MODES, MODE_OFF, UpgradeAdvisor
from app.core.village_state import read_hud_triplet, read_hud_triplet_stable, read_village_state, read_village_state_stable
from app.services.input import InputService
from app.services.vision import BOTTOM_HALF_BOT_TEMPLATES, BOTTOM_RIGHT_BOT_TEMPLATES, TOP_HALF_BOT_TEMPLATES, VisionService
from app.services.window import WindowService
from app.utils.common import get_template_path
from app.utils.logger import setup_logger
from app.utils.player_list_store import PlayerEntry
from app.utils.profile_settings_store import EARTHQUAKE_METHOD_CURVE
logger = setup_logger('BotCore')
_HOME_VILLAGE_BUILDER_TEMPLATES = ('builder.png', 'gbuilder.png')
_WALL_OCR_RETRY_DRAG_BASELINE: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    ASPECT_16_9: ((1300, 280), (1300, 830)),
    ASPECT_16_10: ((1300, 280), (1300, 980)) }
_BB_BABY_DRAGON_RECLICK_WAIT = 10
_BB_RETURN_HOME_TEMPLATE = 'breturnhome.png'
_BB_RETURN_HOME_TEMPLATE_1080P = 'breturnhome1920.png'
_BB_1080P_CAPTURE_SIZE = (1920, 1080)
_BB_1080P_SIZE_TOLERANCE = 40
_BB_TEMPLATE_SUPPRESS_PAD = 0.1
_BB_FULL_ELIXIR_CART_TEMPLATES = ('fullecart.png', 'fullecart2.png', 'fullecart3.png')
_BB_COLLECT_TEMPLATE = 'collect.png'
_BB_STAR_BONUS_TEMPLATE = 'bstar.png'
# "Star Bonus!" reward popup (Oct 2026 UI): its Okay sits this far (frame heights) below the title.
_BB_STAR_BONUS_POPUP_TEMPLATE = 'starbonus.png'
_BB_STAR_BONUS_OKAY_DY = 0.552
_BB_BATTLE_STAR_TEMPLATE = 'bbstar.png'
_BB_BATTLE_MACHINE_TEMPLATE = 'battlemachine.png'
_BB_FLYING_MACHINE_TEMPLATE = 'flyingmachine.png'
_BB_GOLD_PRIORITISE_MIN_STARS = 2
# Trophy prioritise: the battle is never ended early — stage 1 runs to 100%, the bot attacks
# the second village (stage 2) with the cards the troop bar offers there, then waits for the
# result screen. Battle time is capped well above both stages together.
_BB_TROPHY_BATTLE_TIMEOUT = 330
# Stage 2 starts once "Overall Damage" (bottom right) reads >= 100% on two reads in a row;
# the camera then flies to the second village, so the deploy waits this long after it.
_BB_TROPHY_STAGE2_SETTLE = 4.0
_BB_TROPHY_MAX_STAGE2_DEPLOYS = 1
_BB_TROPHY_REDEPLOY_WAIT = 6.0
# "Overall Damage  ★★★ 106%": the percent only (fractions of the 16:9 frame, measured 2560x1440).
_BB_DAMAGE_PERCENT_ROI = (0.925, 0.78, 0.99, 0.83)
# Troop bar: one card per camp, 1st card centre x 0.1732, one card every 0.0659, icon at y 0.93.
_BB_CARD_SLOT_X0 = 0.1732
_BB_CARD_SLOT_STEP = 0.0659
_BB_CARD_SLOT_Y = 0.93
_BB_CARD_SLOTS = 11
# Where a card is tapped: on the dragon's head. The green troop-switch button covers the
# lower half of the card (y 0.94-0.97, from just left of the centre), so never tap there.
_BB_CARD_TAP_Y = 0.905
_BB_CARD_TAP_DX = -0.006
# Troop-switch button (white arrows on green, bottom right of the card): shown only while the
# card's troop has not been deployed yet — it is gone once the troop is on the field.
# White pixels in its box: ~0.32 with the button, 0.00 without (measured both stages).
_BB_SWITCH_BOX = (-0.002, 0.945, 0.024, 0.968)   # x0, x1 from the slot centre; y0, y1
_BB_SWITCH_MIN_WHITE = 0.15
# Ready card: coloured and lit (measured sat ~130-143, val ~165); dead card: grey (sat 0);
# empty dashed slot: dark (val < 60).
_BB_CARD_READY_MIN_SAT = 60
_BB_CARD_READY_MIN_VAL = 100
# Baby Dragon edge deploy (both stages): full zoom-out, read the red border while the game
# shows it (a few seconds), one dragon per zone 2-8 tiles outside it, all within ~3 s.
_BB_ZOOM_OUT_CLICKS = 10
_BB_BORDER_READS = 4
_BB_BORDER_READ_GAP = 0.2
# Card select needs time to register before the drop (0.11 s was too short live); card +
# drop ~0.35 s per troop: 8 troops ~2.8 s, inside the 3 s window.
_BB_CARD_SELECT_PAUSE = 0.22
_BB_DEPLOY_CLICK_PAUSE = 0.12
# Dragons still on the bar after the drop (switch button still there): dropped again, closer
# to the border (2-3 tiles) on fresh zones, until placed or these rounds run out.
_BB_DEPLOY_RETRIES = 5
_BB_DEPLOY_RETRY_DISTANCE = (2.0, 3.0)
_BB_DEPLOY_CHECK_WAIT = 0.35
# Abilities: every deployed card clicked together, once, after a random cooldown.
_BB_ABILITY_DELAY = (10.0, 25.0)
_BB_RETURN_HOME_END_BATTLE_RETRIES = 5
_STAR_BONUS_THRESHOLD = 0.75
_TROOP_FAILURE_LIMIT = 4
_TROOP_RETRY_WAIT_SECONDS = 15  # training is instant since the Mar 2025 "Clash Anytime" update — this only lets the UI settle
_RELOAD_GRACE_SECONDS = 180  # let a quick phone check finish before reconnecting over it
_WALL_BATCH_MAX_ADDS = 15
_WALL_MENU_SCROLL_STEPS = 8  # OCR positions polled: as-opened + 7 wheel nudges down the list
_WALL_MENU_WHEEL_CLICKS = 2  # ~3-4 rows per nudge; the OCR band spans the whole popup so a nudge cannot jump the Wall row past it
_WALL_ROW_STABLE_TOL = 30  # ref px: max y drift between consecutive frames before the row is trusted for a click
_WALL_PANEL_SCROLL_STEPS = 14  # Build panel (UI ottobre 2026): ~35 rows, Wall sits in the last quarter
# Builder Base walls: open the Build panel only when the loot pays at least this many
# walls of the cheapest known level (one wall is not worth the ~20 s round).
_BB_WALL_MIN_WALLS = 2
# ...and keeps buying batches (up to this many per check) while the loot still pays that.
_BB_WALL_MAX_ROUNDS = 5
_WALL_GOLD_ATTACK_BUFFER = 50000  # gold kept for the Find a Match fee (same margin as UpgradePolicy)
_WALL_BAR_PITCH_FRAC = 0.081  # wall bar button pitch at 1x (frame-width fraction, 2559-wide frames)
_WALL_BAR_SCALES = (1.0, 0.95, 0.9, 0.85)  # wall selection bar: 1x on the map, ~0.90x beside the open Build panel
_AUTO_UPGRADE_SCAN_INTERVAL_SECONDS = 600  # full popup scan is OCR-heavy (~15-25s); keep it rare vs the ~35s attack cycle
_IDLE_RECHECK_SECONDS = 300  # while idling (storages full, nothing startable): wake, recover the screen, re-read state
# Loot-tracker plausibility caps per snapshot interval (one battle): a raid tops out
# well under these even with boosts — anything larger is an OCR misread that slipped
# past the ≥0 filter (live repro: "+15.5M elixir" in one battle).
_LOOT_DELTA_MAX_MAIN = 3000000
_LOOT_DELTA_MAX_DARK = 50000
# Super Minion drag: a new total duration in this range for every attack.
_SUPERMINION_DEPLOY_SECONDS = (2.8, 4.2)
# Collapse = a resource falling under this fraction of a previous value at least this
# big: a misread, not a spend (see _resolve_negative_loot).
_LOOT_COLLAPSE_RATIO = 0.1
_LOOT_COLLAPSE_MIN_MAIN = 100000
_LOOT_COLLAPSE_MIN_DARK = 10000
_LOOT_REREAD_WAIT = 0.8
_WALL_MENU_SCROLL_BASELINE: dict[str, tuple[int, int]] = {
    ASPECT_16_9: (1305, 605),
    ASPECT_16_10: (1305, 672) }

class Bot:
    '''Main Bot Logic.'''
    
    def __init__(self):
        self.config = Config()
        self.window = WindowService()
        self.stop_event = threading.Event()
        self.input = InputService(self.window, self.stop_event)
        self.vision = VisionService()
        self._battle_rewards = BattleRewards(self.window, self.input, self.stop_event)
        self.running = False
        self._earthquake_method = EARTHQUAKE_METHOD_CURVE
        self._loot_totals = (0, 0, 0)
        self._loot_prev_resources = None
        self._loot_session_start_mono = 0
        self._loot_callback = None
        self._suppress_loot_negative_error_once = False

    
    def start(self, method, run_time_minutes, star_bonus = False, status_callback = None, loot_callback = None, multi_run_players = None, ranked_fill = False, upgrade_walls = False, earthquake_method = EARTHQUAKE_METHOD_CURVE, builder_base = False, loot_prioritise = 'both', wall_upgrade_threshold = 0, auto_upgrade = MODE_OFF, reserve_builders = 1, state_callback = None, upgrade_order = None, bb_wall_upgrade_threshold = 0):
        '''Starts the bot loop. With ``multi_run_players``, runs a full session per enabled player.
        ``run_time_minutes <= 0`` (single Home Village runs only) means UNLIMITED — farm,
        upgrade and idle until the user stops the bot ("run until maxed").'''
        self._status_callback = status_callback
        self._loot_callback = loot_callback
        self._state_callback = state_callback
        self._earthquake_method = earthquake_method
        if not self.window.find_window():
            raise RuntimeError('Clash of Clans window not found. Please ensure the game is open.')
        self._reset_loot_session()
        self._reset_run_stats()
        self._emit_loot_update()
        self.running = True
        self.stop_event.clear()
        unlimited = not star_bonus and multi_run_players is None and int(run_time_minutes or 0) <= 0
        duration = 900 if star_bonus else (0 if unlimited else max(1, int(run_time_minutes)) * 60)
        mr = multi_run_players is not None
        self._builder_base = builder_base
        self._loot_prioritise = loot_prioritise
        self._wall_upgrade_threshold = max(0, int(wall_upgrade_threshold or 0))
        self._bb_wall_upgrade_threshold = max(0, int(bb_wall_upgrade_threshold or 0))
        self._auto_upgrade_mode = auto_upgrade if auto_upgrade in AUTO_UPGRADE_MODES else MODE_OFF
        self._auto_upgrade_last_scan = 0
        self._reserve_builders = max(0, int(reserve_builders or 0))
        self._upgrade_order = upgrade_order
        self._advisor = None  # one UpgradeAdvisor per session (it holds execution cooldowns)
        logger.info(f'''Bot started. Method: {method}, Time: {'unlimited' if unlimited else f'{run_time_minutes}m'}, StarBonus: {star_bonus}, MultiRun: {mr}, RankedFill: {ranked_fill}, UpgradeWalls: {upgrade_walls}, WallThreshold: {self._wall_upgrade_threshold}, BBWallThreshold: {self._bb_wall_upgrade_threshold}, AutoUpgrade: {self._auto_upgrade_mode}, ReserveBuilders: {self._reserve_builders}, Earthquake: {earthquake_method}, BuilderBase: {builder_base}, LootPrioritise: {loot_prioritise}''')

        try:

            if not multi_run_players is None:
                self._ensure_correct_village(builder_base = False)
                queue = [ p for p in multi_run_players if p.enabled ]
                if not queue:
                    raise RuntimeError('Multi-run: no players marked Run')
                for player in queue:
                    self._check_stop()
                    self._switch_account_and_load_home(player.name)
                    self._check_stop()
                    self._run_loop(method, duration, star_bonus, ranked_fill, upgrade_walls)
                    self._check_stop()
                    self._multi_run_builder_base_after_session()
                    self._check_stop()
            elif self._builder_base:  # [recovered: decompiler nested this single-run block inside the multi-run `if`]
                self._ensure_correct_village(builder_base = True)
                self._run_builder_base_loop(duration, star_bonus = star_bonus, upgrade_walls = upgrade_walls)
            else:
                self._ensure_correct_village(builder_base = False)
                self._run_loop(method, duration, star_bonus, ranked_fill, upgrade_walls)
        except InterruptedError:
            logger.info('Bot stopped by user.')
        except Exception as e:
            logger.error(f'''Bot crashed: {e}''', exc_info = True)
            raise
        finally:
            self.running = False
            self._earthquake_method = EARTHQUAKE_METHOD_CURVE
            logger.info('Bot stopped.')
            # Timer end, user stop or crash alike: always report the session.
            try:
                self._final_loot_snapshot()
                self.last_run_summary = self._build_run_summary()
                for line in self.last_run_summary.splitlines():
                    logger.info(line)
                self.last_run_stats = self._build_run_stats()
            except Exception:
                logger.warning('Run summary failed', exc_info = True)

    
    def stop(self):
        '''Signals the bot to stop.'''
        self.running = False
        self.stop_event.set()

    
    def _reset_loot_session(self):
        '''Reset counters for a new :meth:`start` — no disk persistence.'''
        self._loot_totals = (0, 0, 0)
        self._loot_prev_resources = None
        self._loot_session_start_mono = time.monotonic()
        self._suppress_loot_negative_error_once = False
        self._loot_held = set()
        self._last_hud_triplet = None
        self._gold_pinned = False
        self._elixir_pinned = False

    
    # ---- end-of-run summary ----

    def _reset_run_stats(self):
        self._run_started_mono = time.monotonic()
        self._attacks_done = 0
        self._bb_attacks_done = 0
        self._walls_upgraded = []  # dicts: count, from_level, cost, resource
        self.last_run_summary = None
        self.last_run_stats = None

    def _build_run_stats(self):
        '''The same session numbers as the log summary, as plain values for the UI's
        "Last session" card.'''
        (gold, elixir, dark) = getattr(self, '_loot_totals', (0, 0, 0))
        walls = getattr(self, '_walls_upgraded', [])
        spent = {'gold': 0, 'elixir': 0}
        for w in walls:
            if w.get('cost') and w.get('resource') in spent:
                spent[w['resource']] += w['cost']
        duration = int(max(0, time.monotonic() - getattr(self, '_run_started_mono', time.monotonic())))
        if getattr(self, '_builder_base', False):
            # Builder Base runs have their own "Last session" card in the UI.
            return {'village': 'builder', 'duration_s': duration,
                    'attacks': int(getattr(self, '_bb_attacks_done', 0)),
                    'walls': int(sum(w['count'] for w in walls)),
                    'walls_gold': spent['gold'], 'walls_elixir': spent['elixir']}
        return {
            'village': 'home',
            'duration_s': duration,
            'attacks': int(getattr(self, '_attacks_done', 0)),
            'gold': int(gold), 'elixir': int(elixir), 'dark': int(dark),
            'walls': int(sum(w['count'] for w in walls)),
            'walls_gold': spent['gold'], 'walls_elixir': spent['elixir']}

    def _final_loot_snapshot(self):
        '''Count the LAST battle's loot too: the tracker only adds a battle's gains at
        the next pre-attack snapshot, which never comes once the run ends. Reads the
        HUD directly (the stop event is already set, so the stop-aware stable read
        would bail out) — two agreeing frames, home screen only.'''
        if self._loot_prev_resources is None:
            return
        reads = []
        for _ in range(3):
            frame = self.window.screenshot()
            if frame is not None and frame.size:
                self._update_config_size(frame)
                (ax, _ay) = self.vision.find_template(frame, 'attack.png', region = VisionService.bottom_half_region(frame))
                if not ax:
                    return  # not home (mid-battle stop): that battle's loot is not banked yet
                reads.append(read_hud_triplet(frame))
            if len(reads) >= 2 and reads[-1] is not None and reads[-1] == reads[-2]:
                break
            time.sleep(0.35)
        if len(reads) < 2 or reads[-1] is None or reads[-1] != reads[-2]:
            return
        (cur_g, cur_el, cur_de) = reads[-1]
        (lg, le, ld) = self._loot_prev_resources
        (dg, d_el, d_de) = (cur_g - lg, cur_el - le, cur_de - ld)
        if (0 <= dg <= _LOOT_DELTA_MAX_MAIN and 0 <= d_el <= _LOOT_DELTA_MAX_MAIN and 0 <= d_de <= _LOOT_DELTA_MAX_DARK
                and (dg or d_el or d_de)):
            (tg, te, td) = self._loot_totals
            self._loot_totals = (tg + dg, te + d_el, td + d_de)
            self._loot_prev_resources = reads[-1]
            logger.info('Loot tracker (end of run): +%s / +%s / +%s (G/E/DE)', dg, d_el, d_de)
            self._emit_loot_update()

    @staticmethod
    def _fmt_int(value):
        return f'{int(value):,}'.replace(',', '.')

    @staticmethod
    def _per_wall_cost(entry):
        if entry.get('cost') and entry.get('count'):
            return round(entry['cost'] / entry['count'])
        return entry.get('per_wall')

    def _walls_with_levels(self, walls):
        '''Fill in levels the bar title did not read (~1 in 5): within a run the same
        one-wall price means the same wall level, so a price seen WITH a level read
        names the level of every batch at that price. A price seen with two different
        levels is ambiguous and fills nothing.'''
        by_price = {}
        for w in walls:
            price = self._per_wall_cost(w)
            if price and w.get('from_level'):
                by_price.setdefault(price, set()).add(w['from_level'])
        filled = []
        for w in walls:
            levels = by_price.get(self._per_wall_cost(w), set())
            if not w.get('from_level') and len(levels) == 1:
                w = dict(w, from_level = next(iter(levels)))
            filled.append(w)
        return filled

    def _build_run_summary(self):
        elapsed = int(max(0, time.monotonic() - getattr(self, '_run_started_mono', time.monotonic())))
        (gold, elixir, dark) = getattr(self, '_loot_totals', (0, 0, 0))
        walls = getattr(self, '_walls_upgraded', [])
        names = {'gold': 'oro', 'elixir': 'elisir'}
        if getattr(self, '_builder_base', False):
            lines = [
                '===== Riepilogo run (Builder Base) =====',
                f'Durata: {elapsed // 3600}h {elapsed % 3600 // 60:02d}m {elapsed % 60:02d}s',
                f'Attacchi Builder Base: {getattr(self, "_bb_attacks_done", 0)}',
                f'Muri migliorati: {sum(w["count"] for w in walls)}']
        else:
            lines = [
                '===== Riepilogo run =====',
                f'Durata: {elapsed // 3600}h {elapsed % 3600 // 60:02d}m {elapsed % 60:02d}s',
                f'Attacchi: {getattr(self, "_attacks_done", 0)}',
                f'Risorse farmate: oro {self._fmt_int(gold)} | elisir {self._fmt_int(elixir)} | dark {self._fmt_int(dark)}',
                f'Muri migliorati: {sum(w["count"] for w in walls)}']
        # One line per wall level: count and spend per resource summed over the run.
        groups = {}
        spent = {}
        for w in self._walls_with_levels(walls):
            group = groups.setdefault(w.get('from_level'), {'count': 0, 'cost': {}})
            group['count'] += w['count']
            if w.get('cost') and w.get('resource'):
                group['cost'][w['resource']] = group['cost'].get(w['resource'], 0) + w['cost']
                spent[w['resource']] = spent.get(w['resource'], 0) + w['cost']
        for level in sorted(groups, key = (lambda lv: (lv is None, lv or 0))):
            group = groups[level]
            label = f'liv. {level} → {level + 1}' if level else 'livello ?'
            costs = ' + '.join(f'{self._fmt_int(v)} {names.get(k, k)}' for k, v in sorted(group['cost'].items(), key = (lambda kv: kv[0] != 'gold')))
            lines.append(f'  - {group["count"]} {"muro" if group["count"] == 1 else "muri"} {label}: {costs or "costo ?"}')
        if spent:
            lines.append('Speso in muri: ' + ' | '.join(f'{names.get(k, k)} {self._fmt_int(v)}' for k, v in sorted(spent.items())))
        return '\n'.join(lines)

    def _emit_loot_update(self):
        cb = self._loot_callback
        if not cb:
            return None
        (g, el, de) = self._loot_totals
        elapsed = max(0, time.monotonic() - float(self._loot_session_start_mono))
        cb(g, el, de, elapsed)

    
    def _loot_snapshot_before_attack(self):
        '''
On home: OCR top‑right HUD, diff vs previous snapshot, accumulate non‑negative deltas,
refresh the baseline.

Called before wall upgrades (when storages full) **and** immediately before tapping
Attack so post‑raid gains are recorded **before** wall spend can make the next snapshot
look like a decrease on every resource vs that baseline (which would skip the add).

When deltas vs the previous snapshot are not all non-negative, session totals are not
incremented unless ``_suppress_loot_negative_error_once`` suppresses one skip (set after
wall upgrades for the first pre-Attack snapshot that would otherwise count as an error).
'''
        # Consecutive-frame agreement: single HUD reads get corrupted by animations
        # (live repro: elixir "115M" — an upward misread passes the ≥0 filter and
        # poisons the session totals). No stable read this cycle → just skip.
        triplet = self._read_hud_triplet_stable()
        if triplet is None:
            logger.debug('Loot tracker: no stable HUD read this cycle')
            self._emit_loot_update()
            return None
        self._last_hud_triplet = triplet
        (cur_g, cur_el, cur_de) = triplet
        prev = self._loot_prev_resources
        # Cap detection without TH-specific numbers: at a TRUE cap, consecutive
        # stable pre-attack reads pin to the identical value (raids refill the
        # entry fee back to cap); below cap every battle moves the number. The
        # full-storage icons fire from ~85% up, so they alone must not idle the
        # bot away from real remaining headroom.
        if prev is not None:
            self._gold_pinned = cur_g == prev[0]
            self._elixir_pinned = cur_el == prev[1]
        skipped_due_to_negative_delta = False
        if not prev is None:
            (lg, le, ld) = prev
            dg = cur_g - lg
            d_el = cur_el - le
            d_de = cur_de - ld
            if dg < 0 or d_el < 0 or d_de < 0:
                if not self._suppress_loot_negative_error_once:
                    # Not a wall round: a real small spend or a misread — resolve it per
                    # resource instead of dropping the whole battle.
                    (triplet, gains) = self._resolve_negative_loot(prev, triplet)
                    self._loot_prev_resources = triplet
                    if any(gains):
                        (tg, te, td) = self._loot_totals
                        self._loot_totals = (tg + gains[0], te + gains[1], td + gains[2])
                        logger.info('Loot tracker: +%s / +%s / +%s (G/E/DE) → session %s / %s / %s', gains[0], gains[1], gains[2], self._loot_totals[0], self._loot_totals[1], self._loot_totals[2])
                    self._emit_loot_update()
                    return None
            else:
                self._loot_held = set()
            if dg >= 0 and d_el >= 0 and d_de >= 0:
                if dg <= _LOOT_DELTA_MAX_MAIN and d_el <= _LOOT_DELTA_MAX_MAIN and d_de <= _LOOT_DELTA_MAX_DARK:
                    (tg, te, td) = self._loot_totals
                    self._loot_totals = (tg + dg, te + d_el, td + d_de)
                    logger.info('Loot tracker: +%s / +%s / +%s (G/E/DE) → session %s / %s / %s', dg, d_el, d_de, self._loot_totals[0], self._loot_totals[1], self._loot_totals[2])
                else:
                    # One battle cannot earn this much — an OCR misread slipped through.
                    logger.warning('Loot tracker: implausible gain +%s/+%s/+%s discarded (OCR misread); baseline refreshed', dg, d_el, d_de)
            else:
                skipped_due_to_negative_delta = True
                self._loot_held = set()
                if self._suppress_loot_negative_error_once:
                    # Expected: the wall round right before this snapshot spent loot (the
                    # battle's gains were already banked by the snapshot taken before it).
                    logger.info('Loot tracker: spent on walls %s / %s / %s (G/E/DE) — baseline refreshed', max(0, lg - cur_g), max(0, le - cur_el), max(0, ld - cur_de))
                else:
                    logger.warning('Loot tracker: negative delta — previous gold/elixir/dark=%s/%s/%s current read=%s/%s/%s', lg, le, ld, cur_g, cur_el, cur_de)
        self._loot_prev_resources = triplet
        self._emit_loot_update()
        if skipped_due_to_negative_delta:
            if self._suppress_loot_negative_error_once:
                self._suppress_loot_negative_error_once = False
                return None
            return None
        self._suppress_loot_negative_error_once = False

    
    @staticmethod
    def _loot_collapsed(previous, current, index):
        '''A resource that fell to under a tenth of a sizeable previous value between two
        battles: no single purchase does that, a partial HUD read does (live: elixir
        979299 → "6", 1957852 → "90913").'''
        floor = _LOOT_COLLAPSE_MIN_DARK if index == 2 else _LOOT_COLLAPSE_MIN_MAIN
        return previous >= floor and current < previous * _LOOT_COLLAPSE_RATIO

    def _resolve_negative_loot(self, prev, triplet):
        '''Some resource went down outside a wall round. Returns (baseline, gains).
        A collapse is re-read once; if it persists, that resource keeps its previous
        value for one cycle (adopting the misread made the NEXT battle count a fake
        +2–3M). Other drops — the Find a Match fee, a building upgrade, or the same
        collapse seen twice — are real spends: adopt the read, no gain.'''
        held = getattr(self, '_loot_held', set())
        if any(self._loot_collapsed(p, c, i) and i not in held for (i, (p, c)) in enumerate(zip(prev, triplet))):
            if self.stop_event.wait(_LOOT_REREAD_WAIT):
                return (triplet, (0, 0, 0))
            again = self._read_hud_triplet_stable()
            if again is not None and again != triplet:
                logger.info('Loot tracker: suspicious drop (read %s/%s/%s) — re-read %s/%s/%s', *triplet, *again)
                triplet = again
        baseline = list(triplet)
        gains = [0, 0, 0]
        new_held = set()
        for (i, (p, c)) in enumerate(zip(prev, triplet)):
            if c >= p:
                gains[i] = c - p
            elif self._loot_collapsed(p, c, i) and i not in held:
                baseline[i] = p
                new_held.add(i)
                logger.warning('Loot tracker: %s read %s after %s looks like a misread — keeping the previous value for one cycle', ('gold', 'elixir', 'dark')[i], c, p)
        self._loot_held = new_held
        if gains[0] > _LOOT_DELTA_MAX_MAIN or gains[1] > _LOOT_DELTA_MAX_MAIN or gains[2] > _LOOT_DELTA_MAX_DARK:
            logger.warning('Loot tracker: implausible gain +%s/+%s/+%s discarded (OCR misread); baseline refreshed', *gains)
            gains = [0, 0, 0]
        return (tuple(baseline), tuple(gains))

    def _check_stop(self):
        if self.stop_event.is_set():
            raise InterruptedError('Bot stopped by user')

    
    def _update_config_size(self, frame):
        '''Reload aspect profile if screenshot size implies a different template folder.'''
        self.config.set_target_size_from_frame(frame)

    
    def _scroll_point(self):
        '''Scroll anchor in authoring space [1000,1000]; scaled to current capture.'''
        (x, y) = self.config.scale_point([
            1000,
            1000])
        return (x, y)

    
    def _nudge_view_to_reveal_attack(self):
        '''Click ``empty`` (``data.json``) and scroll at anchor to nudge village until Attack is findable.'''
        self.input.click(pause = 0.15, *self.config.get_point('empty'))
        self.input.scroll(*self._scroll_point(), 5)

    
    def _find_home_village_builder(self, frame, region = None):
        # UI di ottobre 2026: i ritratti sono in basso a destra; la regione passata dai chiamanti
        # (metà alta, valida per la vecchia UI) viene ignorata.
        region = VisionService.bottom_right_quadrant_region(frame)
        for name in _HOME_VILLAGE_BUILDER_TEMPLATES:
            (x, y) = self.vision.find_template(frame, name, region = region)
            if not x:
                continue
            return (x, y)
        return (None, None)

    
    def _wall_menu_drag_to_bottom(self):
        '''Drag the builder upgrade list to its bottom so ``Wall`` (list end) is revealed.

Touch-style swipe up: click low in the list, drag to the top, release — the reverse of
the old wheel scroll. Baseline coords are scaled via :meth:`Config.scale_point`. Dragging
past the bottom is a harmless no-op, so this can be called repeatedly.
'''
        pair = _WALL_OCR_RETRY_DRAG_BASELINE.get(self.config.aspect_key)
        if pair is None:
            logger.warning('wall menu drag: unknown aspect %r; skipping drag', self.config.aspect_key)
            return None
        (top_ref, bottom_ref) = pair
        top = self.config.scale_point([
            top_ref[0],
            top_ref[1]])
        bottom = self.config.scale_point([
            bottom_ref[0],
            bottom_ref[1]])
        (x_top, y_top) = (int(top[0]), int(top[1]))  # [recovered: pycdc reversed STORE_FAST_STORE_FAST pairs]
        (x_bot, y_bot) = (int(bottom[0]), int(bottom[1]))
        self.input.move(x_bot, y_bot)
        self.input.mouse_down(x_bot, y_bot)
        
        try:
            self.input.human_move(x_bot, y_bot, x_top, y_top, duration = 0.5)
            self.input.mouse_up(x_top, y_top)
            return None
        except:
            self.input.mouse_up(x_top, y_top)


    
    def _wall_menu_drag_retry_nudge(self):
        '''Vertical drag in the builder list when ``wall`` OCR misses (~0.5s eased move + hold pause).'''
        pair = _WALL_OCR_RETRY_DRAG_BASELINE.get(self.config.aspect_key)
        if pair is None:
            logger.warning('wall OCR retry drag: unknown aspect %r; skipping drag', self.config.aspect_key)
            return None
        (p1_ref, p2_ref) = pair
        p1 = self.config.scale_point([
            p1_ref[0],
            p1_ref[1]])
        p2 = self.config.scale_point([
            p2_ref[0],
            p2_ref[1]])
        (x1, y1) = (int(p1[0]), int(p1[1]))  # [recovered: pycdc reversed STORE_FAST_STORE_FAST pairs]
        (x2, y2) = (int(p2[0]), int(p2[1]))
        self.input.move(x1, y1)
        self.input.mouse_down(x1, y1)
        
        try:
            self.input.human_move(x1, y1, x2, y2, duration = 0.5)
            if self.stop_event.wait(0.3):
                self.input.mouse_up(x2, y2)
                return None
            self.input.mouse_up(x2, y2)
            return None
        except:
            self.input.mouse_up(x2, y2)


    
    def _find_wall_row_once(self):
        '''One fresh screenshot → Wall label OCR, both polarities (dark popup text first).'''
        frame = self.window.screenshot()
        if frame is None:
            return None
        self._update_config_size(frame)
        # Blob filter kills the small label glyphs at this capture size (live A/B:
        # 0/83 hits with filter, 14/83 without), keep it off.
        for white in (False, True):
            pt = VisionService.find_wall_labels_top_center_ocr(frame, white_text = white, cc_filter_blobs = False)
            if pt:
                return pt
        return None


    def _wall_menu_scroll_point(self):
        '''Wheel target inside the builder popup body (authoring space, per aspect).'''
        ref = _WALL_MENU_SCROLL_BASELINE.get(self.config.aspect_key)
        if ref is None:
            ref = _WALL_MENU_SCROLL_BASELINE[ASPECT_16_10]
        (x, y) = self.config.scale_point([
            ref[0],
            ref[1]])
        return (int(x), int(y))


    def _should_upgrade_walls(self):
        '''True when a full-storage hero-bar icon shows, or HUD gold/elixir is at/above the configured threshold.'''
        frame = self.window.screenshot()
        if frame is None:
            return False
        self._update_config_size(frame)
        triplet = read_hud_triplet(frame)
        if self._can_pay_any_wall(triplet) is False:
            # Opening the panel (~20s) when no known wall level is payable is pure waste.
            logger.info('Wall upgrades: gold=%s elixir=%s cannot pay any known wall level %s — skipping the panel', triplet[0], triplet[1], self._wall_costs_text())
            return False
        (gx, gy) = VisionService.find_active_hgoldfull(frame)
        (ex, ey) = VisionService.find_active_helixirfull(frame)
        if gx is not None or ex is not None:
            logger.info('Wall upgrades: full-storage icon detected')
            return True
        threshold = int(getattr(self, '_wall_upgrade_threshold', 0) or 0)
        if threshold <= 0:
            return False
        if triplet is None:
            return False
        (gold, elixir, _) = triplet
        if gold >= threshold or elixir >= threshold:
            logger.info('Wall upgrades: loot gold=%s elixir=%s reached threshold %s', gold, elixir, threshold)
            return True
        return False


    # ---- wall prices (UI ottobre 2026: one Build-panel row per wall level) ----

    def _remember_wall_costs(self, rows):
        '''Add the one-wall price of every Wall row in ``rows`` to the saved set (the
        wall walk's frames, the auto-upgrade scan). Returns the prices found. The set
        is only REPLACED by a wall walk that covered the whole list (see
        _find_wall_row_build_panel) — merged scan rows can fold same-label levels.'''
        costs = {r.cost for r in rows if is_wall_row(r) and r.cost}
        resources = getattr(self, '_wall_cost_resource', None)
        if resources is None:
            resources = self._wall_cost_resource = {}
        for r in rows:
            if is_wall_row(r) and r.cost and getattr(r, 'resource', None):
                resources[r.cost] = r.resource
        if costs:
            self._wall_costs = set(getattr(self, '_wall_costs', set())) | costs
        return costs

    def _wall_costs_text(self):
        return sorted(getattr(self, '_wall_costs', set()) or [])

    def _wall_gold_only(self, cost):
        '''Wall level that takes gold only: its multi bar showed no elixir button, or (Builder
        Base) its Build-panel row is priced in gold — low BB wall levels have no elixir option.'''
        if cost in getattr(self, '_wall_gold_only_costs', set()):
            return True
        return getattr(self, '_builder_base', False) and getattr(self, '_wall_cost_resource', {}).get(cost) == 'gold'

    def _wall_payable(self, cost, triplet, walls = 1):
        (gold, elixir, _dark) = triplet
        reserve = 0 if getattr(self, '_builder_base', False) else _WALL_GOLD_ATTACK_BUFFER
        if gold - reserve >= cost * walls:
            return True
        return not self._wall_gold_only(cost) and elixir >= cost * walls

    def _can_pay_any_wall(self, triplet, walls = 1):
        '''True / False: some known wall level is payable (gold-only levels by gold alone);
        None when unknown (no prices saved yet, or the HUD did not read) — callers then
        fall back to trying.'''
        costs = getattr(self, '_wall_costs', None)
        if not costs or triplet is None:
            return None
        return any(self._wall_payable(cost, triplet, walls) for cost in costs)

    @staticmethod
    def _pay_slot_blocked(slot):
        '''A pay button that is missing (gold-only level: no elixir button), unmeasured or red.'''
        return not slot.found or slot.cost_roi_xywh is None or slot.redness >= 0.2

    def _deselect_wall_ui(self):
        '''Tap empty ground to close the wall selection bar / gem dialog remnants. The wall
bar has no X button — while it is open, the next tap anywhere is swallowed by the
deselect, which would eat the upcoming Attack click.'''
        if self.config.aspect_key == ASPECT_16_9:
            # UI ottobre 2026: never the generic okay/exit dismiss here — it pressed the
            # "Upgrade Walls" popup's Okay blind (live repro: an 8M batch confirmed while
            # the log said "nothing confirmed"). close_all only ever backs out.
            BuildPanel(self).close_all()
            self.input.click(pause = 0.3, *self.config.get_point('empty'))
            return
        self._dismiss_open_popup()
        self.input.click(pause = 0.3, *self.config.get_point('empty'))


    def _maybe_upgrade_walls(self, upgrade_walls):
        '''Upgrade walls on home when enabled and loot is high enough (threshold or full
        storages) — checked after every attack, the user's threshold is the only gate.'''
        if not upgrade_walls or not self._should_upgrade_walls():  # [recovered: decompiler dropped the second `not`, so it upgraded only when storages were NOT full]
            return None
        cb = getattr(self, '_status_callback', None)
        if cb:
            cb('Upgrading walls...')
        self._loot_snapshot_before_attack()
        confirmed = 0
        for round_no in range(2):
            self._check_stop()
            if round_no:
                # Second round only when what is LEFT still pays at least one wall level
                # (fresh, consecutive-frame HUD read after the first batch was paid).
                triplet = self._read_hud_triplet_stable()
                if self._can_pay_any_wall(triplet) is False:
                    logger.info('Wall upgrades: gold=%s elixir=%s left — no wall level %s payable, skipping the second round', triplet[0], triplet[1], self._wall_costs_text())
                    break
            self._wall_upgrade_confirmed = False
            self._upgrade_walls()
            self._deselect_wall_ui()
            if not self._wall_upgrade_confirmed:
                break  # nothing bought: a second walk over the same loot buys nothing either
            confirmed += 1
        if confirmed == 0:
            logger.info('Wall upgrades: nothing confirmed this round')
        self._suppress_loot_negative_error_once = True


    def _maybe_upgrade_bb_walls(self, upgrade_walls):
        '''Builder Base walls, between attacks: same Build-panel flow as the Home Village
        (Wall row → Upgrade More → add while payable → elixir first → Okay). Opens the
        panel once to learn the wall prices, then only when the HUD pays at least
        _BB_WALL_MIN_WALLS walls of the cheapest level. No loot tracker here — the BB
        has no gold/elixir/dark loot session.'''
        if not upgrade_walls:
            return None
        frame = self.window.screenshot()
        if frame is None:
            return None
        self._update_config_size(frame)
        triplet = read_hud_triplet(frame)
        costs = getattr(self, '_wall_costs', None)
        if costs:
            if triplet is None:
                return None
            threshold = int(getattr(self, '_bb_wall_upgrade_threshold', 0) or 0)
            if threshold > 0:
                # The user's own amount, and at least one wall level must be payable
                # with what is there (gold-only levels by gold alone).
                reason = f'threshold {threshold}'
                if (triplet[0] < threshold and triplet[1] < threshold) or not self._can_pay_any_wall(triplet):
                    return None
            else:
                reason = f'{_BB_WALL_MIN_WALLS}+ walls of a payable level'
                if not self._can_pay_any_wall(triplet, _BB_WALL_MIN_WALLS):
                    return None
            logger.info('Builder Base walls: gold=%s elixir=%s reached %s — upgrading', triplet[0], triplet[1], reason)
        elif getattr(self, '_bb_wall_probed', False):
            return None  # prices unknown after one look: no Wall row to upgrade
        else:
            if not self.vision.find_template(frame, 'attack.png', region = VisionService.bottom_half_region(frame))[0]:
                return None  # not home yet (popup, battle): look for the prices next time
            logger.info('Builder Base walls: first pass — reading the wall prices')
        self._bb_wall_probed = True
        cb = getattr(self, '_status_callback', None)
        if cb:
            cb('Builder Base: upgrading walls...')
        rounds = 0
        for round_no in range(_BB_WALL_MAX_ROUNDS):
            self._check_stop()
            if round_no:
                # Another batch only while what is LEFT pays two walls of the cheapest level.
                triplet = self._read_hud_triplet_stable()
                costs = getattr(self, '_wall_costs', None)
                if triplet is None or not costs:
                    break
                if not self._can_pay_any_wall(triplet, _BB_WALL_MIN_WALLS):
                    logger.info('Builder Base walls: gold=%s elixir=%s left — not enough for another batch', triplet[0], triplet[1])
                    break
                logger.info('Builder Base walls: round %d — gold=%s elixir=%s still pay more walls', round_no + 1, triplet[0], triplet[1])
            self._wall_upgrade_confirmed = False
            self._upgrade_walls()
            self._deselect_wall_ui()
            if not self._wall_upgrade_confirmed:
                break
            rounds += 1
        if rounds:
            logger.info('Builder Base walls: %d batch(es) confirmed this check', rounds)
        return None

    def _maybe_auto_upgrade(self, force = False):
        '''Interval-gated builder-popup scan + upgrade decision/execution (see
        UpgradeAdvisor). ``force=True`` bypasses the interval (used when storages fill
        up — the idle gate needs a spend attempt NOW, not in 10 minutes). A failure
        here must never take down the farm loop. Returns the PassResult or None.'''
        mode = getattr(self, '_auto_upgrade_mode', MODE_OFF)
        if mode == MODE_OFF:
            return None
        now = time.monotonic()
        if not force and now - getattr(self, '_auto_upgrade_last_scan', 0) < _AUTO_UPGRADE_SCAN_INTERVAL_SECONDS:
            return None
        self._auto_upgrade_last_scan = now
        try:
            if getattr(self, '_advisor', None) is None:
                self._advisor = UpgradeAdvisor(self.window, self.input, self.vision, self.config, self.stop_event)
            result = self._advisor.run_pass(mode, reserve_builders = getattr(self, '_reserve_builders', 1),
                                            order = getattr(self, '_upgrade_order', None))
            if result is not None and result.scan is not None:
                # The full-list scan sees every wall level: free price data for the wall flow.
                self._remember_wall_costs(result.scan.rows)
            cb = getattr(self, '_status_callback', None)
            if cb and result is not None and result.pick is not None:
                cb(f'''Upgrades: {result.note}''')
            self._emit_state(note = result.note if result else None,
                             builders = result.scan.chip if result and result.scan else None)
            return result
        except InterruptedError:
            raise
        except Exception:
            logger.warning('Auto-upgrade pass failed; continuing farm loop', exc_info = True)
            return None

    def _emit_state(self, state = None, builders = None, lab = None, storages = None, note = None):
        '''Push a live-state update to the UI panel (best-effort, never raises).'''
        cb = getattr(self, '_state_callback', None)
        if not cb:
            return None
        try:
            cb({ 'state': state, 'builders': builders, 'lab': lab, 'storages': storages, 'note': note })
        except Exception:
            logger.debug('State callback failed', exc_info = True)

    def _read_state_stable(self, attempts = 3):
        def _capture():
            frame = self.window.screenshot()
            if frame is not None and frame.size:
                self._update_config_size(frame)
            return frame
        return read_village_state_stable(_capture, self.stop_event.wait, attempts)

    def _read_hud_triplet_stable(self):
        def _capture():
            frame = self.window.screenshot()
            if frame is not None and frame.size:
                self._update_config_size(frame)
            return frame
        return read_hud_triplet_stable(_capture, self.stop_event.wait)

    @staticmethod
    def _fmt_resource(value):
        value = int(value)
        if value >= 1000000:
            return f'''{value / 1000000:.1f}M'''
        if value >= 10000:
            return f'''{value / 1000:.0f}k'''
        return str(value)

    def _emit_village_state(self, state, mode_label):
        if state is None:
            return None
        # Storages field: real OCR'd amounts (from the last stable loot snapshot) plus
        # the game's bar-fill flags. The flat-swatch "full" templates fire from ~90%
        # up, so they are labeled "~full", never "full".
        flags = []
        if state.gold_full:
            flags.append('gold ~full')
        if state.elixir_full:
            flags.append('elixir ~full')
        triplet = getattr(self, '_last_hud_triplet', None)
        if triplet is not None:
            storages = f'''{self._fmt_resource(triplet[0])} / {self._fmt_resource(triplet[1])} / {self._fmt_resource(triplet[2])}'''
            if flags:
                storages += f''' ({', '.join(flags)})'''
        else:
            storages = ', '.join(flags) if flags else 'filling'
        self._emit_state(state = mode_label, builders = state.builders, lab = state.lab, storages = storages)

    def _maybe_idle(self, deadline):
        '''The "run until maxed" idle gate. When both main storages are full and a
        forced upgrade pass could not spend anything, attacking earns nothing — wait
        in place (game session kept alive via recovery on each wake) until a builder
        frees up or loot is spent, instead of stopping or attacking pointlessly.

        Dark elixir has no full-storage indicator; while gold/elixir still have room
        the normal farm loop is what fills DE. Pet House state is invisible on the
        home screen (no HUD chip, no builder-popup row — verified live), so pets are
        the user's manual job and never block idling; the status line calls out an
        idle LAB so research (also manual for now) is never silently forgotten.'''
        if getattr(self, '_auto_upgrade_mode', MODE_OFF) not in LIVE_UPGRADE_MODES:
            return None
        frame = self.window.screenshot()
        if frame is None:
            return None
        self._update_config_size(frame)
        state = read_village_state(frame)
        self._emit_village_state(state, 'farming')
        if state is None:
            return None
        reserve = getattr(self, '_reserve_builders', 1)
        free = state.free_builders
        # Spend eagerly: ANY full storage with a spare builder is money leaking (live
        # pain: Grand Warden started with elixir, then the free builder sat next to a
        # full gold storage for 10 minutes waiting on the interval pass).
        eager = free is not None and free > reserve and (state.gold_full or state.elixir_full)
        if not state.storages_full and not eager:
            return None
        if not state.storages_full:
            # Eager-only trigger: rate-limit so a full-gold stretch with nothing
            # startable does not burn a ~20s scan every battle cycle.
            now = time.monotonic()
            if now - getattr(self, '_eager_spend_last', 0) < 180:
                return None
            self._eager_spend_last = now
        logger.info('Idle gate: spend burst (%s) — forcing upgrade passes', state.summary())
        # Burn through candidates NOW instead of one per 5-minute wake: every failed
        # pick lands on cooldown so each retry reaches the next candidate, and every
        # SUCCESS frees loot but may leave another builder idle — keep going until
        # nothing is pickable or the attempts are spent.
        for _attempt in range(5):
            result = self._maybe_auto_upgrade(force = True)
            if result is None:
                break  # scan preconditions failed
            if result.pick is None and not result.collecting:
                break  # genuinely nothing pickable remains (a collect pass is not a verdict)
        state = self._read_state_stable()
        if state is None or not state.storages_full:
            return None
        if not (getattr(self, '_gold_pinned', False) and getattr(self, '_elixir_pinned', False)):
            # Icons say ~full but the values are still moving — real headroom remains
            # (live: idled at 18M/21M gold, wasting ~3M of farmable gold). Keep
            # farming until both numbers pin at their caps.
            logger.info('Idle gate: storages ~full but still filling (gold pinned=%s, elixir pinned=%s) — farming on', getattr(self, '_gold_pinned', False), getattr(self, '_elixir_pinned', False))
            return None
        reserve = getattr(self, '_reserve_builders', 1)
        cb = getattr(self, '_status_callback', None)
        logger.info('Idle gate: nothing startable with storages full (%s) — pausing attacks, rechecking every %ds', state.summary(), _IDLE_RECHECK_SECONDS)
        while True:
            self._check_stop()
            if deadline and time.time() >= deadline:
                return None
            msg = f'''Idling — {state.summary() if state else 'state unreadable'}; recheck in {_IDLE_RECHECK_SECONDS // 60}m'''
            if state is not None and state.lab_idle:
                msg += ' — LAB IS IDLE: start a research!'
            if cb:
                cb(msg)
            self._emit_village_state(state, 'idling')
            if self.stop_event.wait(_IDLE_RECHECK_SECONDS):
                return None
            # The game disconnects after a few idle minutes — recovery clicks Reload
            # (after its own grace period) and walks back to the home screen.
            self._home_screen_recovery()
            state = self._read_state_stable()
            if state is None:
                continue
            if not state.storages_full:
                if state.builders is None:
                    # Unreadable builder chip = probably not a clean home frame (mid-
                    # recovery, reload dialog) — the missing full-icons prove nothing.
                    # Stay idle; the next wake re-reads (live repro: one wake exited on
                    # "builders ? free, storages filling" right after a disconnect).
                    logger.info('Idle: degraded read (%s) — staying idle', state.summary())
                    continue
                logger.info('Idle over: storages have room again (%s)', state.summary())
                break
            free = state.free_builders
            if free is not None and free > reserve:
                logger.info('Idle over: %d builder(s) free (%s)', free, state.summary())
                break
        self._auto_upgrade_last_scan = 0  # resume with an immediate scan so the freed builder is used
        if cb:
            cb('Resuming — ' + state.summary())
        self._emit_village_state(state, 'farming')


    def _upgrade_walls_pick_resource_and_okay(self):
        '''Fresh frame → click an affordable resource slot → Okay. If neither resource can pay, close the popup instead (never confirm a red cost).'''
        frame = self.window.screenshot()
        if frame is None:
            return None
        self._update_config_size(frame)
        pair = self._multi_bar_pair(frame)
        for _ in range(2):
            if pair.gold.cost_roi_xywh or pair.elixir.cost_roi_xywh:
                break
            # The popup re-renders for a beat after the last add click and the cost buttons
            # can miss the template match — settle and re-read before giving up.
            if self.stop_event.wait(0.4):
                return None
            frame = self.window.screenshot()
            if frame is None:
                return None
            self._update_config_size(frame)
            pair = self._multi_bar_pair(frame)
        if self.config.aspect_key == ASPECT_16_9:
            # For the run summary: what is about to be bought, and the loot before paying.
            (level, count) = read_wall_bar_title(frame)
            self._wall_pending = {'from_level': level, 'count': count,
                                  'hud_before': self._read_hud_triplet_stable()}
        picked = False
        paid_with = None
        # cost_roi_xywh None means the cost text could not be measured — never click a slot
        # on a blind reading (an unaffordable click opens the buy-with-gems dialog).
        # Elixir first: attacking costs GOLD (Find a Match entry fee), so spend elixir on
        # walls whenever it can pay and keep gold for matchmaking.
        if pair.elixir.redness < 0.2 and pair.elixir.cost_roi_xywh and pair.elixir.center:
            logger.info('Wall upgrade: paying with elixir (redness %.2f)', pair.elixir.redness)
            self.input.click(pause = 0.3, *pair.elixir.center)
            picked = True
            paid_with = 'elixir'
        elif pair.gold.redness < 0.2 and pair.gold.cost_roi_xywh and pair.gold.center:
            logger.info('Wall upgrade: paying with gold (redness %.2f)', pair.gold.redness)
            self.input.click(pause = 0.3, *pair.gold.center)
            picked = True
            paid_with = 'gold'
        frame = self.window.screenshot()
        if frame is None:
            return None
        self._update_config_size(frame)
        if not picked:
            logger.info('Wall upgrade: no affordable resource slot (gold %.2f, elixir %.2f) — dismissing without confirming', pair.gold.redness, pair.elixir.redness)
            if not pair.gold.cost_roi_xywh and not pair.elixir.cost_roi_xywh:
                try:
                    import time as _time
                    import cv2 as _cv2
                    from app.utils.common import get_user_app_data_dir
                    dbg = get_user_app_data_dir() / 'debug'
                    dbg.mkdir(parents = True, exist_ok = True)
                    path = dbg / f'''wallfail_{int(_time.time())}.jpg'''
                    _cv2.imwrite(str(path), frame, [_cv2.IMWRITE_JPEG_QUALITY, 88])
                    logger.info('Wall upgrade: confirm-time frame saved to %s', path)
                except Exception:
                    logger.debug('Wall upgrade: debug frame dump failed', exc_info = True)
            self._deselect_wall_ui()
            return None
        if self.config.aspect_key == ASPECT_16_9:
            self._confirm_wall_dialog(paid_with)
            return None
        (ox, oy) = self.vision.find_template(frame, 'okay.png')
        if ox:
            self.input.click(ox, oy, pause = 0.3)
            self._wall_upgrade_confirmed = True
            logger.info('Wall upgrade batch confirmed')

    
    def _record_wall_upgrade(self, resource, dialog_price):
        '''Log one confirmed wall batch for the run summary. Cost = the paying
        resource's HUD drop (stable reads before/after) — the dialog price is OCR
        and has misread (live: 2000000 for a 4M batch); it is only the fallback.'''
        pending = getattr(self, '_wall_pending', None) or {}
        self._wall_pending = None
        cost = None
        before = pending.get('hud_before')
        after = self._read_hud_triplet_stable()
        index = {'gold': 0, 'elixir': 1}.get(resource)
        if before is not None and after is not None and index is not None:
            drop = before[index] - after[index]
            if drop > 0:
                cost = drop
        if cost is None and dialog_price:
            cost = dialog_price
        per_wall = getattr(self, '_wall_pick_cost', None)
        count = self._wall_record_count(cost, per_wall, pending.get('count'))
        entry = {'count': count, 'from_level': pending.get('from_level'), 'cost': cost, 'resource': resource,
                 'per_wall': per_wall}
        self._walls_upgraded = getattr(self, '_walls_upgraded', []) + [entry]
        logger.info('Wall upgrade recorded: %s wall(s), level %s → %s, cost %s %s', count, entry['from_level'] or '?',
                    entry['from_level'] + 1 if entry['from_level'] else '?', cost, resource)

    def _wall_record_count(self, cost, per_wall, ocr_count):
        '''Walls in the confirmed batch. Most trusted first: the HUD drop divided by
        the per-wall price (exact multiple only), then the walls the bot added itself,
        then the bar title OCR (live misread: "x 4" → 48), else 1.'''
        batch = getattr(self, '_wall_batch_count', None)
        self._wall_batch_count = None
        if cost and per_wall and cost % per_wall == 0 and 1 <= cost // per_wall <= _WALL_BATCH_MAX_ADDS + 1:
            count = cost // per_wall
            if batch and batch != count:
                logger.info('Wall upgrade: %s wall(s) added but the loot drop pays for %s — using %s', batch, count, count)
            return count
        if batch:
            return batch
        if ocr_count and 1 <= ocr_count <= _WALL_BATCH_MAX_ADDS + 1:
            return ocr_count
        return max(1, round(cost / per_wall)) if cost and per_wall else 1

    def _walls_popup_payable(self, walls_dialog):
        '''True when the HUD's amount of the popup's resource covers its price (Home
        Village gold keeps the matchmaking fee back; the Builder Base has no fee).'''
        index = {'gold': 0, 'elixir': 1}.get(walls_dialog.resource)
        if index is None or not walls_dialog.price:
            return False
        # The popup dims the HUD (digits unreadable — live BB 30/10): use the read taken
        # just before the resource click, the live one only as a fallback.
        triplet = (getattr(self, '_wall_pending', None) or {}).get('hud_before') or self._read_hud_triplet_stable()
        if triplet is None:
            return False
        reserve = _WALL_GOLD_ATTACK_BUFFER if index == 0 and not getattr(self, '_builder_base', False) else 0
        return triplet[index] - reserve >= walls_dialog.price

    def _confirm_wall_dialog(self, paid_with = None):
        '''UI ottobre 2026: the resource button opens one of two dialogs —
        a single wall gets "Upgrade Wall to Level N?" with a green Confirm, a batch
        gets the "Upgrade Walls" popup ("…the selected Walls for 8000000 Gold?",
        Cancel / Okay). A red Confirm price, or a popup paid in the other resource,
        is never clicked — close it and go back to attacking.'''
        panel = BuildPanel(self)
        button = None
        walls_dialog = None
        for _ in range(8):
            self._check_stop()
            frame = panel.frame()
            if frame is not None:
                button = read_confirm_button(frame)
                if button is None:
                    walls_dialog = panel.read_walls_okay_dialog(frame)
                if button is not None or walls_dialog is not None:
                    break
            if self.stop_event.wait(0.4):
                return
        if walls_dialog is not None:
            if paid_with and walls_dialog.resource and walls_dialog.resource != paid_with:
                # Live BB 30/10: low wall levels are gold-only, the click landed on the gold
                # button while the bar read it as elixir. The popup names the resource and
                # the price — confirm only when the HUD shows THAT resource pays it.
                if not self._walls_popup_payable(walls_dialog):
                    logger.warning('Wall upgrade: popup asks for %s %s, the bot paid with %s and the HUD cannot cover it — cancelling', walls_dialog.price, walls_dialog.resource, paid_with)
                    panel.close_all()
                    return
                logger.info('Wall upgrade: popup asks for %s instead of %s — the HUD covers %s, confirming', walls_dialog.resource, paid_with, walls_dialog.price)
                paid_with = walls_dialog.resource
            logger.info('Wall upgrade: confirming the batch (%s %s) with Okay', walls_dialog.price, walls_dialog.resource)
            outcome = panel.click_walls_okay_and_check(walls_dialog)
            if outcome == 'ok':
                self._wall_upgrade_confirmed = True
                logger.info('Wall upgrade batch confirmed')
                self._record_wall_upgrade(paid_with or walls_dialog.resource, walls_dialog.price)
            else:
                logger.warning('Wall upgrade: Okay outcome %r — closing', outcome)
                panel.close_all()
            return
        if button is None:
            logger.info('Wall upgrade: no Confirm / Upgrade Walls dialog after the resource click — closing')
            if frame is not None:
                from app.core.upgrader import _dump_debug_frame
                _dump_debug_frame(frame, 'wallconfirm')
            panel.close_all()
            return
        if button.red:
            logger.info('Wall upgrade: Confirm price %s (red=%s) — not confirming', button.price, button.red)
            panel.close_all()
            return
        logger.info('Wall upgrade: confirming %s %s (%s layout)', button.price, button.resource, button.layout)
        outcome = panel.click_confirm_and_check(button)
        if outcome == 'ok':
            self._wall_upgrade_confirmed = True
            logger.info('Wall upgrade batch confirmed')
            self._record_wall_upgrade(paid_with or button.resource, button.price)
        else:
            logger.warning('Wall upgrade: confirm outcome %r — closing', outcome)
            panel.close_all()

    def _upgrade_walls(self):
        '''Open builder menu, scroll to Wall, add walls → remove if both red → Okay.'''
        frame = self.window.screenshot()
        if frame is None:
            return None
        self._update_config_size(frame)
        top_roi = VisionService.top_half_region(frame)
        home_roi = VisionService.bottom_half_region(frame)
        (hax, hay) = self.vision.find_template(frame, 'attack.png', region = home_roi)
        if not hax:
            logger.info('Wall upgrade: not on the home screen (Attack button missing) — skipping this pass')
            return None
        if self.config.aspect_key == ASPECT_16_9:
            # UI ottobre 2026: Wall row lives in the Build panel.
            wall_pt = self._find_wall_row_build_panel()
            if not wall_pt:
                return None
            self._upgrade_walls_from_row(wall_pt)
            return None
        (bx, by) = self._find_home_village_builder(frame, top_roi)
        if not bx:
            logger.info('Wall upgrade: builder portrait not found — skipping this pass')
            return None
        self.input.click(bx, by, pause = 0.5)
        # TH15+ overflows the builder popup ('Suggested upgrades' grows and 'Other upgrades'
        # continues past the fold), so the Wall row can start below the visible area. The
        # popup scrolls with the mouse wheel without closing; touch-drags scroll too but
        # overshoot past Wall (it now sits mid-list, not at the end). Poll the OCR at each
        # position and wheel down a notch between misses.
        if self.stop_event.wait(0.3):
            return None
        wall_pt = None
        candidate = None
        scrolls = 0
        for _ in range(_WALL_MENU_SCROLL_STEPS * 2):
            self._check_stop()
            found = self._find_wall_row_once()
            if found:
                if candidate and abs(found[1] - candidate[1]) <= self.config.scale_scalar(_WALL_ROW_STABLE_TOL):
                    wall_pt = found
                    if scrolls:
                        logger.info('Wall upgrade: Wall row found after %d scroll nudge(s)', scrolls)
                    break
                # One agreeing frame is required before clicking — the list keeps easing
                # after a wheel nudge, and a click on stale coordinates lands on whatever
                # row slid underneath (live repro: opened the Blacksmith's Forge).
                candidate = found
                if self.stop_event.wait(0.25):
                    return None
                continue
            candidate = None
            scrolls += 1
            if scrolls >= _WALL_MENU_SCROLL_STEPS:
                break
            self.input.scroll(*self._wall_menu_scroll_point(), _WALL_MENU_WHEEL_CLICKS)
            if self.stop_event.wait(0.5):
                return None
        if not wall_pt:
            logger.info('Wall upgrade: Wall label OCR missed at all scroll positions — skipping this pass')
            return None
        self._upgrade_walls_from_row(wall_pt)

    def _find_wall_row_build_panel(self):
        '''UI ottobre 2026: open the Build panel and wheel down the list, saving the
        price of every Wall row (one row per wall level) on the way. Returns the click
        point of the first wall level the current gold OR elixir can pay (two
        consecutive frames agreeing on its y — the list eases after each wheel
        nudge), or None with the panel closed again. Levels the loot cannot pay are
        skipped, so a cheaper level further down still gets bought.'''
        triplet = self._read_hud_triplet_stable()  # home screen, before the panel covers it
        panel = BuildPanel(self)
        if not panel.open(reset_to_top = True):
            logger.info('Wall upgrade: Build panel did not open — skipping this pass')
            panel.close_all()
            return None
        if getattr(self, '_upgrade_order', None) == 'cheapest':
            return self._find_cheapest_wall_row(panel, triplet)
        candidate = None  # (center, cost) of the last frame's pick
        scrolls = 0
        seen = set()
        for _ in range(_WALL_PANEL_SCROLL_STEPS * 2):
            self._check_stop()
            frame = panel.frame()
            if frame is None:
                break
            walls = [r for r in parse_builder_menu(frame) if is_wall_row(r)]
            seen |= self._remember_wall_costs(walls)
            usable = self._usable_walls(walls, triplet)
            if usable:
                pick = usable[0]
                if (candidate and candidate[1] == pick.cost
                        and abs(pick.center[1] - candidate[0][1]) <= self.config.scale_scalar(_WALL_ROW_STABLE_TOL)):
                    logger.info('Wall upgrade: wall level at %s per wall picked after %d scroll nudge(s) (levels seen: %s)', pick.cost, scrolls, sorted(seen))
                    self._wall_pick_cost = pick.cost
                    return pick.center
                candidate = (pick.center, pick.cost)
                if self.stop_event.wait(0.25):
                    return None
                continue
            candidate = None
            scrolls += 1
            if scrolls >= _WALL_PANEL_SCROLL_STEPS:
                break
            panel.scroll(_WALL_MENU_WHEEL_CLICKS)
            panel.wait_list_settled()  # until the list stops easing, not a fixed 0.6 s
            if self.stop_event.is_set():
                return None
        if seen and scrolls >= _WALL_PANEL_SCROLL_STEPS:
            # Whole list walked from the top: these are exactly the levels left — drop
            # any saved level finished since (it would keep the pre-check opening the
            # panel for a price that no longer exists).
            self._wall_costs = set(seen)
        if seen:
            logger.info('Wall upgrade: no payable wall level (seen %s, HUD %s) — skipping this pass', sorted(seen), triplet)
        else:
            logger.info('Wall upgrade: Wall row not found in the Build panel — skipping this pass')
        panel.close_all()
        return None

    def _usable_walls(self, walls, triplet):
        if triplet is not None:
            return [r for r in walls if r.cost and self._wall_payable(r.cost, triplet)]
        # HUD unread: fall back to the panel's own colour (white = gold pays).
        return [r for r in walls if r.cost and r.affordable]

    def _find_cheapest_wall_row(self, panel, triplet):
        '''"Cheapest first" (Settings → Upgrade order) for walls. The list runs from
        the priciest row down, so the cheapest payable wall level is only known after
        the whole list: walk to the end noting every payable level, then wheel back
        up to the cheapest one and return its click point (two agreeing frames).'''
        seen = set()
        payable = set()
        previous_sig = None
        reached_end = False
        for _ in range(_WALL_PANEL_SCROLL_STEPS):
            self._check_stop()
            frame = panel.frame()
            if frame is None:
                break
            rows = parse_builder_menu(frame)
            walls = [r for r in rows if is_wall_row(r)]
            seen |= self._remember_wall_costs(walls)
            payable |= {r.cost for r in self._usable_walls(walls, triplet)}
            sig = tuple((r.cost, r.line_y // 20) for r in rows)
            if sig and sig == previous_sig:
                reached_end = True  # the wheel no longer moves the list
                break
            previous_sig = sig
            panel.scroll(_WALL_MENU_WHEEL_CLICKS)
            panel.wait_list_settled()  # until the list stops easing, not a fixed 0.6 s
            if self.stop_event.is_set():
                return None
        if seen and reached_end:
            self._wall_costs = set(seen)  # whole list seen: exactly the levels left
        if not payable:
            logger.info('Wall upgrade: no payable wall level (seen %s, HUD %s) — skipping this pass', sorted(seen), triplet)
            panel.close_all()
            return None
        target = min(payable)
        candidate = None
        for _ in range(_WALL_PANEL_SCROLL_STEPS * 2):
            self._check_stop()
            frame = panel.frame()
            if frame is None:
                break
            matches = [r for r in parse_builder_menu(frame) if is_wall_row(r) and r.cost == target]
            if matches:
                pick = matches[0]
                if candidate and abs(pick.center[1] - candidate[1]) <= self.config.scale_scalar(_WALL_ROW_STABLE_TOL):
                    logger.info('Wall upgrade: cheapest payable wall level at %s per wall picked (payable %s, seen %s)', target, sorted(payable), sorted(seen))
                    self._wall_pick_cost = target
                    return pick.center
                candidate = pick.center
                if self.stop_event.wait(0.25):
                    return None
                continue
            candidate = None
            panel.scroll(_WALL_MENU_WHEEL_CLICKS, upward = True)
            panel.wait_list_settled()
            if self.stop_event.is_set():
                return None
        logger.info('Wall upgrade: cheapest wall level %s not found again on the way back up — skipping this pass', target)
        panel.close_all()
        return None

    def _upgrade_walls_from_row(self, wall_pt):
        '''Click the Wall row → Upgrade More → add walls while affordable → pay.'''
        self.input.click(pause = 0.6, *wall_pt)
        # Clicking the Wall row pans the camera to a wall before the selection bar
        # renders (often >1s) — poll for Upgrade More instead of trusting one early
        # frame (live rate before polling: ~1 success in 8 passes).
        (umx, umy) = (None, None)
        bar_scale = 1.0
        frame = None
        for _ in range(8):
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                return None
            self._update_config_size(frame)
            (umx, umy, bar_scale) = self._find_upgrade_more(frame)
            if umx:
                break
            if self.stop_event.wait(0.5):
                return None
        if not umx:
            # The Wall click missed (wrong row / a building dialog opened instead) —
            # close whatever came up so it cannot block the next pass or the Attack tap.
            logger.info('Wall upgrade: upgrademore.png not visible after Wall row click — dismissing and skipping this pass')
            if frame is not None:
                try:
                    import time as _time
                    import cv2 as _cv2
                    from app.utils.common import get_user_app_data_dir
                    dbg = get_user_app_data_dir() / 'debug'
                    dbg.mkdir(parents = True, exist_ok = True)
                    path = dbg / f'''wallrow_{int(_time.time())}.jpg'''
                    _cv2.imwrite(str(path), frame, [_cv2.IMWRITE_JPEG_QUALITY, 88])
                    logger.info('Wall upgrade: post-click frame saved to %s', path)
                except Exception:
                    logger.debug('Wall upgrade: wallrow debug dump failed', exc_info = True)
                self._dismiss_okay_or_exit_on_frame(frame)
            if self.config.aspect_key == ASPECT_16_9:
                BuildPanel(self).close_all()
            return None
        if bar_scale != 1.0:
            logger.info('Wall upgrade: selection bar at %.2fx (Build panel open)', bar_scale)
        previous = VisionService.set_ui_scale(bar_scale)
        try:
            self._upgrade_walls_batch(umx, umy)
        finally:
            VisionService.set_ui_scale(previous)
        if self.config.aspect_key == ASPECT_16_9:
            # The Build panel stays open behind the wall bar — close it before attacking.
            BuildPanel(self).close_all()

    def _find_upgrade_more(self, frame):
        '''``upgrademore.png`` at the bar's scale → (x, y, scale) or (None, None, 1.0).
        UI ottobre 2026: clicking the Wall row in the Build panel keeps the panel open
        and the selection bar renders smaller (measured 0.90x: 0.86 match vs 0.53 at 1x).'''
        bot_roi = VisionService.bottom_half_region(frame)
        scales = _WALL_BAR_SCALES if self.config.aspect_key == ASPECT_16_9 else (1.0,)
        best = (None, None, 1.0, 0.0)
        for scale in scales:
            previous = VisionService.set_ui_scale(scale)
            try:
                (x, y, conf) = VisionService.find_template_with_confidence(frame, 'upgrademore.png', 0.8, bot_roi)
            finally:
                VisionService.set_ui_scale(previous)
            if x and conf > best[3]:
                best = (x, y, scale, conf)
        return best[:3]

    def _wall_bar_roi(self, frame, pair = None, scale = 1.0):
        '''Where Add/Remove Wall live. 16:9 (UI ottobre 2026): only the strip LEFT of
        the payment buttons, on their row — Add Wall (+1) is one button to their left,
        Remove Wall two or three. Measured off the buttons actually found, so it
        follows the bar wherever it is drawn and at whatever size. A wide fixed box
        let a +1 match land outside the bar (live repro: a click on the map selected
        another wall; another opened the Layout Editor).'''
        (fh, fw) = frame.shape[:2]
        if self.config.aspect_key == ASPECT_16_9:
            anchor = None
            if pair is not None and pair.gold.center:
                anchor = pair.gold.center
            elif pair is not None and pair.elixir.center:
                (ex, ey) = pair.elixir.center
                anchor = (ex - round(_WALL_BAR_PITCH_FRAC * fw * scale), ey)
            if anchor is None:
                return None
            pitch = _WALL_BAR_PITCH_FRAC * fw * scale
            (ax, ay) = anchor
            x0 = max(0, round(ax - 3.6 * pitch))
            x1 = max(x0 + 1, round(ax - 0.5 * pitch))
            y0 = max(0, round(ay - 0.07 * fh * scale))
            y1 = min(fh, round(ay + 0.05 * fh * scale))
            return (x0, y0, x1 - x0, y1 - y0)
        return (fw // 4, fh // 2, fw // 2, fh - fh // 2)

    def _read_multi_bar(self, frame):
        '''Multi-upgrade bar on THIS frame → (scale, pair). The bar's size can change
        between steps (live: Build panel open at 0.90x, then closed and back to 1x
        after Upgrade More), so every step re-measures it on the payment buttons
        instead of trusting the first reading. pair is None when no payment button
        is visible at any scale.'''
        scales = _WALL_BAR_SCALES if self.config.aspect_key == ASPECT_16_9 else (VisionService._ui_scale,)
        best = (1.0, None, 0.0)
        for scale in scales:
            previous = VisionService.set_ui_scale(scale)
            try:
                pair = VisionService.upgrade_cost_redness_by_resource_icons(frame)
            finally:
                VisionService.set_ui_scale(previous)
            if not pair.gold.cost_roi_xywh and not pair.elixir.cost_roi_xywh:
                continue
            conf = max(pair.gold.match_confidence if pair.gold.found else 0,
                       pair.elixir.match_confidence if pair.elixir.found else 0)
            if conf > best[2]:
                best = (scale, pair, conf)
        return best[:2]

    def _multi_bar_pair(self, frame):
        '''Payment buttons at the bar's measured scale; a "not found" pair otherwise.'''
        (_scale, pair) = self._read_multi_bar(frame)
        return pair if pair is not None else VisionService.upgrade_cost_redness_by_resource_icons(frame)

    def _find_in_bar(self, finder, frame, pair, scale):
        '''Run find_active_addwall/removewall at the bar's measured scale, inside the bar.'''
        roi = self._wall_bar_roi(frame, pair, scale)
        if roi is None:
            return (None, None)
        previous = VisionService.set_ui_scale(scale)
        try:
            return finder(frame, region = roi)
        finally:
            VisionService.set_ui_scale(previous)

    def _note_wall_pay_options(self, pair):
        '''Gold button but no elixir button on the multi bar: this wall level is gold-only.'''
        cost = getattr(self, '_wall_pick_cost', None)
        if not cost or not pair.gold.found or pair.elixir.found:
            return
        gold_only = getattr(self, '_wall_gold_only_costs', None)
        if gold_only is None:
            gold_only = self._wall_gold_only_costs = set()
        if cost not in gold_only:
            gold_only.add(cost)
            logger.info('Wall upgrade: wall level at %s per wall takes gold only (no elixir button)', cost)

    def _upgrade_walls_batch(self, umx, umy):
        '''Upgrade More is on screen at (umx, umy): build the batch and pay for it.'''
        self.input.click(umx, umy, pause = 0.4)
        # Add walls to the batch while at least one resource can still pay the total.
        added = 0
        removed = 0
        self._wall_batch_count = None
        for _ in range(_WALL_BATCH_MAX_ADDS):
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                return None
            self._update_config_size(frame)
            (scale, pair) = self._read_multi_bar(frame)
            if pair is None:
                # The cost buttons are the only reliable proof the multi-upgrade popup is
                # actually open — addwall/removewall false-positive on home-screen greens
                # (incl. the Attack button checkmark), so never click blind.
                logger.info('Wall upgrade: cost buttons not visible — popup not open, stopping batch')
                break
            self._note_wall_pay_options(pair)
            if self._pay_slot_blocked(pair.gold) and self._pay_slot_blocked(pair.elixir):
                break
            (awx, awy) = self._find_in_bar(VisionService.find_active_addwall, frame, pair, scale)
            if not awx:
                break
            self.input.click(awx, awy, pause = 0.3)
            added += 1
        if added == 0:
            self._deselect_wall_ui()
            return None
        self._check_stop()
        frame = self.window.screenshot()
        if frame is None:
            return None
        self._update_config_size(frame)
        (scale, pair) = self._read_multi_bar(frame)
        if pair is None:
            logger.info('Wall upgrade: cost buttons gone after adding walls — not paying')
            self._deselect_wall_ui()
            return None
        if added and self._pay_slot_blocked(pair.gold) and self._pay_slot_blocked(pair.elixir):
            # Last add pushed the total over both resources — take one back before confirming.
            (rwx, rwy) = self._find_in_bar(VisionService.find_active_removewall, frame, pair, scale)
            if rwx:
                self.input.click(rwx, rwy, pause = 0.4)
                removed += 1
        elif (added > 1 and not getattr(self, '_builder_base', False) and self._pay_slot_blocked(pair.elixir)
              and not self._pay_slot_blocked(pair.gold)):
            # Gold will pay (elixir can't) — drop one wall so a maxed batch never drains gold
            # to 0. Find a Match costs ~1300 gold; a zeroed gold storage blocks all attacking.
            (rwx, rwy) = self._find_in_bar(VisionService.find_active_removewall, frame, pair, scale)
            if rwx:
                logger.info('Wall upgrade: gold is the payer — removing one wall to keep the attack entry fee')
                self.input.click(rwx, rwy, pause = 0.4)
                removed += 1
        logger.info('Wall upgrade: %d wall(s) added to batch', added)
        # What the bot itself put in the batch: the run summary's wall count (the bar
        # title OCR misreads it — live: "x 4" read as 48).
        self._wall_batch_count = max(1, 1 + added - removed)  # + the wall the row click selected
        self._upgrade_walls_pick_resource_and_okay()

    
    def _dismiss_okay_or_exit_on_frame(self, frame):
        '''If ``okay.png``, ``exit.png``, or a known dialog-specific control is visible,
        click it. Returns True if dismissed. The Daily Reward popup (blocked the bot a
        whole night) must be CLAIMED before its X works ("Claim reward first!"), so the
        green Claim button outranks its grey X; both have their own art (exit.png does
        not match).'''
        names = ['okay.png', 'exit.png']
        for extra in ('claim_btn.png', 'dailyreward_x.png', 'needgold_x.png'):
            if get_template_path(extra).exists():
                names.append(extra)
        for name in names:
            (x, y) = self.vision.find_template(frame, name)
            if not x:
                continue
            self.input.click(x, y, pause = 0.15)
            return True
        return False

    
    def _wait_for_attack_with_nudge(self, timeout = 10, error = True):
        '''Poll bottom-half ``attack.png``; dismiss ``okay`` / ``exit`` popups first; else empty + scroll.'''
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(0.5):
                    return (None, None)
                continue
            self._update_config_size(frame)
            if self._dismiss_okay_or_exit_on_frame(frame):
                if self.stop_event.wait(0.25):
                    return (None, None)
                continue
            (sx, sy) = self.vision.find_template(frame, 'surrender.png')
            if sx:
                # We are inside a live battle — nudge clicks would deploy troops. Bail out and
                # let _home_screen_recovery surrender/return-home.
                logger.warning('Attack wait: live battle detected (surrender visible) — leaving it to recovery')
                return (None, None)
            search_region = self._search_region_for_template(frame, 'attack.png', None, None, 200)
            (ax, ay) = self.vision.find_template(frame, 'attack.png', region = search_region)
            if ax:
                return (ax, ay)
            self._nudge_view_to_reveal_attack()
            if self.stop_event.wait(0.35):
                return (None, None)
        if error:
            logger.warning('Timeout waiting for attack.png')  # [recovered: decompiler misnested this inside the loop — it spammed once per poll]
        return (None, None)

    
    def _run_loop(self, method_id, duration_seconds, star_bonus = False, ranked_fill = False, upgrade_walls = False):
        start_time = time.time()
        if self.stop_event.wait(1):
            return None
        frame = self.window.screenshot()
        self._update_config_size(frame)
        empty_pt = self.config.get_point('empty')
        self.input.click(pause = 0.2, *empty_pt)
        self.input.scroll(*self._scroll_point(), 20)
        delay = random.uniform(0.1, 0.3)
        if self.stop_event.wait(delay):
            return None
        if star_bonus and self._is_star_bonus_claimed():
            logger.info('Star bonus mode: no star bonus template matched on home — nothing to collect. Finishing without attacks.')
            return None
        # duration_seconds == 0 → unlimited ("run until maxed"): only the user's Stop
        # ends the session; full storages park the loop in _maybe_idle instead.
        deadline = start_time + duration_seconds if duration_seconds else None
        self._maybe_upgrade_walls(upgrade_walls)
        self._maybe_auto_upgrade()
        self._maybe_idle(deadline)
        # UI ottobre 2026: clicking a Build-panel row zooms the camera onto that
        # building, and the zoom carries into the next battle (live repro: first
        # attack of the session scouted 4 corners zoomed-in and dropped only the
        # heroes). Zoom fully back out after the home-screen menus, before attacking.
        self.input.scroll(*self._scroll_point(), 20)
        cb = getattr(self, '_status_callback', None)
        troop_failures = 0
        while deadline is None or time.time() < deadline:
            self._check_stop()
            outcome = self._find_match_and_attack(method_id, ranked_fill)
            self._return_home()
            self._home_screen_recovery()
            if outcome == 'ranked_limit':
                return None
            if outcome == 'troop':
                troop_failures += 1
                if troop_failures >= _TROOP_FAILURE_LIMIT:
                    if deadline is None:
                        # Run-until-maxed must never stop on its own: long back-off
                        # instead (a stuck popup / event screen usually clears, and
                        # recovery runs again on the next attempt).
                        msg = f'''Troops not found {troop_failures} times in a row — backing off {_IDLE_RECHECK_SECONDS // 60}m, then retrying (run until maxed).'''
                        logger.warning(msg)
                        if cb:
                            cb(msg)
                        troop_failures = 0
                        if self.stop_event.wait(_IDLE_RECHECK_SECONDS):
                            return None
                        self._home_screen_recovery()
                        continue
                    msg = f'''Troops not found {troop_failures} times in a row — stopping. Check the army / saved recipe.'''
                    logger.warning(msg)
                    if cb:
                        cb(msg)
                    return None
                msg = f'''Troops not found ({troop_failures}/{_TROOP_FAILURE_LIMIT}) — retrying in {_TROOP_RETRY_WAIT_SECONDS}s.'''
                logger.warning(msg)
                if cb:
                    cb(msg)
                # Tap any collect bubbles while we are home — if the failure was really the
                # need-more-gold dialog (entry fee unaffordable), mine gold un-wedges it.
                self._multi_run_collect_home_village_resources()
                if self.stop_event.wait(_TROOP_RETRY_WAIT_SECONDS):
                    return None
            else:
                troop_failures = 0
            self._maybe_upgrade_walls(upgrade_walls)
            self._maybe_auto_upgrade()
            self._maybe_idle(deadline)
            self.input.scroll(*self._scroll_point(), 20)  # full zoom-out: a panel row click zooms in
            if self.stop_event.wait(random.uniform(0.15, 0.25)):
                return None
            if star_bonus and self._is_star_bonus_claimed():
                logger.info('Star bonus claimed (star icons no longer visible). Stopping.')
                return None
        return None

    
    def _run_builder_base_loop(self, duration_seconds, star_bonus = False, upgrade_walls = False):
        '''Builder Base farming: Attack → Find Now → Baby Dragon deploy → end battle or surrender → Return Home.'''
        start_time = time.time()
        # Wall prices are per village: never carry Home Village levels into the BB.
        self._wall_costs = set()
        self._wall_cost_resource = {}
        self._wall_gold_only_costs = set()
        self._bb_wall_probed = False
        cb = getattr(self, '_status_callback', None)
        if self.stop_event.wait(1):
            return None
        frame = self.window.screenshot()
        if not frame is None:
            self._update_config_size(frame)
        empty_pt = self.config.get_point('empty')
        self.input.click(pause = 0.2, *empty_pt)
        self.input.scroll(*self._scroll_point(), 20)
        if self.stop_event.wait(random.uniform(0.1, 0.3)):
            return None
        if star_bonus and self._is_bb_star_bonus_finished():
            msg = 'Builder Base star bonus: bstar.png not visible — nothing to collect. Finishing without attacks.'
            logger.info(msg)
            if cb:
                cb(msg)
            return None
        # duration_seconds == 0 → unlimited ("run until maxed"): only Stop ends the run.
        no_dragon_failures = 0
        while duration_seconds <= 0 or time.time() - start_time < duration_seconds:
            self._check_stop()
            self._bb_dismiss_star_bonus()
            self._maybe_upgrade_bb_walls(upgrade_walls)
            self.input.scroll(*self._scroll_point(), 20)
            if self.stop_event.wait(random.uniform(0.1, 0.25)):
                return None
            (ax, ay) = self._wait_for_image('attack.png', timeout = 10)
            if not ax:
                logger.warning('Builder Base: attack.png not found')
                self._bb_recover_from_battle()
                continue
            self.input.click(ax, ay, pause = 0.15)
            (fx, fy) = self._wait_for_image('findnow.png', timeout = 10)
            if not fx:
                logger.warning('Builder Base: findnow.png not found')
                continue
            self.input.click(fx, fy, pause = 0.15)
            (bx, by) = self._wait_for_image('babydragon.png', timeout = 30, error = False)
            if not bx:
                msg = 'Builder Base: babydragon.png not found after Find Now'
                logger.warning(msg)
                if cb:
                    cb(msg)
                no_dragon_failures += 1
                if self._bb_handle_no_dragon(no_dragon_failures, duration_seconds):
                    return None
                if no_dragon_failures >= _TROOP_FAILURE_LIMIT:
                    no_dragon_failures = 0  # run until maxed backed off: count again
                continue
            frame = self.window.screenshot()
            if frame is None:
                # No capture (window lost / minimised): pause instead of spinning.
                if self.stop_event.wait(0.5):
                    return None
                continue
            self._update_config_size(frame)
            if not self._deploy_bb_baby_dragons(frame):
                logger.warning('Builder Base: no Baby Dragon card on the bar / deploy failed')
                no_dragon_failures += 1
                if self._bb_handle_no_dragon(no_dragon_failures, duration_seconds):
                    return None
                if no_dragon_failures >= _TROOP_FAILURE_LIMIT:
                    no_dragon_failures = 0  # run until maxed backed off: count again
                continue
            no_dragon_failures = 0
            self._bb_attacks_done = getattr(self, '_bb_attacks_done', 0) + 1
            if self._loot_prioritise == 'elixir':
                self._bb_surrender_and_return_home()
            elif self._loot_prioritise == 'gold':
                self._bb_gold_prioritise_end_battle_and_return_home()
            elif self._loot_prioritise == 'trophy':
                self._bb_trophy_play_both_stages_and_return_home()
            else:
                self._bb_end_battle_and_return_home()
            self._bb_collect_elixir_cart_after_attack()
            if star_bonus and self._is_bb_star_bonus_finished():
                logger.info('Builder Base star bonus finished (bstar.png no longer visible). Stopping.')
                return None
            if self.stop_event.wait(random.uniform(0.35, 0.6)):
                return None
        return None

    
    def _bb_handle_no_dragon(self, failures, duration_seconds):
        '''A battle opened without a usable Baby Dragon: leave it now (End Battle /
        Surrender) instead of letting the next loop wait for a Battle button that is not
        there (live: 3.5 minutes stuck). True = stop the run. After _TROOP_FAILURE_LIMIT
        in a row the army has no dragons: a timed run stops, run-until-maxed backs off
        like the Home Village does.'''
        self._bb_recover_from_battle()
        if failures < _TROOP_FAILURE_LIMIT:
            return False
        cb = getattr(self, '_status_callback', None)
        if duration_seconds > 0:
            msg = f'''Builder Base: no Baby Dragon {failures} times in a row — stopping. Check the Builder Base army.'''
            logger.warning(msg)
            if cb:
                cb(msg)
            return True
        msg = f'''Builder Base: no Baby Dragon {failures} times in a row — backing off {_IDLE_RECHECK_SECONDS // 60}m, then retrying (run until maxed).'''
        logger.warning(msg)
        if cb:
            cb(msg)
        return self.stop_event.wait(_IDLE_RECHECK_SECONDS)

    def _bb_pan_down_left_from_center(self):
        '''Pan BB view down-left from screen center (~500px) to reveal the boat / elixir cart.'''
        self._check_stop()
        frame = self.window.screenshot()
        if frame is None or frame.size == 0:
            return None
        self._update_config_size(frame)
        (h, w) = frame.shape[:2]
        cx = w // 2 + random.randint(-25, 25)
        cy = h // 2 + random.randint(-25, 25)
        cx = max(8, min(w - 8, cx))
        cy = max(8, min(h - 8, cy))
        self.input.move(cx, cy, 0)
        self.input.mouse_up(cx, cy)
        if self.stop_event.wait(0.06):
            self._check_stop()
        step = 500
        x2 = max(8, min(w - 8, cx - step))
        y2 = max(8, min(h - 8, cy + step))
        self.input.mouse_down(cx, cy)
        self.input.human_move(cx, cy, x2, y2, duration = random.uniform(0.35, 0.55))
        self.input.mouse_up(x2, y2)
        if self.stop_event.wait(0.45):
            self._check_stop()
            return None

    
    def _find_bb_full_elixir_cart(self, attempts = 3):
        '''Up to ``attempts`` screenshots; try fullecart templates in order (top-right quadrant).'''
        empty_pt = self.config.get_point('empty')
        for _ in range(attempts):
            self._check_stop()
            frame = self.window.screenshot()
            if not frame is None:  # [recovered: decompiler turned this `if` into a `while` and made the return unconditional]
                self._update_config_size(frame)
                roi = VisionService.top_right_quadrant_region(frame)
                for template in _BB_FULL_ELIXIR_CART_TEMPLATES:
                    (x, y) = self.vision.find_template(frame, template, threshold = 0.8, region = roi)
                    if x:
                        return (x, y)
            self.input.click(pause = 0.15, *empty_pt)
        return (None, None)

    
    def _bb_dismiss_star_bonus(self, attempts = 3):
        '''Close the "Star Bonus!" popup (shown after the daily star bonus is earned) via its
Okay button. Returns True when the popup was found and closed.'''
        for _ in range(attempts):
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                return False
            self._update_config_size(frame)
            (tx, ty) = self.vision.find_template(frame, _BB_STAR_BONUS_POPUP_TEMPLATE)
            if not tx:
                return False
            logger.info('Builder Base: Star Bonus popup — clicking Okay')
            self.input.click(tx, ty + round(frame.shape[0] * _BB_STAR_BONUS_OKAY_DY), pause = 0.4)
            if self.stop_event.wait(0.6):
                return False
            frame = self.window.screenshot()
            if frame is not None and not self.vision.find_template(frame, _BB_STAR_BONUS_POPUP_TEMPLATE)[0]:
                return True
        logger.warning('Builder Base: Star Bonus popup still open after %d clicks', attempts)
        return False

    def _bb_collect_elixir_cart_after_attack(self):
        '''After a BB raid: dismiss popups, pan to cart, collect full elixir cart if visible.'''
        if self.stop_event.wait(0.35):
            return None
        self._bb_dismiss_star_bonus()
        self.input.click(pause = 0.15, *self.config.get_point('empty'))
        if self.stop_event.wait(0.15):
            return None
        self._bb_pan_down_left_from_center()
        (cx, cy) = self._find_bb_full_elixir_cart(attempts = 3)
        if cx:
            self.input.click(cx, cy, pause = 0.2)
            (coll_x, coll_y) = self._wait_for_image(_BB_COLLECT_TEMPLATE, timeout = 8, error = False)
            if coll_x:
                self.input.click(coll_x, coll_y, pause = 0.2)
            else:
                logger.warning('Builder Base: collect.png not found after elixir cart')
        else:
            logger.debug('Builder Base: fullecart not visible — skipping cart collect')
        self.input.click(pause = 0.15, *self.config.get_point('empty'))

    
    def _bb_zoom_out(self, frame):
        '''Full zoom-out at the screen centre (fast wheel: the red border shows only briefly).'''
        (h, w) = frame.shape[:2]
        (cx, cy) = (w // 2, h // 2)
        self.input.move(cx, cy)
        self.input.scroll(cx, cy, _BB_ZOOM_OUT_CLICKS, pause = (0.02, 0.05))
        self.stop_event.wait(0.25)

    def _bb_read_border(self, reads = _BB_BORDER_READS):
        '''(frame, hull) of the clearest red border over a few quick screenshots, or
        (last frame, None) when none showed.'''
        (best_frame, best_hull, best_n, last) = (None, None, -1, None)
        for i in range(reads):
            self._check_stop()
            frame = self.window.screenshot()
            if frame is not None:
                self._update_config_size(frame)
                last = frame
                hull = bb_edge.border_hull(frame)
                if hull is not None:
                    n = len(bb_edge.border_segments(frame))
                    if n > best_n:
                        (best_frame, best_hull, best_n) = (frame, hull, n)
                    if n >= 20:
                        break
            if i + 1 < reads and self.stop_event.wait(_BB_BORDER_READ_GAP):
                break
        if best_hull is None:
            return (last, None)
        return (best_frame, best_hull)

    def _bb_dragon_cards(self, frame):
        '''(dragon card tap points, machine card tap point or None) on the troop bar: every
        ready (coloured) slot is a dragon except the Battle / Flying Machine card. Tap points
        sit on the card's upper half, clear of the troop-switch button.'''
        (h, w) = frame.shape[:2]
        roi = VisionService.bottom_half_region(frame)
        machine = None
        for template in (_BB_BATTLE_MACHINE_TEMPLATE, _BB_FLYING_MACHINE_TEMPLATE):
            (mx, my) = self.vision.find_template(frame, template, region = roi)
            if mx:
                machine = (int(mx), int(my))
                break
        slots = self._bb_ready_card_slots(frame)
        half_step = _BB_CARD_SLOT_STEP * w / 2
        if machine is not None:
            slots = [c for c in slots if abs(c[0] - machine[0]) > half_step]
            # Snap the template hit to its slot so the machine is tapped like the dragons.
            index = round((machine[0] / w - _BB_CARD_SLOT_X0) / _BB_CARD_SLOT_STEP)
            if 0 <= index < _BB_CARD_SLOTS:
                machine = (int((_BB_CARD_SLOT_X0 + index * _BB_CARD_SLOT_STEP) * w), machine[1])
            machine = self._bb_card_tap_point(machine, w, h)
        return ([self._bb_card_tap_point(c, w, h) for c in slots], machine)

    @classmethod
    def _bb_undeployed_slots(cls, frame):
        '''Tap points of the cards whose troop is not on the field yet (switch button shown).'''
        import cv2
        (h, w) = frame.shape[:2]
        (dx0, y0, dx1, y1) = _BB_SWITCH_BOX
        hsv = cv2.cvtColor(frame[int(y0 * h):int(y1 * h)], cv2.COLOR_BGR2HSV)  # the switch-button strip only
        out = []
        for i in range(_BB_CARD_SLOTS):
            x = (_BB_CARD_SLOT_X0 + i * _BB_CARD_SLOT_STEP) * w
            patch = hsv[:, max(0, int(x + dx0 * w)):min(w, int(x + dx1 * w))]
            if patch.size == 0:
                continue
            white = float(((patch[:, :, 1] < 40) & (patch[:, :, 2] >= 210)).mean())
            if white >= _BB_SWITCH_MIN_WHITE:
                out.append(cls._bb_card_tap_point((int(x), 0), w, h))
        return out

    @staticmethod
    def _bb_card_tap_point(card, w, h):
        return (int(card[0] + _BB_CARD_TAP_DX * w), int(_BB_CARD_TAP_Y * h))

    def _bb_drop_troops(self, frame, hull, cards, machine, label):
        '''One dragon per zone outside ``hull`` (more cards than zones: shared round-robin),
        each card selected explicitly then dropped; the machine goes with one of the dragons.
        False when no zone could be placed.'''
        zones = bb_edge.zone_points(frame, hull)
        if not zones:
            return False
        drops = bb_edge.spread_over_zones(zones, len(cards))
        started = time.time()
        self._bb_tap_cards_onto(cards, drops)
        if machine is not None:
            (px, py) = random.choice(drops)
            self.input.click(machine[0], machine[1], pause = _BB_CARD_SELECT_PAUSE, rand = False)
            self.input.click(px, py, pause = _BB_DEPLOY_CLICK_PAUSE, rand = False)
        logger.info('Builder Base (%s): %d dragon(s)%s over %d zone(s) in %.1fs', label, len(cards), ' + machine' if machine else '', len(zones), time.time() - started)
        self._bb_redeploy_missed(frame, hull, cards, label)
        return True

    def _bb_tap_cards_onto(self, cards, drops):
        for ((cx, cy), (px, py)) in zip(cards, drops):
            self._check_stop()
            self.input.click(cx, cy, pause = _BB_CARD_SELECT_PAUSE, rand = False)
            self.input.click(px, py, pause = _BB_DEPLOY_CLICK_PAUSE, rand = False)

    def _bb_redeploy_missed(self, frame, hull, cards, label):
        '''Dragons the game did not take (card still showing its switch button) are dropped
        again on fresh zones 2-3 tiles out, round after round, until all are on the field.
        Survivors carried into stage 2 have no switch button and are not checked.'''
        half_step = _BB_CARD_SLOT_STEP * frame.shape[1] / 2
        for attempt in range(1, _BB_DEPLOY_RETRIES + 1):
            if self.stop_event.wait(_BB_DEPLOY_CHECK_WAIT):
                return None
            shot = self.window.screenshot()
            if shot is None:
                return None
            missed = [c for c in self._bb_undeployed_slots(shot) if any(abs(c[0] - d[0]) <= half_step for d in cards)]
            if not missed:
                if attempt > 1:
                    logger.info('Builder Base (%s): every dragon placed after %d retry round(s)', label, attempt - 1)
                return None
            zones = bb_edge.zone_points(frame, hull, distance = _BB_DEPLOY_RETRY_DISTANCE) or bb_edge.zone_points(frame, hull)
            if not zones:
                break
            logger.info('Builder Base (%s): %d dragon(s) still on the bar — retry %d/%d', label, len(missed), attempt, _BB_DEPLOY_RETRIES)
            self._bb_tap_cards_onto(missed, bb_edge.spread_over_zones(zones, len(missed)))
        if self.stop_event.wait(_BB_DEPLOY_CHECK_WAIT):
            return None
        shot = self.window.screenshot()
        left = 0 if shot is None else len([c for c in self._bb_undeployed_slots(shot) if any(abs(c[0] - d[0]) <= half_step for d in cards)])
        if left:
            logger.warning('Builder Base (%s): %d dragon(s) still not placed after %d retries', label, left, _BB_DEPLOY_RETRIES)

    def _bb_activate_abilities(self, cards, machine):
        '''After a random 10-25 s cooldown, click every deployed card (and the machine) together.'''
        targets = list(cards) + ([machine] if machine is not None else [])
        if not targets:
            return None
        delay = random.uniform(*_BB_ABILITY_DELAY)
        if self.stop_event.wait(delay):
            return None
        for (x, y) in targets:
            self._check_stop()
            self.input.click(x, y, pause = 0.08, rand = False)
        logger.info('Builder Base: abilities activated on %d card(s) after %.0fs', len(targets), delay)

    def _deploy_bb_baby_dragons(self, frame):
        '''Baby Dragon edge deploy: zoom out, read the red border, one dragon per zone 2-8 tiles
        outside it (machine with one of them), then abilities after 10-25 s. Falls back to the
        diamond deploy when the border does not show.'''
        self._bb_zoom_out(frame)
        (shot, hull) = self._bb_read_border()
        if shot is None:
            return False
        (cards, machine) = self._bb_dragon_cards(shot)
        if not cards:
            return False
        if hull is None or not self._bb_drop_troops(shot, hull, cards, machine, 'stage 1'):
            logger.warning('Builder Base: red border not found — using the diamond deploy')
            return self._deploy_bb_baby_dragons_diamond(shot)
        if self._loot_prioritise != 'elixir':
            self._bb_activate_abilities(cards, machine)
        return True

    def _deploy_bb_baby_dragons_diamond(self, frame):
        '''Fallback: find all Baby Dragon icons, deploy on diamond edges, wait, then re-click saved icons.'''
        strategy = AttackStrategy(self.input, self.vision, self.config, self.stop_event)
        roi = VisionService.bottom_half_region(frame)
        centers = VisionService.find_all_template_centers(frame, 'babydragon.png', region = roi, max_matches = 12, suppress_pad_frac = _BB_TEMPLATE_SUPPRESS_PAD)
        if not centers:
            return False
        deploy_count = len(centers)
        self.input.click(centers[0][0], centers[0][1], pause = 0.3, rand = False)
        if self.stop_event.wait(0.2):
            return True
        for px, py in strategy._even_diamond_top_perimeter_points(frame, deploy_count, reserve_top_corner_slot = True):
            self._check_stop()
            self.input.click(px, py, pause = _EDRAG_DELAY, rand = False)
        self._deploy_bb_battle_or_flying_machine(strategy)
        if self._loot_prioritise != 'elixir':
            if self.stop_event.wait(_BB_BABY_DRAGON_RECLICK_WAIT):
                return True
            for x, y in centers:
                self._check_stop()
                self.input.click(x, y, pause = 0.15, rand = False)
        return True

    
    def _deploy_bb_battle_or_flying_machine(self, strategy):
        '''One bar lookup: Battle Machine, else Flying Machine; deploy on a random diamond edge.'''
        frame = self.window.screenshot()
        if frame is None:
            return None
        self._update_config_size(frame)
        roi = VisionService.bottom_half_region(frame)
        (tx, ty) = self.vision.find_template(frame, _BB_BATTLE_MACHINE_TEMPLATE, region = roi)
        if not tx:
            (tx, ty) = self.vision.find_template(frame, _BB_FLYING_MACHINE_TEMPLATE, region = roi)
        if not tx:
            logger.debug('Builder Base: %s / %s not found on troop bar', _BB_BATTLE_MACHINE_TEMPLATE, _BB_FLYING_MACHINE_TEMPLATE)
            return None
        (px, py) = strategy._random_diamond_perimeter_point(frame)
        self.input.click(tx, ty, pause = 0.3, rand = False)
        if self.stop_event.wait(0.2):
            return None
        self.input.click(px, py, pause = _EDRAG_DELAY, rand = False)

    
    def _bb_end_battle_and_return_home(self):
        '''Wait for natural battle end, dismiss Okay, then tap BB Return Home.'''
        (ex, ey) = self._wait_for_image('endbattle.png', timeout = 90, error = False)
        if ex:
            self.input.click(ex, ey, pause = 0.15)
        else:
            logger.warning('Builder Base: endbattle.png not found')
            return None
        self._bb_dismiss_okay_and_return_home()

    
    def _bb_gold_prioritise_end_battle_and_return_home(self):
        '''Gold prioritise: wait for 2+ battle stars, then End Battle → Okay → Return Home.'''
        start = time.time()
        timeout = 90
        end_battle_clicked = False
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(0.5):
                    return None
                continue
            self._update_config_size(frame)
            bot_roi = VisionService.bottom_half_region(frame)
            stars = VisionService.find_all_template_centers(frame, _BB_BATTLE_STAR_TEMPLATE, threshold = 0.8, region = bot_roi, max_matches = 3, suppress_pad_frac = 0.35)
            if len(stars) >= _BB_GOLD_PRIORITISE_MIN_STARS:
                bot_roi = VisionService.bottom_half_region(frame)
                (ex, ey) = self.vision.find_template(frame, 'endbattle.png', region = bot_roi)
                if ex:
                    logger.info('Builder Base (gold): %d bbstar.png — clicking endbattle', len(stars))
                    self.input.click(ex, ey, pause = 0.15)
                    end_battle_clicked = True
                    break  # [recovered: decompiler dropped this break and misnested the timeout warning inside the loop]
            if self.stop_event.wait(0.5):
                return None
        if not end_battle_clicked:
            logger.warning('Builder Base (gold): timed out waiting for %d+ %s', _BB_GOLD_PRIORITISE_MIN_STARS, _BB_BATTLE_STAR_TEMPLATE)
            return None
        self._bb_dismiss_okay_and_return_home()

    
    @staticmethod
    def _bb_overall_damage_percent(frame):
        '''The "Overall Damage" percent shown bottom right during a Builder Base battle, or
        None when it does not read (white digits on the dark panel, Tesseract digits only).'''
        import cv2
        import numpy as np
        import pytesseract
        (h, w) = frame.shape[:2]
        (x0, y0, x1, y1) = _BB_DAMAGE_PERCENT_ROI
        crop = frame[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
        if crop.size == 0:
            return None
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        mask = ((hsv[:, :, 2] > 200) & (hsv[:, :, 1] < 70)).astype(np.uint8) * 255
        mask = cv2.resize(255 - mask, None, fx = 2, fy = 2, interpolation = cv2.INTER_CUBIC)
        mask = cv2.copyMakeBorder(mask, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value = 255)
        try:
            text = pytesseract.image_to_string(mask, config = '--psm 7 -c tessedit_char_whitelist=0123456789%')
        except Exception as e:
            logger.debug('Builder Base (trophy): damage OCR failed: %s', e)
            return None
        digits = ''.join(ch for ch in text if ch.isdigit())
        if not digits or len(digits) > 3:
            return None
        value = int(digits)
        return value if value <= 200 else None

    @staticmethod
    def _bb_ready_card_slots(frame):
        '''Centres of the troop-bar cards that can still be deployed: coloured and lit.
        Dead cards are grey, empty slots dark; both are skipped.'''
        import cv2
        (h, w) = frame.shape[:2]
        half = max(6, int(w * 0.0156))
        y = int(_BB_CARD_SLOT_Y * h)
        hsv = cv2.cvtColor(frame[max(0, y - half):min(h, y + half)], cv2.COLOR_BGR2HSV)  # the card row only
        ready = []
        for i in range(_BB_CARD_SLOTS):
            x = int((_BB_CARD_SLOT_X0 + i * _BB_CARD_SLOT_STEP) * w)
            patch = hsv[:, max(0, x - half):min(w, x + half)]
            if patch.size == 0:
                continue
            (sat, val) = (float(patch[:, :, 1].mean()), float(patch[:, :, 2].mean()))
            if sat >= _BB_CARD_READY_MIN_SAT and val >= _BB_CARD_READY_MIN_VAL:
                ready.append((x, y))
        return ready

    def _bb_trophy_deploy_stage2(self, frame):
        '''Stage 2 (the second village): zoom out, select a ready card and tap the village
        centre (on the buildings) so the game shows the red border, read it, then spread every
        ready dragon (survivors + fresh cards) over the zones. Returns the cards deployed.'''
        self._bb_zoom_out(frame)
        shot = self.window.screenshot()
        if shot is None:
            return 0
        self._update_config_size(shot)
        (cards, machine) = self._bb_dragon_cards(shot)
        if not cards:
            return 0
        centre = bb_edge.village_centre(shot)
        self.input.click(cards[0][0], cards[0][1], pause = _BB_CARD_SELECT_PAUSE, rand = False)
        self.input.click(centre[0], centre[1], pause = 0.1, rand = False)
        (border_frame, hull) = self._bb_read_border()
        if hull is None:
            logger.warning('Builder Base (trophy): stage-2 red border not shown — using a ring around the village centre')
            hull = bb_edge.synthetic_hull(centre, shot)
        # The tap could have dropped a dragon on open ground: re-read which cards are left.
        after = self.window.screenshot()
        if after is not None:
            (cards, machine) = self._bb_dragon_cards(after)
        if not cards:
            return 1
        self._bb_drop_troops(border_frame if border_frame is not None else shot, hull, cards, machine, 'trophy stage 2')
        self._bb_activate_abilities(cards, machine)
        return len(cards)

    def _bb_trophy_return_home(self, frame):
        '''Result screen after both stages: "Return Home" is there directly (no Okay).
        True when it was clicked.'''
        (rx, ry) = self.vision.find_template(frame, _BB_RETURN_HOME_TEMPLATE)
        if not rx:
            return False
        self.input.click(rx, ry, pause = 0.5)
        return True

    def _bb_trophy_play_both_stages_and_return_home(self):
        '''Trophy prioritise: never press End Battle or Surrender. Stage 1 plays out; when
        "Overall Damage" passes 100% the battle moves to the second village — deploy the
        ready cards there, then wait for the result screen and Return Home.'''
        start = time.time()
        stage2_at = None
        hits = 0
        deploys = 0
        last_deploy = 0.0
        while time.time() - start < _BB_TROPHY_BATTLE_TIMEOUT:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(0.5):
                    return None
                continue
            self._update_config_size(frame)
            if self._bb_trophy_return_home(frame):
                logger.info('Builder Base (trophy): battle over after %ds (%d stage-2 deploy(s)) — Return Home', int(time.time() - start), deploys)
                return None
            if self.vision.find_template(frame, 'okay.png')[0]:
                logger.info('Builder Base (trophy): battle over after %ds — Okay', int(time.time() - start))
                self._bb_dismiss_okay_and_return_home(retry_battle_template = 'okay.png')
                return None
            now = time.time()
            if stage2_at is None:
                percent = self._bb_overall_damage_percent(frame)
                hits = hits + 1 if percent is not None and percent >= 100 else 0
                if hits >= 2:
                    stage2_at = now
                    logger.info('Builder Base (trophy): stage 1 done (%s%%) after %ds — moving to the second village', percent, int(now - start))
            elif (deploys < _BB_TROPHY_MAX_STAGE2_DEPLOYS and now - stage2_at >= _BB_TROPHY_STAGE2_SETTLE
                  and now - last_deploy >= _BB_TROPHY_REDEPLOY_WAIT):
                if self._bb_trophy_deploy_stage2(frame):
                    deploys += 1
                    last_deploy = time.time()
                    continue
            if self.stop_event.wait(1.0):
                return None
        logger.warning('Builder Base (trophy): no result screen after %ds — ending the battle', _BB_TROPHY_BATTLE_TIMEOUT)
        (ex, ey) = self._wait_for_image('endbattle.png', timeout = 3, error = False)
        if ex:
            self.input.click(ex, ey, pause = 0.15)
            self._bb_dismiss_okay_and_return_home()
        else:
            self._bb_surrender_and_return_home()

    def _bb_return_home_template_for_screen(self, width, height):
        '''Return (template name, scale_template) for Builder Base Return Home.'''
        (tw, th) = _BB_1080P_CAPTURE_SIZE
        tol = _BB_1080P_SIZE_TOLERANCE
        if abs(width - tw) <= tol and abs(height - th) <= tol:
            return (_BB_RETURN_HOME_TEMPLATE_1080P, False)
        return (_BB_RETURN_HOME_TEMPLATE, True)

    
    def _wait_for_bb_return_home(self, timeout = 15):
        '''Wait for BB Return Home; picks 1080p-native template when capture is ~1920x1080.'''
        start = time.time()
        template_name = _BB_RETURN_HOME_TEMPLATE
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                # No capture (window lost / minimised): pause instead of spinning.
                if self.stop_event.wait(0.5):
                    return (None, None, template_name)
                continue
            self._update_config_size(frame)
            (h, w) = frame.shape[:2]
            (template_name, scale_template) = self._bb_return_home_template_for_screen(w, h)
            search_region = self._search_region_for_template(frame, template_name, None, None, 200)
            (x, y) = self.vision.find_template(frame, template_name, threshold = 0.8, region = search_region, scale_template = scale_template)
            if x:
                return (x, y, template_name)
            if self.stop_event.wait(0.5):
                return (None, None, template_name)
        return (None, None, template_name)

    
    def _bb_dismiss_okay_and_return_home(self, *, retry_battle_template = 'endbattle.png', max_retries = _BB_RETURN_HOME_END_BATTLE_RETRIES):
        '''Dismiss Okay, tap Return Home; retry battle-end + Okay if Return Home stays hidden.'''
        return_home_template = _BB_RETURN_HOME_TEMPLATE
        for attempt in range(max_retries + 1):
            self._check_stop()
            if attempt > 0:
                (bx, by) = self._wait_for_image(retry_battle_template, timeout = 3, error = False)
                if bx:
                    self.input.click(bx, by, pause = 0.15)
                else:
                    logger.debug('Builder Base: %s retry %d/%d — control not visible', retry_battle_template, attempt, max_retries)
            okay_timeout = 10 if attempt == 0 else 5
            (ox, oy) = self._wait_for_image('okay.png', timeout = okay_timeout, error = False)
            if ox:
                self.input.click(ox, oy, pause = 0.15)
            (rx, ry, return_home_template) = self._wait_for_bb_return_home(timeout = 15)
            if rx:
                self.input.click(rx, ry, pause = 0.2)
                if attempt > 0:
                    logger.info('Builder Base: return home after %d %s retry(ies)', attempt, retry_battle_template)
                return None
            if not attempt < max_retries:
                continue
            logger.info('Builder Base: %s not found — retrying %s + okay (%d/%d)', return_home_template, retry_battle_template, attempt + 1, max_retries)
        logger.warning('Builder Base: %s not found after %d %s retries', return_home_template, max_retries, retry_battle_template)

    
    def _bb_recover_from_battle(self):
        '''No Battle button: if a battle is running (run started mid-attack, a stolen
        tap), close any troop/popup menu on top of it, surrender and return home.'''
        frame = self.window.screenshot()
        if frame is None:
            return False
        self._update_config_size(frame)
        (rx, ry) = self.vision.find_template(frame, _BB_RETURN_HOME_TEMPLATE)
        if rx:
            logger.info('Builder Base: battle already over — clicking Return Home')
            self.input.click(rx, ry, pause = 0.5)
            return True
        # Before any troop is down the battle shows End Battle, not Surrender (live: the
        # recovery looked for Surrender only and the bot sat 3.5 minutes in a battle).
        if self.vision.find_template(frame, 'surrender.png')[0]:
            button = 'surrender.png'
        elif self.vision.find_template(frame, 'endbattle.png')[0]:
            button = 'endbattle.png'
        else:
            return False
        logger.info('Builder Base: a battle is running — leaving it (%s) to get back home', button)
        if button == 'surrender.png':
            # Nothing is deployed with End Battle up: an empty-ground tap there could drop
            # the selected card, so it is only used to close menus once troops are down.
            self.input.click(pause = 0.3, *self.config.get_point('empty'))
        self._bb_surrender_and_return_home(button)
        return True

    def _bb_surrender_and_return_home(self, button = 'surrender.png'):
        '''Elixir prioritise: surrender right after deploy, then Okay + Return Home. Also
        leaves a battle with nothing deployed, where the button is End Battle (``button``
        is the one expected first; the other is tried briefly after it).'''
        other = 'endbattle.png' if button == 'surrender.png' else 'surrender.png'
        for (template, timeout) in ((button, 10), (other, 2)):
            (sx, sy) = self._wait_for_image(template, timeout = timeout, error = False)
            if sx:
                break
        if not sx:
            logger.warning('Builder Base: surrender.png / endbattle.png not found')
            return None
        self.input.click(sx, sy, pause = 0.15)
        self._bb_dismiss_okay_and_return_home(retry_battle_template = template)

    
    def _find_match_and_attack(self, method_id, ranked_fill = False):
        """One attack cycle. Returns ``'ranked_limit'`` (stop now), ``'troop'`` (troops missing — retry later), or None."""
        battle_template = 'rankedbattle.png' if ranked_fill else 'farmbattle.png'
        (fx, fy) = self._find_template_once(battle_template)
        if fx:
            # A previous cycle left the battle-selection screen open (stolen tap / derail) —
            # use it directly instead of hunting for the home Attack button it covers.
            logger.info('Attack: battle-selection screen already open — continuing from Find a Match')
        else:
            (ax, ay) = self._wait_for_attack_with_nudge()
            if not ax:
                return None
            # Home screen confirmed (Attack visible) → the HUD is readable: record the
            # pre-attack loot baseline / accumulate the previous battle's gains.
            # [recovered: this call existed only in the wall path — with walls off the
            # loot tracker never ran (live repro: 3 battles, session totals stuck at 0)]
            self._loot_snapshot_before_attack()
            self.input.click(ax, ay, pause = 0.1)
            (fx, fy) = self._wait_for_image(battle_template)
        if not fx:
            if ranked_fill:
                msg = 'Ranked battle button not found — daily limit may be reached. Stopping.'
                logger.info(msg)
                cb = getattr(self, '_status_callback', None)
                if cb:
                    cb(msg)
                return 'ranked_limit'
            return None
        self.input.click(fx, fy, pause = 0.1)
        # A single tap here is unreliable: event popups (Card Hunt etc.) or a still-animating
        # screen can eat it. Verify the army screen (attack2) actually appeared; while the
        # Find a Match button is still on screen, the tap was stolen — tap again (the first
        # stolen tap also closes whatever popup ate it).
        (a2x, a2y) = self._wait_for_image('attack2.png', timeout = 5, error = False)
        for _ in range(3):
            if a2x:
                break
            (rfx, rfy) = self._find_template_once(battle_template)
            if not rfx:
                break
            logger.info('%s still on screen — click was eaten (popup?); re-clicking', battle_template)
            self.input.click(rfx, rfy, pause = 0.1)
            (a2x, a2y) = self._wait_for_image('attack2.png', timeout = 5, error = False)
        if not a2x:
            (a2x, a2y) = self._wait_for_image('attack2.png')
        if method_id == 3 and not self._ensure_valkyrie_army_from_recipes():
            # Attack anyway with whatever is trained — a partial Valkyrie army still loots, and
            # bailing out here would leave the Find a Match screen open with nothing to recover it.
            msg = 'Valkyrie army not confirmed (slow screen or missing saved recipe) — attacking with current army'
            logger.warning(msg)
            cb = getattr(self, '_status_callback', None)
            if cb:
                cb(msg)
        if a2x:
            self.input.click(a2x, a2y, pause = 0.1)
            if ranked_fill:
                (rx, ry) = self._wait_for_image('rankedattackconfirm.png', timeout = 10)
                if not rx:
                    logger.warning('rankedattackconfirm.png not found after attack2.png')
                else:
                    self.input.click(rx, ry, pause = 0.1)
        self._wait_for_any_image(('surrender.png', 'endbattle.png'), timeout = 30)
        frame = self.window.screenshot()
        if frame is None:
            return None
        self._update_config_size(frame)
        (h, w) = frame.shape[:2]
        cy = h // 2
        cx = w // 2
        self.input.move(cx, cy)
        if self.stop_event.wait(0.05):
            return None
        self.input.scroll(cx, cy, 3)
        frame = self.window.screenshot()
        if frame is None:
            return None
        self._update_config_size(frame)
        strategy = self._get_strategy(method_id)
        strategy.event_handler = self._battle_rewards
        result = strategy.execute(frame, self.stop_event)
        if result is not False:
            self._attacks_done = getattr(self, '_attacks_done', 0) + 1
        self._wait_for_battle_end(is_sneaky = method_id == 1)
        return 'troop' if result is False else None

    
    def _get_strategy(self, method_id):
        cb = getattr(self, '_status_callback', None)
        eq = getattr(self, '_earthquake_method', EARTHQUAKE_METHOD_CURVE)
        if method_id == 1:
            return TroopSpamStrategy(self.input, self.vision, self.config, self.stop_event, 'sneaky', 15, status_callback = cb, earthquake_method = eq)
        if method_id == 2:
            return TroopSpamStrategy(self.input, self.vision, self.config, self.stop_event, 'superminion', _SUPERMINION_DEPLOY_SECONDS, status_callback = cb, earthquake_method = eq)
        if method_id == 3:
            return TroopSpamStrategy(self.input, self.vision, self.config, self.stop_event, 'valkyrie', 7, status_callback = cb, earthquake_method = eq)
        if method_id == 4:
            return EdragStrategy(self.input, self.vision, self.config, self.stop_event, status_callback = cb, earthquake_method = eq)
        return TroopSpamStrategy(self.input, self.vision, self.config, self.stop_event, 'sneaky', 15, status_callback = cb, earthquake_method = eq)

    
    def _wait_for_battle_end(self, is_sneaky):
        if is_sneaky:
            if self.stop_event.wait(3):
                return None
            (sx, sy) = self._wait_for_image('surrender.png', timeout = 2, error = False)
            if sx:
                self.input.click(sx, sy, pause = 0.1)
                return None
            (bx, by) = self._wait_for_image('endbattle.png', timeout = 2, error = False)
            if bx:
                self.input.click(bx, by, pause = 0.1)
                return None
            return None
        (bx, by) = self._wait_for_image('endbattle.png', timeout = 60, error = False)
        if bx:
            self.input.click(bx, by, pause = 0.1)
            return None
        (sx, sy) = self._wait_for_image('surrender.png', timeout = 2, error = False)
        if sx:
            self.input.click(sx, sy, pause = 0.1)
            return None

    
    def _return_home(self):
        '''Dismiss Okay if present, then wait for ``returnhome.png`` (+ ``returnhome2.png`` on 16:10) or ``chestclaim.png`` (mutually exclusive).'''
        (ox, oy) = self._wait_for_image('okay.png', timeout = 10)
        if ox:
            self.input.click(ox, oy, pause = 0.1)
        (kind, hx, hy) = self._wait_for_return_home_or_chest_claim(timeout = 10)
        if kind == 'return' and hx:
            self.input.click(hx, hy, pause = 0.1)
            return ox is not None
        if kind == 'chest' and hx:
            logger.info('Post-battle UI: chestclaim.png (replacing return home); running chest flow')
            self.input.click(hx, hy, pause = 0.2)
            if self.stop_event.wait(0.35):
                return ox is not None
            self._tap_empty_until_chest_continue()
        return ox is not None

    
    def _wait_for_return_home_or_chest_claim(self, timeout = 10):
        '''
Poll one frame for ``returnhome.png`` (+ ``returnhome2.png`` on 16:10 only) then ``chestclaim.png`` (only one should match).
Returns (``"return"`` | ``"chest"``, x, y) or (None, None, None) on timeout.
'''
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(0.5):
                    return (None, None, None)
                continue
            self._update_config_size(frame)
            if self._battle_rewards.handle(frame):
                continue
            (rx, ry) = (None, None)
            returnhome_tpls = ('returnhome.png', 'returnhome2.png') if self.config.aspect_key == ASPECT_16_10 else ('returnhome.png',)
            for tpl in returnhome_tpls:
                (rx, ry) = self.vision.find_template(frame, tpl)
                if rx:
                    break  # [recovered: decompiler dropped this break, letting the last template overwrite a match]
            if rx:
                return ('return', rx, ry)
            (cx, cy) = self.vision.find_template(frame, 'chestclaim.png')
            if cx:
                return ('chest', cx, cy)
            if self.stop_event.wait(0.5):
                return (None, None, None)
            if time.time() - start < timeout:
                continue
        logger.warning('Timeout waiting for returnhome.png / returnhome2.png (16:10) or chestclaim.png')
        return (None, None, None)

    
    def _random_point_chest_tap_through(self):
        '''Random point near center-right of the capture for chest tap-through (±85 px from anchor).'''
        (w, h) = (self.config.width, self.config.height)  # [recovered: pycdc reversed STORE_FAST_STORE_FAST pairs]
        if w <= 1 or h <= 1:
            (w, h) = (self.config.ref_width, self.config.ref_height)
        cx = int(w * 0.75)
        cy = h // 2
        j = 85
        return (max(0, min(w - 1, cx + random.randint(-j, j))), max(0, min(h - 1, cy + random.randint(-j, j))))

    
    def _tap_empty_until_chest_continue(self):
        '''After ``chestclaim`` was clicked: tap center-right (±85px) until ``chestcontinue.png``, then click it (home).'''
        CHEST_TAP_TIMEOUT = 120
        deadline = time.time() + CHEST_TAP_TIMEOUT
        while time.time() < deadline:
            self._check_stop()
            (nx, ny) = self._random_point_chest_tap_through()
            self.input.click_at(nx, ny, rand = False)
            t0 = time.time()
            if self.stop_event.wait(0.15):
                return None
            frame2 = self.window.screenshot()
            if not frame2 is None:
                self._update_config_size(frame2)
                (tx, ty) = self.vision.find_template(frame2, 'chestcontinue.png')
                if tx:
                    logger.info('Chest reward: chestcontinue.png found; clicking (expect home village)')
                    self.input.click(tx, ty, pause = 0.25)
                    return None
            elapsed = time.time() - t0
            to_wait = max(0.05, 0.5 - elapsed)
            if self.stop_event.wait(to_wait):
                return None
        logger.warning(f'''chestcontinue.png not seen within {int(CHEST_TAP_TIMEOUT)}s after chest claim; continuing bot loop''')  # [recovered: decompiler misnested this inside the loop, ending the tap-through after one tap]
        return None

    
    def _is_star_bonus_claimed(self):
        '''True if neither emptystar nor glowstar matches strongly (bonus claimed / not shown).'''
        frame = self.window.screenshot()
        if frame is None:
            return False
        self._update_config_size(frame)
        for template in ('emptystar.png', 'glowstar.png'):
            (_, _, confidence) = self.vision.find_template_with_confidence(frame, template, threshold = 0)  # [recovered + verified against original bytecode]
            if confidence >= _STAR_BONUS_THRESHOLD:
                return False
        return True

    
    def _is_bb_star_bonus_finished(self):
        '''True when ``bstar.png`` is not visible in the bottom half (BB star bonus attacks done).'''
        frame = self.window.screenshot()
        if frame is None:
            return False
        self._update_config_size(frame)
        bot_roi = VisionService.bottom_half_region(frame)
        (_, _, confidence) = self.vision.find_template_with_confidence(frame, _BB_STAR_BONUS_TEMPLATE, threshold = 0.0, region = bot_roi)  # [recovered + verified against original bytecode]
        return confidence < _STAR_BONUS_THRESHOLD

    
    def _home_screen_recovery(self):
        '''Ensures we are back at home screen. Escapes popups, stray screens, live battles, and end screens.'''
        for _ in range(20):
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(1):
                    return None
                continue
            self._update_config_size(frame)
            if self._battle_rewards.handle(frame):
                continue
            if self._dismiss_okay_or_exit_on_frame(frame):
                if self.stop_event.wait(0.3):
                    return None
                continue
            (sx, sy) = self.vision.find_template(frame, 'surrender.png')
            if sx:
                logger.info('Recovery: live battle — surrendering to get home')
                self.input.click(sx, sy, pause = 0.3)
                if self.stop_event.wait(0.5):
                    return None
                continue
            (rx, ry) = self.vision.find_template(frame, 'returnhome.png')
            if rx:
                logger.info('Recovery: clicking Return Home')
                self.input.click(rx, ry, pause = 0.3)
                if self.stop_event.wait(0.5):
                    return None
                continue
            if get_template_path('reload.png').exists():
                (lx, ly) = self.vision.find_template(frame, 'reload.png')
                if lx:
                    now = time.monotonic()
                    first = getattr(self, '_reload_first_seen', None)
                    if first is None:
                        self._reload_first_seen = now
                        logger.warning('Recovery: connection-lost dialog detected — waiting %ds before reloading (another device may be using the account)', _RELOAD_GRACE_SECONDS)
                    elif now - first >= _RELOAD_GRACE_SECONDS:
                        logger.warning('Recovery: connection-lost dialog persisted — clicking RELOAD')
                        self.input.click(lx, ly, pause = 1.0)
                        self._reload_first_seen = None
                        if self.stop_event.wait(10):
                            return None
                    if self.stop_event.wait(2):
                        return None
                    continue
            top_roi = VisionService.top_half_region(frame)
            (hx, hy) = self._find_home_village_builder(frame, top_roi)
            if hx:
                self._reload_first_seen = None
                return None
            if not self.stop_event.wait(1):
                continue
        return None

    
    def _switch_account_and_load_home(self, username):
        '''Open Settings → Change user, OCR-click username, wait for home. Raises on failure.'''
        cb = getattr(self, '_status_callback', None)
        msg = f'''Multi-run: switching to {username!r}'''
        logger.info(msg)
        if cb:
            cb(msg)
        self._wall_costs = set()  # wall prices belong to the previous village
        (stx, sty) = self._wait_for_image('settings.png')
        if not stx:
            raise RuntimeError('Multi-run: settings button not found')
        self.input.click(stx, sty, pause = 0.25)
        (cux, cuy) = self._wait_for_image('changeuser.png')
        if not cux:
            raise RuntimeError('Multi-run: change user button not found')
        self.input.click(cux, cuy, pause = 1)
        (ucx, ucy) = self._wait_for_player_name(username, timeout = 25, min_confidence = 70, tesseract_config = '--psm 11', match_alnum_only = True, fuzzy_min_ratio = 0.8, white_text = True)
        if not ucx:
            err = f'''Multi-run: could not find username "{username}" on screen (OCR)'''
            logger.error(err)
            if cb:
                cb(err)
            raise RuntimeError(err)
        self.input.click(ucx, ucy, pause = 0.2)
        if self.stop_event.wait(1):
            self._check_stop()
        (ax, ay) = self._wake_home_and_wait_for_attack(timeout = 30)
        if not ax:
            err = f'''Multi-run: Home Village not ready after loading {username!r} (builder.png|gbuilder.png / attack.png timeout after login / leaving Builder Base)'''
            logger.error(err)
            if cb:
                cb(err)
            raise RuntimeError(err)
        self._loot_prev_resources = None

    
    def _wake_home_and_wait_for_attack(self, timeout = 30):
        '''
After switching accounts: dismiss idle UI, then poll the **top half** for village type
(``mbuilder.png`` = Builder Base; ``builder.png`` or ``gbuilder.png`` = Home Village). If Builder Base,
leave via :meth:`_leave_builder_base_with_nboat`. When Home Village is detected, return
``attack.png`` coordinates from the **bottom half** (battle bar) once visible — same
template as :meth:`_find_match_and_attack` uses to start battles.
Each iteration dismisses ``okay.png`` / ``exit.png`` if present, then village / attack logic; else nudge.
'''
        frame = self.window.screenshot()
        self._update_config_size(frame)
        empty_pt = self.config.get_point('empty')
        self.input.click(pause = 0.2, *empty_pt)
        self.input.scroll(*self._scroll_point(), 20)
        delay = random.uniform(0.1, 0.3)
        if self.stop_event.wait(delay):
            return (None, None)
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if not frame is None:
                self._update_config_size(frame)
                if self._dismiss_okay_or_exit_on_frame(frame):
                    if self.stop_event.wait(0.25):
                        return (None, None)
                    continue
                top_roi = VisionService.top_half_region(frame)
                (mx, my) = self.vision.find_template(frame, 'mbuilder.png', region = VisionService.bottom_right_quadrant_region(frame))  # Oct 2026 UI: builder portraits bottom-right
                if mx:
                    logger.info('Account loaded in Builder Base (mbuilder.png); leaving to Home Village')
                    cb = getattr(self, '_status_callback', None)
                    if cb:
                        cb('Multi-run: Builder Base on login — leaving (nboat)')
                    self._leave_builder_base_with_nboat(settle_before_drag = False)
                    if self.stop_event.wait(1):
                        return (None, None)
                    continue
                (hx, hy) = self._find_home_village_builder(frame, top_roi)
                if hx:
                    bot_roi = VisionService.bottom_half_region(frame)
                    (ax, ay) = self.vision.find_template(frame, 'attack.png', region = bot_roi)
                    if ax:
                        return (ax, ay)
            self._nudge_view_to_reveal_attack()
            if self.stop_event.wait(0.35):
                return (None, None)
        return (None, None)  # [recovered: decompiler put an unconditional return inside the loop, so only one poll ever ran]

    
    def _detect_village_type(self, frame = None):
        '''Return ``"home"``, ``"builder"``, or ``None`` from top-half builder portraits.'''
        if frame is None:
            frame = self.window.screenshot()
        if frame is None or frame.size == 0:
            return None
        self._update_config_size(frame)
        top_roi = VisionService.top_half_region(frame)
        (mx, my) = self.vision.find_template(frame, 'mbuilder.png', region = VisionService.bottom_right_quadrant_region(frame))  # Oct 2026 UI: builder portraits bottom-right
        if mx:
            return 'builder'
        (hx, hy) = self._find_home_village_builder(frame, top_roi)
        if hx:
            return 'home'

    
    def _go_to_builder_base_with_boat(self):
        '''Home Village → Builder Base via ``boat.png``.'''
        self._check_stop()
        (bx, by) = self._wait_for_image('boat.png', timeout = 15, error = False)
        if not bx:
            logger.warning('boat.png not found — cannot switch to Builder Base')
            return False
        self.input.click(bx, by, pause = 0.25)
        if self.stop_event.wait(1):
            return False
        (mx, my) = self._wait_for_image('mbuilder.png', timeout = 15, error = False)
        if not mx:
            logger.warning('mbuilder.png not found after boat — may still be in Home Village')
            return False
        return True

    
    def _ensure_correct_village(self, builder_base):
        '''Before farming: switch villages if the wrong builder portrait is showing.'''
        self._check_stop()
        self.input.click(pause = 0.15, *self.config.get_point('empty'))
        if self.stop_event.wait(0.2):
            return None
        village = self._detect_village_type()
        if builder_base:
            if village == 'builder':
                return None
            if village == 'home':
                logger.info('Startup: in Home Village but Builder Base was selected — taking boat')
                self._go_to_builder_base_with_boat()
                return None
            logger.warning('Startup: could not detect village (expected Builder Base)')
            return None
        if village == 'home':
            return None
        if village == 'builder':
            logger.info('Startup: in Builder Base but Home Village was selected — leaving (nboat)')
            self._leave_builder_base_with_nboat()
            return None
        logger.warning('Startup: could not detect village (expected Home Village)')

    
    def _leave_builder_base_with_nboat(self, settle_before_drag = True):
        '''
Pan down-left from screen center (~500px), then click ``nboat.png`` to return to Home Village.
Does not check ``mbuilder.png`` first — call only when a BB→HV trip is intended.

``settle_before_drag``: small delay after prior UI (e.g. collect clicks) before capturing
dimensions and dragging.
'''
        self._check_stop()
        if settle_before_drag and self.stop_event.wait(0.75):
            self._check_stop()
        logger.info('Leaving Builder Base (drag + nboat)')
        cb = getattr(self, '_status_callback', None)
        if cb:
            cb('Multi-run: leaving Builder Base (nboat)')
        self._bb_pan_down_left_from_center()
        (nx, ny) = self._wait_for_image('nboat.png', timeout = 12, error = False)
        if nx:
            self.input.click(nx, ny, pause = 0.25)
            return None
        logger.warning('nboat.png not found after Builder Base drag — may still be in Builder Base')

    
    def _multi_run_collect_home_village_resources(self):
        '''Multi-run: tap Home Village collect bubbles if visible, before taking the boat to Builder Base.'''
        cb = getattr(self, '_status_callback', None)
        logger.info('Multi-run: Home Village collect (hgold, helixir, hdelixir)')
        if cb:
            cb('Multi-run: Home Village collect')
        for tpl in ('hgold.png', 'helixir.png', 'hdelixir.png'):
            self._check_stop()
            (rx, ry) = self._find_template_once(tpl, threshold = 0.7)
            if not rx:
                continue
            self.input.click(rx, ry, pause = 0.15)

    
    def _multi_run_builder_base_after_session(self):
        """
Multi-run only: after an account's farming session, collect Home Village resources if icons
appear, open the secondary base via boat, collect builder resources if icons appear,
optionally run the clock boost chain, then leave Builder Base.
"""
        self._multi_run_collect_home_village_resources()
        cb = getattr(self, '_status_callback', None)
        msg = 'Multi-run: Builder Base (boat → collect)'
        logger.info(msg)
        if cb:
            cb(msg)
        (bx, by) = self._wait_for_image('boat.png', timeout = 15, error = False)
        if not bx:
            logger.warning('Multi-run: boat.png not found — skipping Builder Base step')
            return None
        self.input.click(bx, by, pause = 0.2)
        if self.stop_event.wait(1):
            self._check_stop()
        for tpl in ('bgold.png', 'belixir.png', 'bgem.png'):
            self._check_stop()
            (rx, ry) = self._find_template_once(tpl, threshold = 0.7)
            if not rx:
                continue
            self.input.click(rx, ry, pause = 0.15)
        self._check_stop()
        (cx, cy) = self._wait_for_image('bclock.png', timeout = 2, error = False)
        if cx:
            self.input.click(cx, cy, pause = 0.2)
            if self.stop_event.wait(1):
                self._check_stop()
            (cbx, cby) = self._wait_for_image('clockboost.png', timeout = 10, error = False)
            if cbx:
                self.input.click(cbx, cby, pause = 0.2)
            if self.stop_event.wait(1):
                self._check_stop()
            (bux, buy) = self._wait_for_image('boost.png', timeout = 10, error = False)
            if bux:
                self.input.click(bux, buy, pause = 0.15)
        self._leave_builder_base_with_nboat(settle_before_drag = True)

    
    def _frame_shows_supercell_login_prompt(self, frame):
        """True if OCR sees the Supercell ID login line (list scroll won't help)."""
        if frame is None or frame.size == 0:
            return False
        words = self.vision.find_words_ocr(frame, query = None, min_confidence = 20, preprocess = True, tesseract_config = '--psm 11', white_text = True)
        blob = ' '.join([ w.text for w in words ]).lower()
        if 'supercell id' in blob:
            return True
        if 'log in' in blob and 'supercell' in blob:
            return True
        return False

    
    def _scroll_player_list_with_drag(self, frame):
        '''Drag ~200px upward from lower-right (client coords) to scroll the change-user list.'''
        if frame is None or frame.size == 0:
            return None
        (h, w) = frame.shape[:2]
        x1 = int(w * 0.86) + random.randint(-15, 15)
        x1 = max(int(w * 0.72), min(w - 8, x1))
        y1 = int(h * 0.86) + random.randint(-12, 12)
        y1 = max(int(h * 0.55), min(h - 12, y1))
        y2 = max(int(h * 0.12), y1 - 200)
        x2 = x1
        self.input.mouse_down(x1, y1)
        self.input.human_move(x1, y1, x2, y2, duration = random.uniform(0.28, 0.42))
        self.input.mouse_up(x2, y2)

    
    def _wait_for_player_name(self, text, timeout = 25, error = True, region = None, **ocr_kwargs):
        '''
Like :meth:`_wait_for_text`, but after each failed OCR pass drags upward in the lower-right
to scroll the account list before trying again.

OCR is limited to the right half of the window unless ``region`` is passed explicitly.
'''
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(0.5):
                    return (None, None)
                continue
            self._update_config_size(frame)
            roi = region if not region is None else VisionService.right_half_region(frame)
            (x, y) = self.vision.find_word_on_screen(frame, text, region = roi, **ocr_kwargs)
            if x:
                return (x, y)
            if self._frame_shows_supercell_login_prompt(frame):
                msg = f'''Multi-run: "Log in to Supercell ID" is showing and {text!r} was not found — log in or dismiss that screen, then retry.'''
                logger.warning(msg)
                cb = getattr(self, '_status_callback', None)
                if cb:
                    cb(msg)
                raise RuntimeError(msg)
            self._scroll_player_list_with_drag(frame)
            if self.stop_event.wait(0.45):
                return (None, None)
            if error:
                logger.warning(f'''Timeout waiting for player name OCR match: {text!r}''')
        return (None, None)

    
    def _wait_for_text(self, text, timeout = 10, error = True, region = None, **ocr_kwargs):
        '''Poll screenshots until OCR finds ``text`` (substring match). Returns click center.'''
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(0.5):
                    return (None, None)
                continue
            self._update_config_size(frame)
            (x, y) = self.vision.find_word_on_screen(frame, text, region = region, **ocr_kwargs)
            if x:
                return (x, y)
            if self.stop_event.wait(0.5):
                return (None, None)
        if error:
            logger.warning(f'''Timeout waiting for OCR text containing {text!r}''')
        return (None, None)

    
    def _dismiss_open_popup(self):
        '''Best-effort close of whatever popup is on screen (okay/exit) so the flow underneath is usable again.'''
        frame = self.window.screenshot()
        if frame is None:
            return False
        self._update_config_size(frame)
        return self._dismiss_okay_or_exit_on_frame(frame)


    def _ensure_valkyrie_army_from_recipes(self):
        '''If Valkyrie army template is missing, load it from Saved Recipes. Returns False on failure.'''
        (vx, vy) = self._wait_for_image('valkarmy.png', timeout = 3, error = False)
        if vx:
            return True
        (sx, sy) = self._wait_for_image('savedrecipes.png')
        if not sx:
            logger.warning('Saved Recipes button not found while ensuring Valkyrie army')
            return False
        self.input.click(sx, sy, pause = 0.2)
        (rx, ry) = self._wait_for_image('valkrecipe.png')
        if not rx:
            logger.warning('Valkyrie recipe template not found')
            self._dismiss_open_popup()  # close the recipes popup we opened
            return False
        (ux, uy) = self._wait_for_image('use.png', y_anchor = ry, y_slop = 200)
        if not ux:
            logger.warning('Use button not found near Valkyrie recipe row')
            self._dismiss_open_popup()  # close the recipes popup we opened
            return False
        self.input.click(ux, uy, pause = 0.2)
        if self.stop_event.wait(0.35):
            return False
        (vx2, _) = self._wait_for_image('valkarmy.png', timeout = 5, error = False)
        if not vx2:
            logger.warning('valkarmy.png still not visible after applying saved recipe')
            return False
        return True

    
    def _search_region_for_template(self, frame, template, region = None, y_anchor = None, y_slop = 200):
        if not region is None:
            return region
        if not y_anchor is None:
            (h, w) = frame.shape[:2]
            y0 = max(0, y_anchor - y_slop)
            y1 = min(h, y_anchor + y_slop)
            return (0, y0, w, y1 - y0)
        if template in BOTTOM_RIGHT_BOT_TEMPLATES:
            return VisionService.bottom_right_quadrant_region(frame)
        if template in TOP_HALF_BOT_TEMPLATES:
            return VisionService.top_half_region(frame)
        if template in BOTTOM_HALF_BOT_TEMPLATES:
            return VisionService.bottom_half_region(frame)

    
    def _find_template_once(self, template, region = None, y_anchor = None, y_slop = 200, threshold = 0.8):
        '''One screenshot; match template or return (None, None). No polling.'''
        self._check_stop()
        frame = self.window.screenshot()
        if frame is None:
            return (None, None)
        self._update_config_size(frame)
        search_region = self._search_region_for_template(frame, template, region, y_anchor, y_slop)
        return self.vision.find_template(frame, template, threshold = threshold, region = search_region)

    
    def _wait_for_any_image(self, templates, timeout = 10, error = True, threshold = 0.8, region = None, region_from_frame = None):
        '''First ordered template match wins (checked left-to-right each frame).'''
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                # No capture (window lost / minimised): pause instead of spinning.
                if self.stop_event.wait(0.5):
                    return (None, None)
                continue
            self._update_config_size(frame)
            if self._battle_rewards.handle(frame):
                continue
            search_region = region
            if search_region is None and region_from_frame is not None:  # [recovered: both conditions were inverted]
                search_region = region_from_frame(frame)
            for template in templates:
                tpl_region = search_region
                if tpl_region is None:
                    tpl_region = self._search_region_for_template(frame, template, None, None, 200)
                (x, y) = self.vision.find_template(frame, template, threshold = threshold, region = tpl_region)
                if x:  # [recovered: was an unconditional `return`, so only the first template was ever checked]
                    return (x, y)
            if self.stop_event.wait(0.5):
                return (None, None)
            if time.time() - start < timeout:
                continue
        if error:
            logger.warning(f'''Timeout waiting for any of {templates}''')
        return (None, None)

    
    def _wait_for_image(self, template, timeout = 10, error = True, region = None, y_anchor = None, y_slop = 200, threshold = 0.8):
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                # No capture (window lost / minimised): pause instead of spinning.
                if self.stop_event.wait(0.5):
                    return (None, None)
                continue
            self._update_config_size(frame)
            if self._battle_rewards.handle(frame):
                continue
            search_region = self._search_region_for_template(frame, template, region, y_anchor, y_slop)
            (x, y) = self.vision.find_template(frame, template, threshold = threshold, region = search_region)
            if x:
                return (x, y)
            if self.stop_event.wait(0.5):
                return (None, None)
        if error:
            logger.warning(f'''Timeout waiting for {template}''')
        return (None, None)


