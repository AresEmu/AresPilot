'''PySide6 GUI entry point.'''
from __future__ import annotations
import sys
from app.utils.common import APP_NAME
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication
from app.ui.qt.branding import apply_app_icon
from app.ui.qt.dialogs import DISCLAIMER_VERSION, accept_disclaimer
from app.ui.qt.main_window import MainWindow
from app.ui.qt.theme import apply_theme

def _parse_autostart(argv):
    '''``--autostart [--minutes N] [--walls] [--upgrades off|dry|maxer|rusher] [--bb]`` →
    (minutes, walls, upgrades, builder_base) or None. ``--minutes 0`` = run until maxed
    (no limit); ``--bb`` = Builder Base run (``--walls`` = Builder Base walls).'''
    if '--autostart' not in argv:
        return None
    minutes = 15
    if '--minutes' in argv:
        try:
            minutes = max(0, min(999, int(argv[argv.index('--minutes') + 1])))
        except (IndexError, ValueError):
            pass
    upgrades = 'off'
    if '--upgrades' in argv:
        try:
            candidate = argv[argv.index('--upgrades') + 1].lower()
            if candidate in ('off', 'dry', 'maxer', 'rusher'):
                upgrades = candidate
        except IndexError:
            pass
    return (minutes, '--walls' in argv, upgrades, '--bb' in argv)


def _disclaimer_accepted():
    '''Show the disclaimer until it is accepted once (again when its text version changes).'''
    settings = QSettings(APP_NAME, 'UI')
    if settings.value('disclaimer/acceptedVersion', 0, type = int) >= DISCLAIMER_VERSION:
        return True
    if not accept_disclaimer():
        return False
    settings.setValue('disclaimer/acceptedVersion', DISCLAIMER_VERSION)
    return True


def run_gui():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    apply_app_icon(app)
    apply_theme(app)
    if not _disclaimer_accepted():
        sys.exit(0)
    window = MainWindow()
    apply_app_icon(window)
    window.show()
    autostart = _parse_autostart(sys.argv[1:])
    if autostart is not None:
        (minutes, walls, upgrades, builder_base) = autostart
        QTimer.singleShot(3000, (lambda : window.autostart_run(minutes, walls, upgrades, builder_base)))
    sys.exit(app.exec())

