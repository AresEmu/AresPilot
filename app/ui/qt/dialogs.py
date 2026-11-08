'''Modal dialogs for the Qt UI.'''
from __future__ import annotations
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout
from app.ui.qt.theme import SPACING, TOKENS
from app.ui.qt.widgets import danger_button, neutral_button

def show_error(parent, title, message):
    QMessageBox.critical(parent, title, message)


DISCLAIMER_VERSION = 1
DISCLAIMER_TEXT = (
    'AresPilot is a personal, educational project about computer vision and desktop UI '
    'automation.\n\n'
    "Automating Clash of Clans violates Supercell's Terms of Service and can get an account "
    'permanently banned. The author does not condone cheating and does not approve of using '
    'this software to play the game, for any reason.\n\n'
    'AresPilot is not affiliated with, endorsed by or connected to Supercell. Clash of Clans '
    'is a trademark of Supercell Oy.\n\n'
    'If you continue, you do so on your own initiative and at your own risk, and you alone '
    'are responsible for the consequences. The software comes with no warranty.')


def accept_disclaimer(parent = None):
    '''First-start disclaimer: True only when the user explicitly accepts it.'''
    box = QMessageBox(parent)
    box.setWindowTitle('Disclaimer')
    box.setIcon(QMessageBox.Icon.Warning)
    box.setText('Please read before continuing')
    box.setInformativeText(DISCLAIMER_TEXT)
    accept = box.addButton('I understand and accept', QMessageBox.ButtonRole.AcceptRole)
    box.addButton('Exit', QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is accept


def show_under_development(parent):
    QMessageBox.information(parent, 'Under development', 'This feature is under development.')


def show_bb_prioritise_help(parent):
    QMessageBox.information(parent, 'Prioritise loot', 'Choose what the bot optimises for after each attack:\n\n• Gold — waits until 2 stars, then ends the battle.\n• Both — waits until 1 star, then ends the battle.\n• Elixir — surrenders immediately after deploying troops.\n• Trophy — never ends the battle early: plays stage 1 to 100%, then attacks the second village (stage 2) with the troops left, and waits for the battle to finish.')


class RankedAttackConfirmDialog(QDialog):

    def __init__(self, parent, minutes):
        super().__init__(parent)
        self.setWindowTitle('Ranked attack fill')
        self.setModal(True)
        self._remaining = 5
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick_countdown)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING['lg'], SPACING['lg'], SPACING['lg'], SPACING['lg'])
        msg = f'''The bot will use up your ranked attacks up to {minutes} minutes, are you sure you want to continue?'''
        label = QLabel(msg)
        label.setWordWrap(True)
        label.setStyleSheet(f'''color: {TOKENS['text']};''')
        layout.addWidget(label)
        row = QHBoxLayout()
        row.addStretch()
        self._btn_no = neutral_button('No', parent = self)
        self._btn_no.clicked.connect(self.reject)
        row.addWidget(self._btn_no)
        self._btn_yes = danger_button('Yes (5)', parent = self)
        self._btn_yes.setEnabled(False)
        self._btn_yes.clicked.connect(self.accept)
        row.addWidget(self._btn_yes)
        layout.addLayout(row)
        self._tick_countdown()
        self._timer.start()


    def _tick_countdown(self):
        if self._remaining > 0:
            self._btn_yes.setText(f'''Yes ({self._remaining})''')
            self._btn_yes.setEnabled(False)
            self._remaining -= 1
            return None
        self._timer.stop()
        self._btn_yes.setText('Yes')
        self._btn_yes.setEnabled(True)


    @classmethod
    def ask(cls, parent, minutes):
        dlg = cls(parent, minutes)
        return dlg.exec() == QDialog.Accepted
