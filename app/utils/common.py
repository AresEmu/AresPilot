import os
import sys
from pathlib import Path

def get_resource_path(relative_path):
    '''Get absolute path to resource, works for dev and for PyInstaller.'''
    
    try:
        base_path = Path(sys._MEIPASS)
        return base_path / relative_path
    except Exception:
        base_path = Path(__file__).resolve().parent.parent.parent
        return base_path / relative_path



APP_NAME = 'AresPilot'
LOG_FILENAME = 'arespilot.log'
# Earlier names of the data dir, newest first: BasePilot (upstream name of this fork) and
# ClashAutoLoot (upstream's pre-rebrand name). Settings are migrated from the first found.
_LEGACY_DATA_DIR_NAMES = ('BasePilot', 'ClashAutoLoot')
_migration_checked = False


def _data_root():
    if sys.platform == 'win32':
        local = os.environ.get('LOCALAPPDATA')
        if local:
            return Path(local)
    return Path.home() / '.local' / 'share'


def _legacy_data_dir():
    for name in _LEGACY_DATA_DIR_NAMES:
        folder = _data_root() / name
        if folder.is_dir():
            return folder
    return _data_root() / _LEGACY_DATA_DIR_NAMES[0]


def _maybe_migrate_legacy_data(new_dir):
    '''One-time settings migration from the previous name's data dir: copy the small
    user-state files (settings, player list, window pin, display restore) — never logs
    or debug frames; the old dir is left untouched. Skipped once the new dir holds settings.'''
    global _migration_checked
    if _migration_checked:
        return
    _migration_checked = True
    old_dir = _legacy_data_dir()
    if not old_dir.is_dir() or (new_dir / 'settings.json').exists():
        return
    import shutil
    ensure_dir(new_dir)
    for item in old_dir.glob('*.json'):
        try:
            shutil.copy2(item, new_dir / item.name)
        except OSError:
            pass
    for item in old_dir.glob('*.devmode'):
        try:
            shutil.copy2(item, new_dir / item.name)
        except OSError:
            pass


def get_user_app_data_dir():
    '''Per-user writable data (Windows: LOCALAPPDATA\\AresPilot).'''
    path = _data_root() / APP_NAME
    _maybe_migrate_legacy_data(path)
    return path


def get_log_path():
    '''Path to the rotating ``arespilot.log`` in the per-user data dir
    (``ARESPILOT_LOG_DIR`` overrides the folder — the tests use it to keep their
    log lines out of the real run log).'''
    override = os.environ.get('ARESPILOT_LOG_DIR')
    folder = Path(override) if override else get_user_app_data_dir()
    ensure_dir(folder)
    return folder / LOG_FILENAME


# Back-compat alias (old name used across the decompiled tree).
get_autoloot_log_path = get_log_path


def get_template_path(template_name):
    '''
Return ``templates/<16_10|16_9>/…`` for the active aspect (see :class:`app.config.Config`).
``template_name`` should be a filename like ``attack.png`` (not a subpath with ``..``).
'''
    from app.config import Config
    sub = Config().aspect_key
    return get_resource_path(f'''templates/{sub}/{template_name}''')


def ensure_dir(path):
    '''Ensure a directory exists.'''
    path.mkdir(parents = True, exist_ok = True)

