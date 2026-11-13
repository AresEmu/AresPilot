import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

_FORMATTER = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt = '%Y-%m-%d %H:%M:%S')
# One handler per log file, shared by every named logger. A RotatingFileHandler of its
# own per logger kept the same file open many times: on Windows the rename at 5 MB then
# fails (file in use) and from that point every record of the rotating handler is lost.
_FILE_HANDLERS = {}
_CONSOLE_HANDLER = None


def _console_handler():
    global _CONSOLE_HANDLER
    if _CONSOLE_HANDLER is None:
        _CONSOLE_HANDLER = logging.StreamHandler(sys.stdout)
        _CONSOLE_HANDLER.setFormatter(_FORMATTER)
    return _CONSOLE_HANDLER


def _file_handler(log_file):
    handler = _FILE_HANDLERS.get(log_file)
    if handler is None:
        handler = RotatingFileHandler(log_file, mode = 'a', encoding = 'utf-8', maxBytes = 5242880, backupCount = 3)
        handler.setFormatter(_FORMATTER)
        _FILE_HANDLERS[log_file] = handler
    return handler


def setup_logger(name = 'AresPilot', log_file = None, level = logging.INFO):
    '''Configures and returns a logger instance.'''
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if logger.hasHandlers():
        return logger
    logger.addHandler(_console_handler())
    if log_file is None:
        from app.utils.common import get_autoloot_log_path
        log_file = str(get_autoloot_log_path())

    try:
        logger.addHandler(_file_handler(log_file))
        return logger
    except Exception as e:
        print(f'''Failed to set up file logging: {e}''')
        return logger
