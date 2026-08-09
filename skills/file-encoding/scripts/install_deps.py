# -*- coding: utf-8 -*-
"""install_deps.py - Install Python dependencies for the file-encoding skill.

With Claude Code's official plugin mechanism (see .claude-plugin/plugin.json),
hooks are registered automatically by `claude plugin install` - no settings.json
patching needed. What the plugin mechanism does NOT do is install Python
packages, so run this once after installing the plugin:

    python install_deps.py            # ensure charset-normalizer (+ chardet)
    python install_deps.py --check    # report status only

Dependencies:
  charset-normalizer  - modern encoding detection (required for reliability)
  chardet             - legacy detection fallback (optional)

Failure to install is non-fatal: detection falls back to heuristics.
"""

import os
import subprocess
import sys

_PACKAGES = [
    'charset-normalizer',   # required - reliable detection
    'chardet',              # optional - legacy fallback
]


def _importable(module):
    """Return True if `module` is importable in this interpreter."""
    try:
        __import__(module)
        return True
    except ImportError:
        return False


def _version(module):
    """Return version string of `module`, or 'not installed'."""
    try:
        mod = __import__(module)
        return getattr(mod, '__version__', 'unknown')
    except ImportError:
        return 'not installed'


def _pip_install(package):
    """Try to pip-install `package` via several strategies.

    Returns (ok, detail). Never raises.
    """
    cmds = [
        [sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', package],
        [sys.executable, '-m', 'pip', 'install', '--user', '--disable-pip-version-check', package],
        ['pip', 'install', package],
    ]
    for cmd in cmds:
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            proc.communicate()
        except (OSError, IOError):
            continue
        if proc.returncode == 0:
            return True, ' '.join(cmd)
    return False, ' '.join(cmds[0])


def _status_report():
    lines = []
    for pkg, mod in (('charset-normalizer', 'charset_normalizer'),
                     ('chardet', 'chardet')):
        lines.append('  %-18s %s' % (pkg, _version(mod)))
    return '\n'.join(lines)


def ensure_deps():
    """Ensure required + optional detection packages are importable.

    Returns exit code (0 = all good, 0 even on failure - non-fatal by design).
    """
    print('file-encoding dependencies:')
    print(_status_report())

    for pkg, mod in (('charset-normalizer', 'charset_normalizer'),
                     ('chardet', 'chardet')):
        if _importable(mod):
            print('OK: %s already available (%s).' % (pkg, _version(mod)))
            continue
        ok, detail = _pip_install(pkg)
        if ok:
            print('OK: installed %s (%s) -> %s' % (pkg, _version(mod), detail))
        else:
            print('WARNING: could not install %s (%s). Run manually: %s'
                  % (pkg, detail, detail))
            if pkg == 'charset-normalizer':
                print('  Detection will fall back to heuristics and may '
                      'misidentify Shift-JIS/EUC-KR as GBK on short files.')
    return 0


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    if '--check' in args:
        print('file-encoding dependencies:')
        print(_status_report())
        missing = [m for _, m in (('charset-normalizer', 'charset_normalizer'),
                                  ('chardet', 'chardet')) if not _importable(m)]
        if missing:
            print('MISSING: %s. Run `python install_deps.py` to install.'
                  % ', '.join(missing))
            sys.exit(1)
        sys.exit(0)
    sys.exit(ensure_deps())


if __name__ == '__main__':
    main()
