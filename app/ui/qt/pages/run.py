'''Run page — attack, schedule, modes, live status, controls.'''
from __future__ import annotations
import json
import time
from datetime import datetime
from typing import Callable, List, Optional
from app.utils.common import APP_NAME
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtWidgets import QButtonGroup, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QScrollArea, QSpinBox, QVBoxLayout, QWidget
from app.config import check_game_window_aspect_for_start
from app.ui.qt._constants import ATTACK_STRATEGIES, BUILDER_BASE_ATTACK_STRATEGIES, BUILDER_BASE_ATTACK_STRATEGIES_UNDER_DEV, BUILDER_BASE_PRIORITISE_LABELS
from app.ui.qt.bot_controller import BotController
from app.ui.qt.dialogs import RankedAttackConfirmDialog, show_bb_prioritise_help, show_error, show_under_development
from app.ui.qt.theme import SPACING, TOKENS
from app.ui.qt.widgets import Card, HelpButton, PageTitle, SectionTitle, StepperButton, ToggleSwitch, chip_button, danger_button, link_button, primary_button, segment_button
from app.utils.player_list_store import PlayerEntry, load_players

class RunPage(QWidget):
    _STRATEGY_LABELS = [
        'Valkyries',
        'Sneaky Goblins',
        'Super Minions',
        'Edrags']
    _VILLAGE_LABELS = [
        'Home Village',
        'Builder Base']
    _AUTO_UPGRADE_LABELS = [
        ('Off', 'off'),
        ('Dry run', 'dry'),
        ('Maxer', 'maxer'),
        ('Rusher', 'rusher')]

    def __init__(self, controller, navigate_to, parent = None):
        super().__init__(parent)
        self._controller = controller
        self._navigate_to = navigate_to
        self._settings = QSettings(APP_NAME, 'UI')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACING['lg'], SPACING['lg'], SPACING['lg'], SPACING['lg'])
        outer.setSpacing(SPACING['md'])
        # Title row: Start / Stop stay visible at the top right, outside the scroll.
        header = QHBoxLayout()
        header.setSpacing(SPACING['sm'])
        header.addWidget(PageTitle('Run'))
        header.addStretch()
        header.addWidget(self._build_controls())
        outer.addLayout(header)
        outer.addWidget(self._build_village_selector())
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(SPACING['md'])
        self._attack_card = self._build_attack_card()
        layout.addWidget(self._attack_card)
        self._bb_attack_card = self._build_bb_attack_card()
        layout.addWidget(self._bb_attack_card)
        layout.addWidget(self._build_schedule_card())
        self._modes_card = self._build_modes_card()
        layout.addWidget(self._modes_card)
        self._bb_modes_card = self._build_bb_modes_card()
        layout.addWidget(self._bb_modes_card)
        # Live status and Last session side by side, each half the row.
        status_row = QHBoxLayout()
        status_row.setSpacing(SPACING['md'])
        self._status_card = self._build_status_card()
        self._last_session_card = self._build_last_session_card()
        self._bb_last_session_card = self._build_bb_last_session_card()
        status_row.addWidget(self._status_card, 1)
        status_row.addWidget(self._last_session_card, 1)
        status_row.addWidget(self._bb_last_session_card, 1)
        layout.addLayout(status_row)
        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self._apply_village_ui()
        self._restore_choices()
        self._controller.botStarted.connect(self._on_bot_started)
        self._controller.botFinished.connect(self._on_bot_finished_ui)
        self._controller.runningChanged.connect(self._on_running_changed)
        self._controller.stateChanged.connect(self._on_state_changed)
        self._controller.lootChanged.connect(self._on_loot_changed)
        self._controller.statusChanged.connect(self._on_status_line)
        self._controller.runSummary.connect(self._on_run_summary)
        self._load_last_session()

    
    def _build_village_selector(self):
        wrapper = QWidget()
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self._village_group = QButtonGroup(self)
        self._village_group.setExclusive(True)
        for i, label in enumerate(self._VILLAGE_LABELS):
            btn = segment_button(label, parent = wrapper)
            if label == 'Home Village':
                btn.setChecked(True)
            self._village_group.addButton(btn, i)
            row.addWidget(btn)
        row.addStretch()
        self._village_group.idClicked.connect(self._on_village_changed)
        return wrapper

    
    def _is_builder_base(self):
        btn = self._village_group.checkedButton()
        return btn is not None and btn.text() == 'Builder Base'

    
    def _on_village_changed(self, _button_id):
        self._apply_village_ui()

    
    def _apply_village_ui(self):
        builder_base = self._is_builder_base()
        self._attack_card.setVisible(not builder_base)
        self._modes_card.setVisible(not builder_base)
        self._bb_attack_card.setVisible(builder_base)
        self._bb_modes_card.setVisible(builder_base)
        self._last_session_card.setVisible(not builder_base)
        self._bb_last_session_card.setVisible(builder_base)
        # Same "Run until maxed" switch for both villages; the hint says what it does here.
        self._until_hint.setText(self._UNTIL_HINT_BB if builder_base else self._UNTIL_HINT_HOME)

    
    def _build_attack_card(self):
        card = Card()
        card.card_layout.addWidget(SectionTitle('Attack Strategy'))
        row = QHBoxLayout()
        self._strategy_group = QButtonGroup(self)
        self._strategy_group.setExclusive(True)
        for i, label in enumerate(self._STRATEGY_LABELS):
            btn = segment_button(label, parent = card)
            if label == 'Valkyries':
                btn.setChecked(True)
            self._strategy_group.addButton(btn, i)
            row.addWidget(btn)
        card.card_layout.addLayout(row)
        return card

    
    def _build_bb_attack_card(self):
        card = Card()
        card.card_layout.addWidget(SectionTitle('Attack Strategy'))
        row = QHBoxLayout()
        self._bb_strategy_group = QButtonGroup(self)
        self._bb_strategy_group.setExclusive(True)
        for i, label in enumerate(BUILDER_BASE_ATTACK_STRATEGIES):
            btn = segment_button(label, parent = card)
            if label == 'Baby Dragon':
                btn.setChecked(True)
            self._bb_strategy_group.addButton(btn, i)
            row.addWidget(btn)
        for label in BUILDER_BASE_ATTACK_STRATEGIES_UNDER_DEV:
            btn = segment_button(label, parent = card, under_development = True)
            btn.clicked.connect((lambda _checked = False: show_under_development(self.window())))
            row.addWidget(btn)
        row.addStretch()
        card.card_layout.addLayout(row)
        return card

    
    _UNTIL_HINT_HOME = 'Farms, upgrades, and idles in a loop until you press Stop. When storages are full and nothing can be started, the bot waits and rechecks every 5 minutes instead of attacking for nothing.'
    _UNTIL_HINT_BB = 'Builder Base: attacks (and upgrades walls, if on) in a loop until you press Stop — no time limit.'

    def _build_schedule_card(self):
        card = Card()
        card.card_layout.addWidget(SectionTitle('Schedule'))
        self._star_bonus = ToggleSwitch('Star Bonus', parent = card)
        self._star_bonus.toggled.connect(self._on_star_bonus_toggle)
        card.card_layout.addWidget(self._star_bonus)
        self._until_maxed = ToggleSwitch('Run until maxed (no time limit)', parent = card)
        self._until_maxed.toggled.connect(self._on_until_maxed_toggle)
        card.card_layout.addWidget(self._until_maxed)
        self._until_hint = QLabel(self._UNTIL_HINT_HOME)
        self._until_hint.setWordWrap(True)
        self._until_hint.setStyleSheet(f'''color: {TOKENS['text_muted']}; font-size: 12px;''')
        card.card_layout.addWidget(self._until_hint)
        dur_row = QHBoxLayout()
        self._duration_label = SectionTitle('Duration')
        dur_row.addWidget(self._duration_label)
        self._minutes_spin = QSpinBox()
        self._minutes_spin.setObjectName('DurationSpin')
        # Built-in arrows hidden by the theme (QSpinBox#DurationSpin::up-button), NOT by
        # setButtonSymbols(NoButtons) — that collapses the text field to 1 px on Windows.
        self._minutes_spin.setRange(1, 999)
        self._minutes_spin.setValue(15)
        self._minutes_spin.setFixedSize(56, 28)
        self._minutes_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        step_col = QVBoxLayout()
        step_col.setSpacing(2)
        step_col.setContentsMargins(0, 0, 0, 0)
        self._btn_spin_up = StepperButton(up = True, parent = card)
        self._btn_spin_up.clicked.connect((lambda : self._step_minutes(1)))
        self._btn_spin_down = StepperButton(up = False, parent = card)
        self._btn_spin_down.clicked.connect((lambda : self._step_minutes(-1)))
        step_col.addWidget(self._btn_spin_up)
        step_col.addWidget(self._btn_spin_down)
        self._minutes_unit = QLabel('minutes')
        self._minutes_unit.setObjectName('DurationUnit')
        self._minutes_unit.setStyleSheet(f'''color: {TOKENS['text_muted']};''')
        spin_group = QHBoxLayout()
        spin_group.setSpacing(4)
        spin_group.addWidget(self._minutes_spin)
        spin_group.addLayout(step_col)
        spin_group.addWidget(self._minutes_unit)
        spin_group.addStretch()
        dur_row.addLayout(spin_group)
        dur_row.addStretch()
        card.card_layout.addLayout(dur_row)
        preset_row = QHBoxLayout()
        self._btn_5m = chip_button('5m', parent = card)
        self._btn_5m.clicked.connect((lambda : self._set_minutes(5)))
        preset_row.addWidget(self._btn_5m)
        self._btn_10m = chip_button('10m', parent = card)
        self._btn_10m.clicked.connect((lambda : self._set_minutes(10)))
        preset_row.addWidget(self._btn_10m)
        self._btn_20m = chip_button('20m', parent = card)
        self._btn_20m.clicked.connect((lambda : self._set_minutes(20)))
        preset_row.addWidget(self._btn_20m)
        preset_row.addStretch()
        card.card_layout.addLayout(preset_row)
        self._on_star_bonus_toggle(self._star_bonus.isChecked())
        return card

    
    def _build_modes_card(self):
        card = Card()
        card.card_layout.addWidget(SectionTitle('Modes'))
        upg_row = QHBoxLayout()
        upg_row.addWidget(SectionTitle('Auto upgrade'))
        upg_row.addSpacing(SPACING['xs'])
        self._auto_upgrade_group = QButtonGroup(self)
        self._auto_upgrade_group.setExclusive(True)
        for i, (label, _key) in enumerate(self._AUTO_UPGRADE_LABELS):
            btn = segment_button(label, parent = card)
            if label == 'Off':
                btn.setChecked(True)
            self._auto_upgrade_group.addButton(btn, i)
            upg_row.addWidget(btn)
        upg_row.addStretch()
        card.card_layout.addLayout(upg_row)
        upg_hint = QLabel('Maxer starts the cheapest affordable upgrade with your loot (never the Town Hall); Rusher grabs the Town Hall the moment it is affordable. Dry run only logs what it would start. Works at any Town Hall level. Reserve builders for walls in Settings.')
        upg_hint.setWordWrap(True)
        upg_hint.setStyleSheet(f'''color: {TOKENS['text_muted']}; font-size: 12px;''')
        card.card_layout.addWidget(upg_hint)
        self._ranked = ToggleSwitch('Ranked attack fill', parent = card, danger = True)
        card.card_layout.addWidget(self._ranked)
        self._upgrade_walls = ToggleSwitch('Upgrade walls', parent = card)
        card.card_layout.addWidget(self._upgrade_walls)
        mr_row = QHBoxLayout()
        self._multi_run = ToggleSwitch('Multi-run', parent = card)
        mr_row.addWidget(self._multi_run)
        mr_row.addStretch()
        edit_players = link_button('Edit player list ›', parent = card)
        edit_players.clicked.connect((lambda : self._navigate_to('players')))
        mr_row.addWidget(edit_players)
        card.card_layout.addLayout(mr_row)
        return card

    
    def _build_bb_modes_card(self):
        card = Card()
        card.card_layout.addWidget(SectionTitle('Modes'))
        prior_row = QHBoxLayout()
        prior_row.addWidget(SectionTitle('Prioritise'))
        prior_help = HelpButton((lambda : show_bb_prioritise_help(self.window())), parent = card)
        prior_row.addWidget(prior_help, alignment = Qt.AlignmentFlag.AlignVCenter)
        prior_row.addSpacing(SPACING['xs'])
        self._bb_prioritise_group = QButtonGroup(self)
        self._bb_prioritise_group.setExclusive(True)
        for i, label in enumerate(BUILDER_BASE_PRIORITISE_LABELS):
            btn = segment_button(label, parent = card)
            if label == 'Both':
                btn.setChecked(True)
            self._bb_prioritise_group.addButton(btn, i)
            prior_row.addWidget(btn)
        prior_row.addStretch()
        card.card_layout.addLayout(prior_row)
        self._bb_upgrade_walls = ToggleSwitch('Upgrade walls', parent = card)
        card.card_layout.addWidget(self._bb_upgrade_walls)
        mr_row = QHBoxLayout()
        self._bb_multi_run = ToggleSwitch('Multi-run', parent = card, under_development = True)
        mr_row.addWidget(self._bb_multi_run)
        mr_row.addStretch()
        edit_players = link_button('Edit player list ›', parent = card)
        edit_players.setEnabled(False)
        edit_players.setToolTip('Builder Base multi-run is under development')
        mr_row.addWidget(edit_players)
        card.card_layout.addLayout(mr_row)
        return card

    
    @staticmethod
    def _stat_card(title):
        """A status-styled card with a grid of TITLE / value pairs; returns
        (card, add) where ``add(row, col, label)`` places one pair and returns its value label."""
        card = Card()
        card.card_layout.addWidget(SectionTitle(title))
        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACING['lg'])
        grid.setVerticalSpacing(4)

        def add(row, col, label):
            t = QLabel(label.upper())
            t.setObjectName('StatTitle')
            font = t.font()
            font.setLetterSpacing(font.SpacingType.PercentageSpacing, 110)
            t.setFont(font)
            v = QLabel('—')
            v.setObjectName('StatValue')
            # Word-wrap keeps a long readout from inflating the card's minimum width
            # past the viewport (clipped every card's right edge).
            v.setWordWrap(True)
            grid.addWidget(t, row * 2, col)
            grid.addWidget(v, row * 2 + 1, col)
            grid.setColumnStretch(col, 1)
            return v

        card.card_layout.addLayout(grid)
        return (card, add)

    def _build_status_card(self):
        (card, stat) = self._stat_card('Live status')
        self._stat_state = stat(0, 0, 'State')
        self._stat_runtime = stat(0, 1, 'Run time')
        self._stat_loot = stat(1, 0, 'Loot this session')
        self._stat_loot_rate = stat(1, 1, 'Loot / hour')
        self._stat_note = QLabel('Start the bot to see the live state here.')
        self._stat_note.setWordWrap(True)
        self._stat_note.setStyleSheet(f"color: {TOKENS['text_muted']};")
        card.card_layout.addWidget(self._stat_note)
        # Run time ticks once a second while the bot runs and freezes on the final
        # value when the run ends.
        self._run_started_at = None
        self._runtime_timer = QTimer(self)
        self._runtime_timer.setInterval(1000)
        self._runtime_timer.timeout.connect(self._tick_runtime)
        return card

    def _build_last_session_card(self):
        (card, stat) = self._stat_card('Last session')
        self._last_gold = stat(0, 0, 'Gold')
        self._last_elixir = stat(0, 1, 'Elixir')
        self._last_walls = stat(1, 0, 'Walls upgraded')
        self._last_attacks = stat(1, 1, 'Attacks')
        self._last_duration = stat(2, 0, 'Duration')
        self._last_note = QLabel('Filled in when a run ends.')
        self._last_note.setWordWrap(True)
        self._last_note.setStyleSheet(f"color: {TOKENS['text_muted']};")
        card.card_layout.addWidget(self._last_note)
        return card

    def _build_bb_last_session_card(self):
        '''Builder Base runs: shown in place of "Last session" while Builder Base is selected.'''
        (card, stat) = self._stat_card('Last session — Builder Base')
        self._bb_last_attacks = stat(0, 0, 'Attacks')
        self._bb_last_walls = stat(0, 1, 'Walls upgraded')
        self._bb_last_duration = stat(1, 0, 'Duration')
        self._bb_last_note = QLabel('Filled in when a Builder Base run ends.')
        self._bb_last_note.setWordWrap(True)
        self._bb_last_note.setStyleSheet(f"color: {TOKENS['text_muted']};")
        card.card_layout.addWidget(self._bb_last_note)
        return card

    @staticmethod
    def _fmt_duration(seconds):
        seconds = max(0, int(seconds))
        return f'{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}'

    def _tick_runtime(self):
        if self._run_started_at is not None:
            self._stat_runtime.setText(self._fmt_duration(time.monotonic() - self._run_started_at))

    def _show_last_session(self, stats):
        self._last_gold.setText(f"{int(stats.get('gold', 0)):,}")
        self._last_elixir.setText(f"{int(stats.get('elixir', 0)):,}")
        self._last_walls.setText(str(int(stats.get('walls', 0))))
        self._last_attacks.setText(str(int(stats.get('attacks', 0))))
        self._last_duration.setText(self._fmt_duration(stats.get('duration_s', 0)))
        ended = stats.get('ended')
        self._last_note.setText(f'Ended {ended}' if ended else '')

    def _show_bb_last_session(self, stats):
        self._bb_last_attacks.setText(str(int(stats.get('attacks', 0))))
        self._bb_last_walls.setText(str(int(stats.get('walls', 0))))
        self._bb_last_duration.setText(self._fmt_duration(stats.get('duration_s', 0)))
        ended = stats.get('ended')
        self._bb_last_note.setText(f'Ended {ended}' if ended else '')

    def _on_run_summary(self, stats):
        """End of a run: refresh the Last session card and keep it across app restarts."""
        stats = dict(stats)
        stats['ended'] = datetime.now().strftime('%d/%m %H:%M')
        builder = stats.get('village') == 'builder'
        (self._show_bb_last_session if builder else self._show_last_session)(stats)
        try:
            self._settings.setValue('run/lastSessionBB' if builder else 'run/lastSession', json.dumps(stats))
        except Exception:
            pass

    def _load_last_session(self):
        try:
            raw = self._settings.value('run/lastSession', '', type = str)
            if raw:
                self._show_last_session(json.loads(raw))
        except Exception:
            pass
        try:
            raw = self._settings.value('run/lastSessionBB', '', type = str)
            if raw:
                self._show_bb_last_session(json.loads(raw))
        except Exception:
            pass

    @staticmethod
    def _fmt_amount(value):
        value = int(value)
        if value >= 1000000:
            return f'''{value / 1000000:.1f}M'''
        if value >= 10000:
            return f'''{value / 1000:.0f}k'''
        return str(value)

    _STATE_COLORS = {
        'farming': TOKENS['success'],  # engaged green
        'idling': TOKENS['warning'],   # holding amber
    }

    def _on_state_changed(self, payload):
        state = payload.get('state')
        if state:
            self._stat_state.setText(str(state).upper())
            color = self._STATE_COLORS.get(str(state).lower(), TOKENS['text'])
            self._stat_state.setStyleSheet(f'''color: {color};''')
        note = payload.get('note')
        if note:
            self._stat_note.setText(f'''Upgrades: {note}''')

    def _on_loot_changed(self, gold, elixir, dark, elapsed):
        self._stat_loot.setText(f'''{self._fmt_amount(gold)} / {self._fmt_amount(elixir)} / {self._fmt_amount(dark)}''')
        if elapsed < 600:
            # A per-hour figure extrapolated from a few minutes is noise — hold it back.
            self._stat_loot_rate.setText('— (needs 10m)')
            return None
        hours = elapsed / 3600
        self._stat_loot_rate.setText(f'''{self._fmt_amount(gold / hours)} / {self._fmt_amount(elixir / hours)} / {self._fmt_amount(dark / hours)}''')

    def _on_status_line(self, msg, _warning):
        if msg.lower().startswith(('idling', 'resuming')):
            idling = msg.lower().startswith('idling')
            self._stat_state.setText('IDLING' if idling else 'FARMING')
            self._stat_state.setStyleSheet(f'''color: {self._STATE_COLORS['idling' if idling else 'farming']};''')
            self._stat_note.setText(msg)

    def _confirm_bb_elixir_prioritise(self):
        reply = QMessageBox.warning(self.window(), 'Elixir priority', 'Prioritising Elixir will deplete your trophies.\n\nDo you want to continue?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        return reply == QMessageBox.StandardButton.Yes

    
    def _build_controls(self):
        wrapper = QWidget()
        btn_row = QHBoxLayout(wrapper)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(SPACING['sm'])
        self._btn_start = primary_button('Start', parent = wrapper)
        self._btn_start.setObjectName('RunAction')
        self._btn_start.setMinimumWidth(110)
        self._btn_start.clicked.connect(self.start_bot)
        btn_row.addWidget(self._btn_start)
        self._btn_stop = danger_button('Stop', parent = wrapper)
        self._btn_stop.setObjectName('RunAction')
        self._btn_stop.setMinimumWidth(110)
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._controller.stop)
        btn_row.addWidget(self._btn_stop)
        return wrapper

    
    def _clear_minutes_selection(self):
        editor = self._minutes_spin.lineEdit()
        if not editor is None:
            editor.deselect()
            editor.setCursorPosition(len(editor.text()))
            return None

    
    def _duration_locked(self):
        return self._star_bonus.isChecked() or self._until_maxed.isChecked()

    def _step_minutes(self, delta):
        if self._duration_locked():
            return None
        if delta > 0:
            self._minutes_spin.stepUp()
        else:
            self._minutes_spin.stepDown()
        self._clear_minutes_selection()
        QTimer.singleShot(0, self._clear_minutes_selection)


    def _set_minutes(self, value):
        if self._duration_locked():
            return None
        self._minutes_spin.setValue(value)
        self._clear_minutes_selection()


    def _update_duration_enabled(self):
        enabled = not self._duration_locked()
        duration_widgets = (self._duration_label, self._minutes_spin, self._btn_spin_up, self._btn_spin_down, self._minutes_unit, self._btn_5m, self._btn_10m, self._btn_20m)
        for widget in duration_widgets:
            widget.setEnabled(enabled)
        if enabled:
            self._minutes_unit.setStyleSheet(f'''color: {TOKENS['text_muted']};''')
            return None
        self._minutes_unit.setStyleSheet(f'''color: {TOKENS['text_faint']};''')

    def _on_star_bonus_toggle(self, checked):
        if checked and getattr(self, '_until_maxed', None) is not None and self._until_maxed.isChecked():
            self._until_maxed.setChecked(False)
        self._update_duration_enabled()

    def _on_until_maxed_toggle(self, checked):
        if checked and self._star_bonus.isChecked():
            self._star_bonus.setChecked(False)
        self._update_duration_enabled()

    
    def _get_method(self):
        if self._is_builder_base():
            btn = self._bb_strategy_group.checkedButton()
            if btn is None:
                return BUILDER_BASE_ATTACK_STRATEGIES['Baby Dragon']
            return BUILDER_BASE_ATTACK_STRATEGIES.get(btn.text(), 5)
        btn = self._strategy_group.checkedButton()
        if btn is None:
            return ATTACK_STRATEGIES['Valkyries']
        return ATTACK_STRATEGIES.get(btn.text(), 1)

    
    def _get_bb_prioritise(self):
        btn = self._bb_prioritise_group.checkedButton()
        if btn is None:
            return 'both'
        return btn.text().lower()


    def _get_auto_upgrade_mode(self):
        checked_id = self._auto_upgrade_group.checkedId()
        if 0 <= checked_id < len(self._AUTO_UPGRADE_LABELS):
            return self._AUTO_UPGRADE_LABELS[checked_id][1]
        return 'off'

    def _set_auto_upgrade_mode(self, mode):
        for i, (_label, key) in enumerate(self._AUTO_UPGRADE_LABELS):
            if key == mode:
                btn = self._auto_upgrade_group.button(i)
                if btn is not None:
                    btn.setChecked(True)
                return None

    @staticmethod
    def _check_by_text(group, text):
        '''Check the button of ``group`` labelled ``text``; False when there is none.'''
        for btn in group.buttons():
            if btn.text() == text:
                btn.setChecked(True)
                return True
        return False

    @staticmethod
    def _checked_text(group):
        btn = group.checkedButton()
        return '' if btn is None else btn.text()

    def _restore_choices(self):
        '''Bring back the last run's choices across app starts: village, army, Builder Base
        mode, toggles and duration (saved when Start is pressed).'''
        self._check_by_text(self._village_group, str(self._settings.value('run/village', 'Home Village')))
        self._apply_village_ui()
        self._check_by_text(self._strategy_group, str(self._settings.value('run/strategy', 'Valkyries')))
        self._check_by_text(self._bb_strategy_group, str(self._settings.value('run/bbStrategy', 'Baby Dragon')))
        self._check_by_text(self._bb_prioritise_group, str(self._settings.value('run/bbPrioritise', 'Both')))
        self._ranked.setChecked(self._settings.value('run/ranked', False, type = bool))
        self._multi_run.setChecked(self._settings.value('run/multiRun', False, type = bool))
        self._set_auto_upgrade_mode(str(self._settings.value('run/autoUpgrade', 'off')))
        self._upgrade_walls.setChecked(self._settings.value('run/upgradeWalls', False, type = bool))
        self._bb_upgrade_walls.setChecked(self._settings.value('run/bbUpgradeWalls', False, type = bool))
        self._until_maxed.setChecked(self._settings.value('run/untilMaxed', False, type = bool))
        minutes = self._settings.value('run/minutes', 15, type = int)
        if 1 <= minutes <= 999:
            self._minutes_spin.setValue(minutes)
        # After "until maxed": the two switches turn each other off.
        if self._settings.value('run/starBonus', False, type = bool):
            self._star_bonus.setChecked(True)

    def _save_choices(self):
        self._settings.setValue('run/village', self._checked_text(self._village_group))
        self._settings.setValue('run/strategy', self._checked_text(self._strategy_group))
        self._settings.setValue('run/bbStrategy', self._checked_text(self._bb_strategy_group))
        self._settings.setValue('run/bbPrioritise', self._checked_text(self._bb_prioritise_group))
        self._settings.setValue('run/starBonus', self._star_bonus.isChecked())
        self._settings.setValue('run/ranked', self._ranked.isChecked())
        self._settings.setValue('run/multiRun', self._multi_run.isChecked())
        self._settings.setValue('run/autoUpgrade', self._get_auto_upgrade_mode())
        self._settings.setValue('run/upgradeWalls', self._upgrade_walls.isChecked())
        self._settings.setValue('run/bbUpgradeWalls', self._bb_upgrade_walls.isChecked())
        self._settings.setValue('run/untilMaxed', self._until_maxed.isChecked())
        self._settings.setValue('run/minutes', self._minutes_spin.value())

    
    def _get_minutes(self):
        return self._minutes_spin.value()

    
    def _multi_run_players_for_start(self):
        if self._is_builder_base() or not self._multi_run.isChecked():  # [recovered: decompiler inverted both halves — multi-run never engaged on Home Village]
            return None
        players = load_players()
        if not any([ p.enabled and p.name.strip() for p in players ]):
            return []
        return players

    
    def start_bot(self):
        if self._controller.is_running():
            return None
        if not check_game_window_aspect_for_start(parent = self.window(), on_configure = (lambda : self._navigate_to('settings'))):
            return None
        builder_base = self._is_builder_base()
        method = self._get_method()
        multi_arg = self._multi_run_players_for_start()
        if not builder_base and self._multi_run.isChecked() and not multi_arg:  # [recovered: decompiler dropped the `not` — the error fired when players DID exist]
            show_error(self.window(), 'Multi-run', 'Enable at least one player with Run and a non-empty name.\nOpen Player list… to edit.')
            return None
        star_bonus = self._star_bonus.isChecked()
        # "Run until maxed" = unlimited duration; single runs (either village) only.
        until_maxed = (not star_bonus and multi_arg is None
                       and self._until_maxed.isChecked())
        if star_bonus:
            mins = 5
        elif until_maxed:
            mins = 0
        else:
            mins = self._get_minutes()
            if mins <= 0 or mins > 999:
                show_error(self.window(), 'Error', 'Invalid time duration. Enter 1-999 minutes.')
                return None
        ranked_fill = False if builder_base else self._ranked.isChecked()
        if ranked_fill:
            confirm_mins = self._get_minutes()
            if not RankedAttackConfirmDialog.ask(self.window(), confirm_mins):
                return None
        if builder_base and self._get_bb_prioritise() == 'elixir' and not self._confirm_bb_elixir_prioritise():  # [recovered: decompiler inverted both conditions]
            return None
        self._save_choices()
        self._controller.start(method = method, minutes = mins, star_bonus = star_bonus, ranked_fill = ranked_fill, upgrade_walls = self._bb_upgrade_walls.isChecked() if builder_base else self._upgrade_walls.isChecked(), multi_run_players = multi_arg, builder_base = builder_base, loot_prioritise = self._get_bb_prioritise() if builder_base else 'both', auto_upgrade = 'off' if builder_base else self._get_auto_upgrade_mode())

    
    def is_star_bonus_enabled(self):
        return self._star_bonus.isChecked()

    
    def request_start_from_taskbar(self):
        if not self._controller.is_running():
            self.start_bot()
            return None


    def apply_autostart(self, minutes, upgrade_walls, auto_upgrade = 'off', builder_base = False):
        '''CLI ``--autostart``: run with the given duration (``0`` = run until maxed),
        wall toggle, and auto-upgrade mode (off|dry|maxer|rusher); ``builder_base``
        selects the Builder Base (its own wall toggle; auto-upgrade is Home only).'''
        if self._controller.is_running():
            return None
        target = 'Builder Base' if builder_base else 'Home Village'
        for btn in self._village_group.buttons():
            if btn.text() == target:
                btn.setChecked(True)
        self._apply_village_ui()
        self._star_bonus.setChecked(False)
        self._until_maxed.setChecked(minutes <= 0)
        if minutes > 0:
            self._minutes_spin.setValue(minutes)
        if builder_base:
            self._bb_upgrade_walls.setChecked(bool(upgrade_walls))
        else:
            self._upgrade_walls.setChecked(bool(upgrade_walls))
            self._set_auto_upgrade_mode(auto_upgrade)
        self.start_bot()

    
    def request_stop_from_taskbar(self):
        if self._controller.is_running():
            self._controller.stop()
            return None

    
    def _on_bot_started(self):
        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._run_started_at = time.monotonic()
        self._stat_runtime.setText(self._fmt_duration(0))
        self._runtime_timer.start()

    
    def _on_bot_finished_ui(self, _error):
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._tick_runtime()  # the final value stays on screen
        self._runtime_timer.stop()
        self._run_started_at = None

    
    def _on_running_changed(self, running):
        self._btn_start.setEnabled(not running)
        self._btn_stop.setEnabled(running)


