# -*- coding: utf-8 -*-
"""setup.py - Install or uninstall the encoding_guard PreToolUse hook.

Modifies ~/.claude/settings.json to register encoding_guard.py as a
PreToolUse hook that intercepts Edit/Write tool calls.

Usage:
  python setup.py             # install hook
  python setup.py --uninstall # remove hook
  python setup.py --check     # print current status, exit 0=installed 1=not installed

Compatible with Python 2.6+ and 3.x.
"""

from __future__ import print_function

import io
import json
import os
import sys

_SETTINGS_PATH = os.path.join(os.path.expanduser('~'), '.claude', 'settings.json')
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_GUARD_PATH = os.path.join(_SCRIPTS_DIR, 'encoding_guard.py')
_GUARD_MARKER = 'encoding_guard.py'


def _load_settings():
    if not os.path.exists(_SETTINGS_PATH):
        return {}
    try:
        with io.open(_SETTINGS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (ValueError, IOError) as e:
        print('ERROR: cannot parse {}: {}'.format(_SETTINGS_PATH, e))
        sys.exit(1)


def _save_settings(data):
    settings_dir = os.path.dirname(_SETTINGS_PATH)
    if not os.path.exists(settings_dir):
        os.makedirs(settings_dir)
    content = json.dumps(data, indent=2, ensure_ascii=False)
    if not content.endswith('\n'):
        content += '\n'
    if not isinstance(content, type(u'')):
        content = content.decode('utf-8')
    with io.open(_SETTINGS_PATH, 'w', encoding='utf-8') as f:
        f.write(content)


def _hook_command():
    # Forward slashes: bash does not eat them on Windows; Python accepts them.
    path = _GUARD_PATH.replace(chr(92), '/')
    return 'python "{}"'.format(path)


def _is_installed(settings):
    hooks = settings.get('hooks', {})
    for group in hooks.get('PreToolUse', []):
        for hook in group.get('hooks', []):
            if _GUARD_MARKER in hook.get('command', ''):
                return True
    return False


def install(settings):
    if _is_installed(settings):
        print('encoding_guard hook already installed in {}'.format(_SETTINGS_PATH))
        return
    if not os.path.exists(_GUARD_PATH):
        print('ERROR: encoding_guard.py not found at {}'.format(_GUARD_PATH))
        sys.exit(1)
    hook_group = {
        'matcher': 'Edit|Write',
        'hooks': [{'type': 'command', 'command': _hook_command()}],
    }
    if 'hooks' not in settings:
        settings['hooks'] = {}
    if 'PreToolUse' not in settings['hooks']:
        settings['hooks']['PreToolUse'] = []
    settings['hooks']['PreToolUse'].append(hook_group)
    _save_settings(settings)
    print('OK: hook installed -> {}'.format(_SETTINGS_PATH))
    print('    command: {}'.format(_hook_command()))
    print('Restart Claude Code to activate.')


def uninstall(settings):
    if not _is_installed(settings):
        print('encoding_guard hook not found in {}'.format(_SETTINGS_PATH))
        return
    hooks = settings.get('hooks', {})
    pre = hooks.get('PreToolUse', [])
    new_pre = []
    for group in pre:
        filtered = [h for h in group.get('hooks', [])
                    if _GUARD_MARKER not in h.get('command', '')]
        if filtered:
            group = dict(group)
            group['hooks'] = filtered
            new_pre.append(group)
    if new_pre:
        settings['hooks']['PreToolUse'] = new_pre
    else:
        del settings['hooks']['PreToolUse']
        if not settings['hooks']:
            del settings['hooks']
    _save_settings(settings)
    print('OK: hook removed from {}'.format(_SETTINGS_PATH))
    print('Restart Claude Code to deactivate.')


def check(settings):
    if _is_installed(settings):
        print('INSTALLED: encoding_guard hook active in {}'.format(_SETTINGS_PATH))
        sys.exit(0)
    else:
        print('NOT INSTALLED: encoding_guard hook not found in {}'.format(_SETTINGS_PATH))
        sys.exit(1)


def main():
    args = sys.argv[1:]
    settings = _load_settings()
    if '--uninstall' in args:
        uninstall(settings)
    elif '--check' in args:
        check(settings)
    else:
        install(settings)


if __name__ == '__main__':
    main()
