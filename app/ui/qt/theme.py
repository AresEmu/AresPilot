'''AresPilot theme: pure-black, Apple-style QSS for the PySide6 UI.

Design (macOS dark / iOS grouped lists): true-black canvas, #1C1C1E grouped cards with
no borders, one BLUE accent (#0A84FF) for selection and the main action, green and
amber only for live state, red only for Stop/destructive. Segoe UI Variable / Inter on
Windows stand in for SF Pro; monospace stays for the log view.
'''
from __future__ import annotations
import os
import tempfile
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFontDatabase, QPainter, QPalette, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication

TOKENS = {
    'bg': '#000000',           # true black canvas
    'sidebar': '#0B0B0C',      # sidebar column, a hair above black
    'surface': '#1C1C1E',      # grouped card (Apple secondarySystemBackground)
    'surface_hi': '#2C2C2E',   # inputs, tracks, raised fills
    'border': '#1C1C1E',
    'border_hi': '#38383A',    # separators inside cards
    'text': '#F5F5F7',
    'text_muted': '#98989F',
    'text_faint': '#636366',   # disabled / de-emphasized
    'primary': '#0A84FF',      # system blue
    'primary_hov': '#409CFF',
    'primary_dim': '#0A2540',  # blue-tinted disabled fill
    'primary_tint': 'rgba(10, 132, 255, 0.18)',
    'on_primary': '#FFFFFF',
    'danger': '#FF453A',
    'danger_hov': '#FF6961',
    'success': '#30D158',
    'warning': '#FF9F0A',      # holding / idling amber
    'neutral': '#3A3A3C',
    'neutral_hov': '#48484A',
    'neutral_dark': '#2C2C2E',
    'neutral_dark_hov': '#3A3A3C' }
SPACING = {
    'xs': 4,
    'sm': 8,
    'md': 12,
    'lg': 20,
    'xl': 28 }
RADIUS = 12
SIDEBAR_WIDTH = 196
WINDOW_DEFAULT = (960, 680)
WINDOW_MIN = (760, 540)

_SANS_CANDIDATES = ('SF Pro Text', 'Segoe UI Variable Text', 'Inter', 'Segoe UI')
_MONO_CANDIDATES = ('SF Mono', 'Cascadia Mono', 'Cascadia Code', 'Consolas')
SANS_FONT = 'Segoe UI'
MONO_FONT = 'Consolas'


def _resolve_fonts():
    global SANS_FONT, MONO_FONT
    try:
        families = set(QFontDatabase.families())
    except Exception:
        return
    for name in _SANS_CANDIDATES:
        if name in families:
            SANS_FONT = name
            break
    for name in _MONO_CANDIDATES:
        if name in families:
            MONO_FONT = name
            break


def _arrow_images():
    '''Small chevron PNGs for spin boxes and combo boxes (Qt QSS cannot draw them once the
    sub-controls are restyled). Written to the temp folder; {} before a QApplication exists.'''
    if QApplication.instance() is None:
        return {}
    folder = os.path.join(tempfile.gettempdir(), 'arespilot_ui')
    os.makedirs(folder, exist_ok = True)
    paths = {}
    for (name, up, color) in (('up', True, TOKENS['text']), ('down', False, TOKENS['text']), ('down_off', False, TOKENS['text_faint']), ('up_off', True, TOKENS['text_faint'])):
        pix = QPixmap(20, 12)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        tip = (10, 2) if up else (10, 10)
        base_y = 10 if up else 2
        painter.drawPolygon(QPolygonF([QPointF(*tip), QPointF(4, base_y), QPointF(16, base_y)]))
        painter.end()
        path = os.path.join(folder, f'arrow_{name}.png')
        pix.save(path)
        paths[name] = path.replace(os.sep, '/')
    return paths


def _arrow_rules(t):
    arrows = _arrow_images()
    if not arrows:
        return ''
    return f'''
QSpinBox, QDoubleSpinBox {{
    padding-left: 4px;
    padding-right: 20px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    border: none;
    background: transparent;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    border: none;
    background: transparent;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {t['neutral']};
    border-radius: 4px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url({arrows['up']});
    width: 10px;
    height: 6px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url({arrows['down']});
    width: 10px;
    height: 6px;
}}
QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled {{
    image: url({arrows['up_off']});
}}
QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled {{
    image: url({arrows['down_off']});
}}
QComboBox {{
    padding-right: 26px;
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 26px;
    border: none;
}}
QComboBox::down-arrow {{
    image: url({arrows['down']});
    width: 10px;
    height: 6px;
}}
'''


def build_stylesheet():
    t = TOKENS
    return f'''
QWidget {{
    background-color: {t['bg']};
    color: {t['text']};
    font-family: '{SANS_FONT}';
    font-size: 13px;
}}
QLabel {{
    background-color: transparent;
    padding: 0;
    margin: 0;
}}
QToolTip {{
    background-color: {t['surface_hi']};
    color: {t['text']};
    border: 1px solid {t['border_hi']};
    border-radius: 6px;
    padding: 4px 8px;
}}
QFrame#Card {{
    background-color: {t['surface']};
    border: none;
    border-radius: {RADIUS}px;
}}
QFrame#Card QWidget {{
    background-color: transparent;
}}
QFrame#Card QLineEdit, QFrame#Card QSpinBox, QFrame#Card QDoubleSpinBox, QFrame#Card QComboBox, QFrame#Card QListWidget {{
    background-color: {t['surface_hi']};
}}
QFrame#Card QPushButton[role="primary"] {{
    background-color: {t['primary']};
}}
QFrame#Card QPushButton[role="primary"]:hover {{
    background-color: {t['primary_hov']};
}}
QFrame#Card QPushButton[role="primary"]:disabled {{
    background-color: {t['primary_dim']};
}}
QFrame#Card QPushButton[role="danger"] {{
    background-color: {t['danger']};
}}
QFrame#Card QPushButton[role="danger"]:disabled {{
    background-color: #2A1311;
}}
QFrame#Card QPushButton[role="neutral"], QFrame#Card QPushButton[role="chip"], QFrame#Card QPushButton[role="stepper"] {{
    background-color: {t['neutral_dark']};
}}
QFrame#Card QPushButton[role="neutral"]:hover, QFrame#Card QPushButton[role="chip"]:hover, QFrame#Card QPushButton[role="stepper"]:hover {{
    background-color: {t['neutral_dark_hov']};
}}
QFrame#Card QPushButton[role="chip"]:disabled, QFrame#Card QPushButton[role="stepper"]:disabled {{
    background-color: {t['surface']};
}}
QFrame#Card QPushButton[role="segment"] {{
    background-color: {t['surface_hi']};
}}
QFrame#Card QPushButton[role="segment"]:hover:!checked {{
    background-color: {t['neutral']};
}}
QFrame#Card QPushButton[role="segment"]:checked {{
    background-color: {t['primary']};
}}
QFrame#Card QPushButton[role="segment"][underDevelopment="true"] {{
    background-color: {t['surface']};
}}
QFrame#Separator, QFrame#Card QFrame#Separator {{
    background-color: {t['border_hi']};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}
QLabel#SectionTitle {{
    color: {t['text_muted']};
    font-weight: 600;
    font-size: 11px;
    background-color: transparent;
}}
QLabel#SectionTitle:disabled {{
    color: {t['text_faint']};
}}
QLabel#DurationUnit:disabled {{
    color: {t['text_faint']};
}}
QLabel#PageTitle {{
    font-size: 26px;
    font-weight: 700;
    color: {t['text']};
    background-color: transparent;
}}
QLabel#StatValue {{
    font-size: 17px;
    font-weight: 600;
    color: {t['text']};
    background-color: transparent;
}}
QLabel#StatTitle {{
    color: {t['text_muted']};
    font-size: 10px;
    font-weight: 600;
    background-color: transparent;
}}
QLabel#Brand {{
    font-size: 17px;
    font-weight: 700;
    background-color: transparent;
}}
QLabel#BrandSub {{
    color: {t['text_faint']};
    font-size: 11px;
}}
QPushButton {{
    border: none;
    border-radius: 8px;
    padding: 6px 14px;
    min-height: 28px;
    font-weight: 600;
}}
QPushButton[role="primary"] {{
    background-color: {t['primary']};
    color: {t['on_primary']};
}}
QPushButton[role="primary"]:hover {{
    background-color: {t['primary_hov']};
}}
QPushButton[role="primary"]:disabled {{
    background-color: {t['primary_dim']};
    color: {t['text_faint']};
}}
QPushButton[role="danger"] {{
    background-color: {t['danger']};
    color: #FFFFFF;
}}
QPushButton[role="danger"]:hover {{
    background-color: {t['danger_hov']};
}}
QPushButton[role="danger"]:disabled {{
    background-color: #2A1311;
    color: {t['text_faint']};
}}
QPushButton[role="neutral"] {{
    background-color: {t['neutral_dark']};
    color: {t['text']};
}}
QPushButton[role="neutral"]:hover {{
    background-color: {t['neutral_dark_hov']};
}}
QPushButton[role="neutral"]:disabled {{
    color: {t['text_faint']};
}}
QPushButton#RunAction {{
    border-radius: 18px;
    min-height: 36px;
    max-height: 36px;
    padding: 0 22px;
    font-size: 14px;
}}
QPushButton[role="link"] {{
    background-color: transparent;
    color: {t['primary_hov']};
    padding: 4px 6px;
}}
QPushButton[role="link"]:hover {{
    color: #70B5FF;
}}
QPushButton[role="link"]:disabled {{
    color: {t['text_faint']};
}}
QPushButton[role="chip"] {{
    background-color: {t['neutral_dark']};
    color: {t['text']};
    padding: 3px 12px;
    min-height: 24px;
    border-radius: 12px;
    font-size: 12px;
}}
QPushButton[role="chip"]:hover {{
    background-color: {t['neutral_dark_hov']};
}}
QPushButton[role="chip"]:disabled {{
    background-color: {t['surface']};
    color: {t['text_faint']};
}}
QPushButton[role="segment"] {{
    background-color: {t['surface_hi']};
    color: {t['text_muted']};
    border-radius: 8px;
    padding: 6px 14px;
}}
QPushButton[role="segment"]:hover:!checked {{
    background-color: {t['neutral']};
    color: {t['text']};
}}
QPushButton[role="segment"]:checked {{
    background-color: {t['primary']};
    color: {t['on_primary']};
}}
QPushButton[role="segment"][underDevelopment="true"] {{
    background-color: {t['surface']};
    color: {t['text_faint']};
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {{
    background-color: {t['surface_hi']};
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 5px 10px;
    selection-background-color: {t['primary']};
    selection-color: #FFFFFF;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {t['primary']};
}}
QComboBox QAbstractItemView {{
    background-color: {t['surface_hi']};
    border: 1px solid {t['border_hi']};
    selection-background-color: {t['primary']};
    outline: none;
}}
QSpinBox#DurationSpin {{
    min-height: 28px;
    max-height: 28px;
    padding: 2px 6px;
    font-weight: 600;
}}
/* The duration box has its own stepper buttons beside it. Its built-in arrows are
   hidden HERE (zero width) instead of with setButtonSymbols(NoButtons): on Windows,
   NoButtons + a stylesheet collapses the inner text field to 1 px, so the minutes
   were set but never drawn (live repro: empty Duration box). */
QSpinBox#DurationSpin::up-button, QSpinBox#DurationSpin::down-button {{
    width: 0px;
    border: none;
}}
QSpinBox#DurationSpin::up-arrow, QSpinBox#DurationSpin::down-arrow {{
    width: 0px;
    height: 0px;
}}
QSpinBox:disabled, QDoubleSpinBox:disabled, QSpinBox#DurationSpin:disabled {{
    color: {t['text_faint']};
    background-color: {t['surface']};
}}
QPushButton[role="stepper"] {{
    background-color: {t['neutral_dark']};
    padding: 0;
    min-height: 13px;
    max-height: 13px;
    min-width: 22px;
    max-width: 22px;
    border-radius: 4px;
}}
QPushButton[role="stepper"]:hover {{
    background-color: {t['neutral_dark_hov']};
}}
QPushButton[role="stepper"]:pressed {{
    background-color: {t['neutral_hov']};
}}
QPushButton[role="stepper"]:disabled {{
    background-color: {t['surface']};
}}
QPushButton[role="help"] {{
    background-color: transparent;
    color: {t['text_muted']};
    padding: 0;
    min-height: 18px;
    min-width: 18px;
    max-height: 18px;
    max-width: 18px;
    border-radius: 9px;
    border: 1px solid {t['text_muted']};
    font-size: 11px;
    font-weight: bold;
}}
QPushButton[role="help"]:hover {{
    color: {t['text']};
    border-color: {t['text']};
}}
QPushButton[role="icon"] {{
    background-color: {t['neutral_dark']};
    color: {t['text']};
    padding: 0;
    min-height: 34px;
    min-width: 34px;
    max-height: 34px;
    max-width: 34px;
    border-radius: 8px;
}}
QPushButton[role="icon"]:hover {{
    background-color: {t['neutral_dark_hov']};
}}
QPushButton[role="icon"]:checked {{
    background-color: {t['neutral']};
}}
QWidget#SidebarPanel {{
    background-color: {t['sidebar']};
    border-right: 1px solid {t['surface']};
}}
QListWidget#Sidebar {{
    background-color: transparent;
    border: none;
    padding: 0;
    outline: none;
}}
QListWidget#Sidebar::item {{
    padding: 8px 10px;
    margin: 1px 0;
    border-radius: 8px;
    color: {t['text']};
}}
QListWidget#Sidebar::item:selected {{
    background-color: {t['primary_tint']};
    color: {t['primary_hov']};
    font-weight: 600;
}}
QListWidget#Sidebar::item:hover:!selected {{
    background-color: {t['surface']};
}}
QListWidget#WindowList, QListWidget#WindowInfoList {{
    border: none;
    border-radius: 8px;
    padding: 4px;
    outline: none;
}}
QListWidget#WindowList::item, QListWidget#WindowInfoList::item {{
    padding: 6px 8px;
    border-radius: 6px;
}}
QListWidget#WindowList::item:selected, QListWidget#WindowInfoList::item:selected {{
    background-color: {t['primary_tint']};
    color: {t['text']};
}}
QPlainTextEdit#LogView {{
    background-color: #0B0B0C;
    border: 1px solid {t['surface']};
    border-radius: {RADIUS}px;
    padding: 10px 12px;
    font-family: '{MONO_FONT}';
    font-size: 12px;
}}
QStatusBar {{
    background-color: {t['bg']};
    border-top: 1px solid {t['surface']};
    color: {t['text_muted']};
    font-size: 11px;
}}
QStatusBar::item {{
    border: none;
}}
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {t['neutral']};
    border-radius: 3px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t['neutral_hov']};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
QCheckBox#ToggleSwitch {{
    spacing: 8px;
    background-color: transparent;
}}
QCheckBox#ToggleSwitch::indicator {{
    width: 0;
    height: 0;
    border: none;
}}
QMessageBox, QDialog {{
    background-color: {t['surface']};
}}
QMessageBox QLabel, QDialog QLabel {{
    background-color: transparent;
}}
QMessageBox QPushButton {{
    background-color: {t['neutral']};
    min-width: 72px;
}}
QMessageBox QPushButton:default {{
    background-color: {t['primary']};
}}
''' + _arrow_rules(t)


def apply_theme(app):
    app.setStyle('Fusion')
    _resolve_fonts()
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(TOKENS['bg']))
    pal.setColor(QPalette.Base, QColor(TOKENS['surface_hi']))
    pal.setColor(QPalette.AlternateBase, QColor(TOKENS['surface']))
    pal.setColor(QPalette.Text, QColor(TOKENS['text']))
    pal.setColor(QPalette.WindowText, QColor(TOKENS['text']))
    pal.setColor(QPalette.Button, QColor(TOKENS['surface']))
    pal.setColor(QPalette.ButtonText, QColor(TOKENS['text']))
    pal.setColor(QPalette.ToolTipBase, QColor(TOKENS['surface_hi']))
    pal.setColor(QPalette.ToolTipText, QColor(TOKENS['text']))
    pal.setColor(QPalette.Highlight, QColor(TOKENS['primary']))
    pal.setColor(QPalette.HighlightedText, QColor('#ffffff'))
    app.setPalette(pal)
    app.setStyleSheet(build_stylesheet())


# Back-compat: some call sites import STYLESHEET directly.
STYLESHEET = build_stylesheet()
