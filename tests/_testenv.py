'''Imported first by every test module: sends the test run's log to
%LOCALAPPDATA%\\AresPilot\\test_logs instead of the real arespilot.log. Must run
before any ``app`` import — the logger opens its file on first use.'''
import os
from pathlib import Path

os.environ.setdefault('ARESPILOT_LOG_DIR', str(Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'AresPilot' / 'test_logs'))
