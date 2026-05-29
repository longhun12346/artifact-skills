# -*- coding: utf-8 -*-
"""install_hook.py - Install or uninstall the encoding_transparent hook.

Modifies ~/.claude/settings.json to register encoding_transparent.py as
PreToolUse + PostToolUse hooks that transparently handle file encoding.

Usage:
  python install_hook.py             # install hooks
  python install_hook.py --uninstall # remove hooks (also removes old encoding_guard if present)
  python install_hook.py --check     # print current status, exit 0=installed 1=not installed

Compatible with Python 2.6+ and 3.x.
"""

from __future__ import print_function

import io
import json
import os
import sys

_SETTINGS_PATH = os.path.join(os.path.expanduser('~'), '.claude', 'settings.json')
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_HOOK_PATH = os.path.join(_SCRIPTS_DIR, 'encoding_transparent.py')
_HOOK_MARKER = 'encoding_transparent.py'
_OLD_MARKER = 'encoding_guard.py'


def _load_settings():
    if not os.path.exists(_SETTINGS_PATH):
        return {}
    try:
        with io.open(_SETTINGS_PATH, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        if not content:
            return {}
        return json.loads(content)
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


def _hook_command(mode):
    """Return the hook command string for the given mode (pre/post)."""
    path = _HOOK_PATH.replace(chr(92), '/')
    return 'python "{}" {}'.format(path, mode)


def _has_marker(settings, hook_type, marker):
    """Check if a hook with the given marker is installed in hook_type."""
    hooks = settings.get('hooks', {})
    for group in hooks.get(hook_type, []):
        for hook in group.get('hooks', []):
            if marker in hook.get('command', ''):
                return True
    return False


def _is_installed(settings):
    return (_has_marker(settings, 'PreToolUse', _HOOK_MARKER) and
            _has_marker(settings, 'PostToolUse', _HOOK_MARKER))


def _remove_marker(settings, hook_type, marker):
    """Remove all hook groups containing the marker from hook_type."""
    hooks = settings.get('hooks', {})
    groups = hooks.get(hook_type, [])
    new_groups = []
    for group in groups:
        filtered = [h for h in group.get('hooks', [])
                    if marker not in h.get('command', '')]
        if filtered:
            group = dict(group)
            group['hooks'] = filtered
            new_groups.append(group)
    if new_groups:
        hooks[hook_type] = new_groups
    elif hook_type in hooks:
        del hooks[hook_type]
    if hooks:
        settings['hooks'] = hooks
    elif 'hooks' in settings:
        del settings['hooks']


def install(settings):
    if _is_installed(settings):
        print('encoding_transparent hooks already installed in {}'.format(_SETTINGS_PATH))
        return

    if not os.path.exists(_HOOK_PATH):
        print('ERROR: encoding_transparent.py not found at {}'.format(_HOOK_PATH))
        sys.exit(1)

    # Remove old encoding_guard if present
    if _has_marker(settings, 'PreToolUse', _OLD_MARKER):
        _remove_marker(settings, 'PreToolUse', _OLD_MARKER)
        print('Removed old encoding_guard hook.')

    # Install PreToolUse
    pre_group = {
        'matcher': 'Edit|Write|Read',
        'hooks': [{'type': 'command', 'command': _hook_command('pre')}],
    }
    if 'hooks' not in settings:
        settings['hooks'] = {}
    if 'PreToolUse' not in settings['hooks']:
        settings['hooks']['PreToolUse'] = []
    settings['hooks']['PreToolUse'].append(pre_group)

    # Install PostToolUse
    post_group = {
        'matcher': 'Edit|Write|Read',
        'hooks': [{'type': 'command', 'command': _hook_command('post')}],
    }
    if 'PostToolUse' not in settings['hooks']:
        settings['hooks']['PostToolUse'] = []
    settings['hooks']['PostToolUse'].append(post_group)

    _save_settings(settings)
    print('OK: hooks installed -> {}'.format(_SETTINGS_PATH))
    print('    PreToolUse:  {}'.format(_hook_command('pre')))
    print('    PostToolUse: {}'.format(_hook_command('post')))
    print('Restart Claude Code to activate.')


def uninstall(settings):
    removed = False

    if _has_marker(settings, 'PreToolUse', _HOOK_MARKER):
        _remove_marker(settings, 'PreToolUse', _HOOK_MARKER)
        removed = True
    if _has_marker(settings, 'PostToolUse', _HOOK_MARKER):
        _remove_marker(settings, 'PostToolUse', _HOOK_MARKER)
        removed = True

    # Also remove old encoding_guard if present
    if _has_marker(settings, 'PreToolUse', _OLD_MARKER):
        _remove_marker(settings, 'PreToolUse', _OLD_MARKER)
        removed = True

    if not removed:
        print('No encoding hooks found in {}'.format(_SETTINGS_PATH))
        return

    _save_settings(settings)
    print('OK: hooks removed from {}'.format(_SETTINGS_PATH))
    print('Restart Claude Code to deactivate.')


def check(settings):
    if _is_installed(settings):
        print('INSTALLED: encoding_transparent hooks active in {}'.format(_SETTINGS_PATH))
        sys.exit(0)
    elif _has_marker(settings, 'PreToolUse', _OLD_MARKER):
        print('OLD VERSION: encoding_guard (blocking) hook found. Run install_hook.py to upgrade.')
        sys.exit(1)
    else:
        print('NOT INSTALLED: no encoding hooks found in {}'.format(_SETTINGS_PATH))
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
