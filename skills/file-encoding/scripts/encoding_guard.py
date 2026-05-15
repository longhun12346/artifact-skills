# -*- coding: utf-8 -*-
"""encoding_guard.py - PreToolUse hook for Claude Code.

Intercepts Edit/Write/Read tool calls on monitored file extensions inside
recognised project roots:

- Edit/Write: blocked when the target file has a non-UTF-8 encoding, or
  when a new file should inherit the project's existing encoding convention.
- Read: blocked when the file encoding would produce garbled output in the
  Read tool (UTF-16 variants always; ANSI encodings such as GBK/Shift-JIS
  when the file actually contains non-ASCII bytes).

Exit codes:
  0 - allow tool call to proceed
  2 - block tool call (Claude Code interprets this as a hard block)

Claude Code hook stdin: JSON {"tool_name": "...", "tool_input": {...}}
Claude Code hook stdout: message shown to Claude when blocked
"""

from __future__ import print_function

import collections
import json
import locale
import os
import sys

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _sys_ansi_enc():
    """Return the system ANSI encoding as a friendly name (e.g. 'gbk', 'shift-jis').

    Used as the default encoding for C/C++ source files when no sibling-file
    evidence exists.  Falls back to 'gbk' on failure so Chinese-Windows
    projects keep working even if locale detection is unavailable.
    """
    try:
        enc = locale.getdefaultlocale()[1]
        if enc:
            n = enc.lower().replace('-', '').replace('_', '')
            if n in ('cp936', 'gb2312', 'gb18030', 'gbk'):
                return 'gbk'
            if n in ('cp932', 'shiftjis', 'sjis', 'mskanji'):
                return 'shift-jis'
            if n in ('cp949', 'euckr', 'ksc56011987'):
                return 'euc-kr'
            if n in ('cp950', 'big5', 'big5hkscs'):
                return 'big5'
            return enc
    except Exception:
        pass
    return 'gbk'


_SYS_ANSI = _sys_ansi_enc()

MONITORED_EXTENSIONS = {
    '.cpp', '.h', '.hpp', '.c', '.cc', '.cxx',
    '.rc', '.bat', '.nsi', '.ini', '.xml',
}

# Default encoding per extension when sibling inference produces no result.
# C/C++ source files use the system ANSI code page (GBK on Chinese Windows,
# Shift-JIS on Japanese Windows, etc.).  Other types have fixed encodings.
EXTENSION_DEFAULTS = {
    '.cpp':  _SYS_ANSI,
    '.h':    _SYS_ANSI,
    '.hpp':  _SYS_ANSI,
    '.c':    _SYS_ANSI,
    '.cc':   _SYS_ANSI,
    '.cxx':  _SYS_ANSI,
    '.rc':   _SYS_ANSI,
    '.bat':  _SYS_ANSI,
    '.nsi':  'utf-8-bom',
    '.ini':  'utf-16-le-bom',
    '.xml':  'utf-8',
}

# Encodings safe for Edit/Write tools (plain UTF-8 output).
SAFE_ENCODINGS = {
    'utf-8', 'ascii', 'binary', '',
    # Windows-125x (except 1251/Cyrillic) and iso-8859-* are heuristic
    # chardet fallbacks on near-ASCII content; treat as safe to avoid
    # false-positive blocks on UTF-8 files.
    'windows-1252', 'windows-1250', 'windows-1253', 'windows-1254',
    'windows-1255', 'windows-1256', 'windows-1257', 'windows-1258',
    'iso-8859-1', 'iso-8859-2',
}

# Encodings considered "strong evidence" of a non-UTF-8 project convention.
# Windows-1252 / iso-8859-* are excluded: they are heuristic fallbacks that
# fire on ASCII-only or near-ASCII UTF-8 files, not real project encoding.
STRONG_NONASCII_ENCODINGS = {
    'gbk', 'gb2312', 'gb18030',
    'shift-jis', 'euc-kr', 'big5',
    'utf-8-bom', 'utf-16-le-bom', 'utf-16-be-bom', 'utf-16',
    'windows-1251',  # Cyrillic — deliberate; 1252 excluded (too ambiguous)
}

SIBLING_SAMPLE_LIMIT = 5

# Encodings where the Read tool produces completely garbled output.
# UTF-16 encodes every character as 2 bytes; a UTF-8 reader sees null bytes
# between every ASCII character and cannot display the content meaningfully.
READ_ALWAYS_BLOCK = frozenset([
    'utf-16-le-bom', 'utf-16-be-bom', 'utf-16-le', 'utf-16-be', 'utf-16',
])

# ANSI encodings where non-ASCII bytes will be misinterpreted as UTF-8
# sequences.  Only block Read when the file actually has non-ASCII content
# (pure-ASCII ANSI files are displayed correctly by the Read tool).
READ_ANSI_CHECK = frozenset([
    'gbk', 'gb2312', 'gb18030',
    'shift-jis', 'euc-kr', 'big5',
    'windows-1251',
])

# Project root markers: any of these found while walking up → "in a project".
# List (not frozenset) so .git is checked first — it covers the vast majority of projects
# with a single os.path.exists() call, avoiding unnecessary listdir() on most invocations.
_PROJECT_MARKERS = [
    '.git', '.svn', '.hg',
    'CMakeLists.txt', 'setup.py', 'pyproject.toml',
]
# Extension-based markers (scan dir entries); frozenset for O(1) 'in' checks.
_PROJECT_MARKER_EXTS = frozenset(['.vcxproj', '.sln'])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ENCODING_UTILS = os.path.join(_SCRIPT_DIR, 'encoding_utils.py')

# Set ENCODING_GUARD_DEBUG=1 to echo block messages to stderr for debugging.
_DEBUG = os.environ.get('ENCODING_GUARD_DEBUG') == '1'

# In-process import of encoding_utils (lazy, cached).
# Avoids spawning a Python subprocess (~100 ms) on every Edit/Write hook.
_eu = None


def _get_eu():
    global _eu
    if _eu is None:
        sys.path.insert(0, _SCRIPT_DIR)
        import encoding_utils
        _eu = encoding_utils
    return _eu


def _detect(filepath):
    """Detect encoding of filepath. Returns encoding string or '' on error."""
    try:
        return _get_eu().detect_encoding(filepath)
    except Exception:
        return ''


def _infer_encoding_for_new_file(filepath):
    """Infer expected encoding for a new (not-yet-existing) file.

    Strategy:
    1. Scan siblings with same extension; count only STRONG_NONASCII_ENCODINGS.
    2. If dominant strong encoding found, return it.
    3. Otherwise fall back to EXTENSION_DEFAULTS.
    4. If extension not in EXTENSION_DEFAULTS, return 'utf-8'.

    'windows-1252' and 'iso-8859-*' are intentionally excluded from strong
    evidence — they are heuristic fallbacks on ASCII content, not real project
    encoding conventions.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext not in MONITORED_EXTENSIONS:
        return 'utf-8'

    directory = os.path.dirname(filepath) or '.'
    try:
        all_files = os.listdir(directory)
    except OSError:
        all_files = []

    siblings = [
        os.path.join(directory, f)
        for f in all_files
        if os.path.splitext(f)[1].lower() == ext
           and os.path.isfile(os.path.join(directory, f))
    ][:SIBLING_SAMPLE_LIMIT]

    if siblings:
        counter = collections.Counter()
        for s in siblings:
            enc = _detect(s)
            if enc in STRONG_NONASCII_ENCODINGS:
                counter[enc] += 1
        if counter:
            return counter.most_common(1)[0][0]

    return EXTENSION_DEFAULTS.get(ext, 'utf-8')


def _block(message):
    print(message)
    if _DEBUG:
        print(message, file=sys.stderr)
    sys.exit(2)


def _allow():
    sys.exit(0)


def _in_project(filepath):
    """Return True if filepath sits under a recognised project root.

    Walks up the directory tree looking for VCS dirs (.git/.svn/.hg),
    build system files (CMakeLists.txt, *.vcxproj, *.sln), or Python
    project files (setup.py, pyproject.toml).

    Returns False for files that live outside any project (e.g. temp dirs),
    allowing the hook to pass them through without encoding checks.
    """
    d = os.path.dirname(os.path.abspath(filepath))
    while True:
        for marker in _PROJECT_MARKERS:
            if os.path.exists(os.path.join(d, marker)):
                return True
        try:
            for entry in os.listdir(d):
                if os.path.splitext(entry)[1].lower() in _PROJECT_MARKER_EXTS:
                    return True
        except OSError:
            pass
        parent = os.path.dirname(d)
        if parent == d:   # reached filesystem root
            return False
        d = parent


def _has_nonascii(filepath):
    """Return True if the first 512 bytes of filepath contain any byte >= 0x80."""
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(512)
        return any(b >= 0x80 for b in bytearray(chunk))
    except Exception:
        return True  # fail-safe: assume non-ASCII


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except Exception:
        _allow()

    try:
        tool_name = data.get('tool_name', '')
        tool_input = data.get('tool_input', {})

        if tool_name not in ('Edit', 'Write', 'Read'):
            _allow()

        file_path = tool_input.get('file_path', '')
        if not file_path:
            _allow()

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in MONITORED_EXTENSIONS:
            _allow()

        if not _in_project(file_path):
            _allow()

        if tool_name == 'Read':
            if os.path.exists(file_path):
                enc = _detect(file_path)
                if enc in READ_ALWAYS_BLOCK:
                    _block(
                        '[encoding_guard] BLOCKED: Read cannot display {path} (encoding: {enc})\n'
                        '$EU = {utils}\n'
                        '  python $EU read "{path}"'.format(
                            path=file_path, enc=enc, utils=_ENCODING_UTILS,
                        )
                    )
                if enc in READ_ANSI_CHECK and _has_nonascii(file_path):
                    _block(
                        '[encoding_guard] BLOCKED: Read will garble non-ASCII content in {path} (encoding: {enc})\n'
                        '$EU = {utils}\n'
                        '  python $EU read "{path}"'.format(
                            path=file_path, enc=enc, utils=_ENCODING_UTILS,
                        )
                    )
            _allow()

        if not os.path.exists(file_path):
            expected = _infer_encoding_for_new_file(file_path)
            if expected in SAFE_ENCODINGS:
                _allow()
            _block(
                '[encoding_guard] BLOCKED: new file {path}\n'
                'Expected encoding: {enc}\n'
                '$EU = {utils}\n'
                '  python $EU write "{path}" --enc {enc} < content.txt'.format(
                    path=file_path, ext=ext, enc=expected, utils=_ENCODING_UTILS,
                )
            )
        else:
            encoding = _detect(file_path)
            if encoding in SAFE_ENCODINGS:
                _allow()
            _block(
                '[encoding_guard] BLOCKED: {path} (encoding: {enc})\n'
                '$EU = {utils}\n'
                '  python $EU safe-edit "{path}" --old "OLD" --new "NEW"\n'
                '  python $EU read "{path}" > tmp.txt && '
                'python $EU write "{path}" --enc {enc} < tmp.txt'.format(
                    path=file_path, enc=encoding, utils=_ENCODING_UTILS,
                )
            )
    except Exception:
        # Fail-open: any unexpected error allows the tool call through.
        _allow()


if __name__ == '__main__':
    main()
