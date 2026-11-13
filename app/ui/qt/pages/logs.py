'''Logs page — tail arespilot.log in the UI.'''
from __future__ import annotations
import os
import subprocess
import sys
from typing import Optional
from PySide6.QtCore import QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QVBoxLayout, QWidget
from app.ui.qt.theme import SPACING
from app.ui.qt.widgets import PageTitle, neutral_button
from app.utils.common import get_autoloot_log_path

class LogsPage(QWidget):
    
    def __init__(self, parent = None):
        super().__init__(parent)
        self._pos = 0
        self._tail_timer = QTimer(self)
        self._tail_timer.setInterval(1000)
        self._tail_timer.timeout.connect(self._tail_log)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING['lg'], SPACING['lg'], SPACING['lg'], SPACING['lg'])
        layout.setSpacing(SPACING['md'])
        layout.addWidget(PageTitle('Logs'))
        btn_row = QHBoxLayout()
        open_btn = neutral_button('Open in Explorer')
        open_btn.clicked.connect(self._open_in_explorer)
        btn_row.addWidget(open_btn)
        clear_btn = neutral_button('Clear view')
        clear_btn.clicked.connect(self._clear_view)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(5000)
        self._log_view.setObjectName('LogView')  # monospace + panel look come from the theme
        layout.addWidget(self._log_view, stretch = 1)

    
    # On show only the end of the file is loaded: the view keeps 5000 lines anyway, and
    # re-reading a multi-MB log froze the UI (and appended it all again on every show).
    _SHOW_TAIL_BYTES = 512 * 1024

    def showEvent(self, event):
        super().showEvent(event)
        self._log_view.clear()
        try:
            size = get_autoloot_log_path().stat().st_size
        except OSError:
            size = 0
        self._pos = max(0, size - self._SHOW_TAIL_BYTES)
        self._skip_partial_line = self._pos > 0
        self._tail_log()
        self._tail_timer.start()

    
    def hideEvent(self, event):
        self._tail_timer.stop()
        super().hideEvent(event)

    
    def _tail_log(self):
        path = get_autoloot_log_path()
        
        try:
            path.parent.mkdir(parents = True, exist_ok = True)
            if not path.is_file():
                path.touch()
            if path.stat().st_size < self._pos:
                self._pos = 0  # the log rotated: follow the new file from its start
            with path.open('rb') as fh:
                fh.seek(self._pos)
                chunk = fh.read()
            # Only whole lines: a read in the middle of a write could split a UTF-8 character.
            cut = chunk.rfind(b'\n') + 1
            chunk = chunk[:cut]
            self._pos += cut
            if chunk and getattr(self, '_skip_partial_line', False):
                self._skip_partial_line = False
                chunk = chunk[chunk.find(b'\n') + 1:]
            if chunk:
                text = chunk.decode('utf-8', errors = 'replace')
                self._log_view.moveCursor(QTextCursor.MoveOperation.End)
                self._log_view.insertPlainText(text)
                self._log_view.moveCursor(QTextCursor.MoveOperation.End)
                return None
            return None
        except OSError:
            return None


    
    def _clear_view(self):
        self._log_view.clear()

    
    def _open_in_explorer(self):
        path = get_autoloot_log_path()
        
        try:
            path.parent.mkdir(parents = True, exist_ok = True)
            if not path.is_file():
                path.touch()
            if sys.platform == 'win32':
                os.startfile(path.parent)
                return None
            if sys.platform == 'darwin':
                subprocess.run([
                    'open',
                    str(path.parent)], check = False)
                return None
            subprocess.run([
                'xdg-open',
                str(path.parent)], check = False)
            return None
        except OSError:
            return None



