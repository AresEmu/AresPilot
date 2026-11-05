'''Reusable Qt widgets for the AresPilot UI.'''
from __future__ import annotations
from collections.abc import Callable
from typing import Optional
from PySide6.QtCore import Qt, QRectF, QSize, QPointF
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QCheckBox, QFrame, QLabel, QPushButton, QVBoxLayout, QWidget
from app.ui.qt.theme import SPACING, TOKENS

class Card(QFrame):
    
    def __init__(self, parent = None):
        super().__init__(parent)
        self.setObjectName('Card')
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 16)
        self._layout.setSpacing(10)

    
    @property
    def card_layout(self):
        return self._layout



class SectionTitle(QLabel):
    '''Instrument-panel micro-label: uppercase + letter-spaced (QSS cannot express
    either, so the widget owns them; color/size stay in the stylesheet).'''

    def __init__(self, text, parent = None):
        super().__init__(text.upper(), parent)
        self.setObjectName('SectionTitle')
        self.setAutoFillBackground(False)
        font = self.font()
        font.setLetterSpacing(font.SpacingType.PercentageSpacing, 108)
        self.setFont(font)



class PageTitle(QLabel):
    
    def __init__(self, text, parent = None):
        super().__init__(text, parent)
        self.setObjectName('PageTitle')



class ToggleSwitch(QCheckBox):
    
    def __init__(self, text = '', *, parent = None, danger = False, under_development = False):
        super().__init__(text, parent)
        self.setObjectName('ToggleSwitch')
        self._danger = danger
        self._under_development = under_development
        self.setFixedHeight(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if under_development:
            self.setChecked(False)
            return None

    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        (track_w, track_h) = (44, 26)
        x0 = 0
        y0 = (self.height() - track_h) // 2
        if self._under_development:
            on_color = QColor(TOKENS['neutral'])
            off_color = QColor(TOKENS['surface_hi'])
            text_color = QColor(TOKENS['text_faint'])
        else:
            on_color = QColor(TOKENS['danger'] if self._danger else TOKENS['primary'])
            off_color = QColor(TOKENS['neutral'])
            text_color = QColor(TOKENS['text'])
        track_color = on_color if self.isChecked() and not self._under_development else off_color
        painter.setPen(Qt.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(x0, y0, track_w, track_h, track_h / 2, track_h / 2)
        knob_d = 22
        knob_x = x0 + track_w - knob_d - 2 if self.isChecked() and not self._under_development else x0 + 2
        knob_y = y0 + (track_h - knob_d) // 2
        painter.setBrush(QColor(TOKENS['text_faint'] if self._under_development else '#ffffff'))
        painter.drawEllipse(knob_x, knob_y, knob_d, knob_d)
        if self.text():
            painter.setPen(text_color)
            font = painter.font()
            painter.setFont(font)
            text_rect = QRectF(track_w + 12, 0, self.width() - track_w - 12, self.height())
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())
            return None

    
    def mousePressEvent(self, event):
        if self._under_development:
            from app.ui.qt.dialogs import show_under_development
            show_under_development(self.window())
            return None
        super().mousePressEvent(event)

    
    def sizeHint(self):
        text_w = self.fontMetrics().horizontalAdvance(self.text()) + 8 if self.text() else 0
        return QSize(44 + text_w + 12, 30)

    
    def hitButton(self, pos):
        return self.rect().contains(pos)



def _styled_button(text, role, parent = None):
    btn = QPushButton(text, parent)
    btn.setProperty('role', role)
    btn.style().unpolish(btn)
    btn.style().polish(btn)
    return btn


def primary_button(text, *, parent = None):
    return _styled_button(text, 'primary', parent)


def danger_button(text, *, parent = None):
    return _styled_button(text, 'danger', parent)


def neutral_button(text, *, parent = None):
    return _styled_button(text, 'neutral', parent)


def chip_button(text, *, parent = None):
    return _styled_button(text, 'chip', parent)


def link_button(text, *, parent = None):
    '''Borderless blue text button ("Edit player list ›").'''
    btn = _styled_button(text, 'link', parent)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def hint_label(text, parent = None):
    '''Small grey explanatory text under a control.'''
    label = QLabel(text, parent)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {TOKENS['text_muted']}; font-size: 12px;")
    return label


class Separator(QFrame):
    '''1 px inset line between rows of a grouped card.'''

    def __init__(self, parent = None):
        super().__init__(parent)
        self.setObjectName('Separator')
        self.setFixedHeight(1)


def segment_button(text, *, parent = None, under_development = False):
    btn = _styled_button(text, 'segment', parent)
    if under_development:
        btn.setCheckable(False)
        btn.setProperty('underDevelopment', True)
    else:
        btn.setCheckable(True)
    btn.style().unpolish(btn)
    btn.style().polish(btn)
    btn.setMinimumWidth(int(btn.sizeHint().width() * 1.1))
    return btn


class StepperButton(QPushButton):
    '''Compact up/down arrow for numeric steppers.'''
    
    def __init__(self, *, up, parent = None):
        super().__init__(parent)
        self._up = up
        self.setProperty('role', 'stepper')
        self.setFixedSize(22, 13)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.style().unpolish(self)
        self.style().polish(self)

    
    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.isEnabled():
            return None
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(TOKENS['text']))
        cx = self.width() / 2
        cy = self.height() / 2
        if self._up:
            points = [
                QPointF(cx, cy - 3),
                QPointF(cx - 4, cy + 2),
                QPointF(cx + 4, cy + 2)]
        else:
            points = [
                QPointF(cx, cy + 3),
                QPointF(cx - 4, cy - 2),
                QPointF(cx + 4, cy - 2)]
        painter.drawPolygon(QPolygonF(points))



class HelpButton(QPushButton):
    '''Compact ? button that opens a help popup when clicked.'''
    
    def __init__(self, on_click, *, parent = None):
        super().__init__('?', parent)
        self.setProperty('role', 'help')
        self.setFixedSize(18, 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip('What does each option do?')
        self.style().unpolish(self)
        self.style().polish(self)
        self.clicked.connect(on_click)



class VisibilityToggleButton(QPushButton):
    '''Minimal line-art eye toggle for password fields.'''
    
    def __init__(self, parent = None):
        super().__init__(parent)
        self.setProperty('role', 'icon')
        self.setCheckable(True)
        self.setFixedSize(34, 34)
        self.setToolTip('Show password')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.style().unpolish(self)
        self.style().polish(self)
        self.toggled.connect((lambda _: self.update()))

    
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(TOKENS['text'])
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        cx = self.width() / 2
        cy = self.height() / 2
        painter.drawEllipse(QRectF(cx - 9, cy - 6, 18, 12))
        if self.isChecked():
            painter.drawLine(int(cx - 8), int(cy + 6), int(cx + 8), int(cy - 6))
            return None
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(cx - 2.5, cy - 2.5, 5, 5))




def _paint_sidebar_glyph(painter, kind, size):
    s = size / 24.0
    if kind == 'run':
        painter.setBrush(painter.pen().color())
        painter.drawPolygon(QPolygonF([QPointF(7 * s, 5 * s), QPointF(19 * s, 12 * s), QPointF(7 * s, 19 * s)]))
    elif kind == 'settings':
        painter.drawEllipse(QPointF(12 * s, 12 * s), 3.2 * s, 3.2 * s)
        painter.drawEllipse(QPointF(12 * s, 12 * s), 8 * s, 8 * s)
        for (x1, y1, x2, y2) in ((12, 1.5, 12, 4), (12, 20, 12, 22.5), (1.5, 12, 4, 12), (20, 12, 22.5, 12)):
            painter.drawLine(QPointF(x1 * s, y1 * s), QPointF(x2 * s, y2 * s))
    elif kind == 'players':
        painter.drawEllipse(QPointF(9 * s, 8 * s), 3.5 * s, 3.5 * s)
        path = QPainterPath()
        path.moveTo(2.5 * s, 20 * s)
        path.cubicTo(2.5 * s, 14 * s, 15.5 * s, 14 * s, 15.5 * s, 20 * s)
        painter.drawPath(path)
        painter.drawArc(int(14 * s), int(4.5 * s), int(7 * s), int(7 * s), -90 * 16, 180 * 16)
        painter.drawLine(QPointF(18 * s, 15 * s), QPointF(21.5 * s, 20 * s))
    elif kind == 'logs':
        painter.drawRoundedRect(QRectF(5 * s, 3 * s, 14 * s, 18 * s), 2.5 * s, 2.5 * s)
        for y in (8.5, 12.5, 16.5):
            painter.drawLine(QPointF(8.5 * s, y * s), QPointF(15.5 * s, y * s))


def sidebar_icon(kind, size = 18):
    """Line-art sidebar glyph (run / settings / players / logs): grey normally, blue when
    the item is selected (QIcon.Selected)."""
    icon = QIcon()
    for (mode, color) in ((QIcon.Mode.Normal, TOKENS['text_muted']), (QIcon.Mode.Selected, TOKENS['primary_hov'])):
        pix = QPixmap(size * 2, size * 2)
        pix.setDevicePixelRatio(2)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color), 1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        _paint_sidebar_glyph(painter, kind, size)
        painter.end()
        icon.addPixmap(pix, mode)
    return icon
