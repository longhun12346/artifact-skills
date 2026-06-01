# -*- coding: utf-8 -*-
"""encoding_transparent.py - Transparent encoding hook for Claude Code.

Makes non-UTF-8 files editable by Claude Code's native Edit/Write/Read tools
without any special commands or encoding awareness from Claude.

How it works:
  PreToolUse:  Detects encoding; if non-UTF-8, converts file to UTF-8 in place
               and saves original encoding to a state file.
  PostToolUse: Reads state file; converts file back from UTF-8 to original encoding.
  Recover:     Scans for leftover state files (from crashes) and restores files.

Hook configuration in ~/.claude/settings.json:
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Edit|Write|Read",
      "hooks": [{"type": "command",
        "command": "python encoding_transparent.py pre"}]
    }],
    "PostToolUse": [{
      "matcher": "Edit|Write|Read",
      "hooks": [{"type": "command",
        "command": "python encoding_transparent.py post"}]
    }]
  }
}

Exit codes:
  0 - allow tool call (PreToolUse) / success (PostToolUse)
  2 - block tool call (only used if conversion fails critically)
"""

from __future__ import print_function

import hashlib
import io
import json
import os
import sys
import tempfile
import time

if os.name == 'nt':
    import msvcrt
else:
    import fcntl

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MONITORED_EXTENSIONS = {
    '.cpp', '.h', '.hpp', '.c', '.cc', '.cxx',
    '.rc', '.bat', '.nsi', '.ini', '.xml',
}

# Encodings that Claude's tools handle natively — no conversion needed.
SAFE_ENCODINGS = {
    'utf-8', 'ascii', 'binary',
    # Single-byte western encodings: chardet often reports these as false
    # positives on near-ASCII UTF-8 content.  Even if genuinely windows-1252,
    # Claude's tools can read/write them without garbling (bytes < 0x80 are
    # identical to ASCII, and high bytes are rare in source code).
    'windows-1252', 'windows-1250', 'windows-1253', 'windows-1254',
    'windows-1255', 'windows-1256', 'windows-1257', 'windows-1258',
    'iso-8859-1', 'iso-8859-2',
}

# State directory for tracking files currently in UTF-8 temporary state
STATE_DIR = os.path.join(tempfile.gettempdir(), 'claude-encoding-hook-state')

# Set ENCODING_TRANSPARENT_DEBUG=1 for stderr diagnostics
_DEBUG = os.environ.get('ENCODING_TRANSPARENT_DEBUG') == '1'

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_eu = None


def _get_eu():
    """Lazy-import encoding_utils from sibling module."""
    global _eu
    if _eu is None:
        if _SCRIPT_DIR not in sys.path:
            sys.path.insert(0, _SCRIPT_DIR)
        import encoding_utils
        _eu = encoding_utils
    return _eu


def _debug(msg):
    if _DEBUG:
        sys.stderr.write('[encoding_transparent] %s\n' % msg)


class _FileLock(object):
    """Cross-platform file lock context manager."""

    def __init__(self, path):
        self._path = path + '.lock'
        self._f = None

    def __enter__(self):
        if not os.path.isdir(os.path.dirname(self._path)):
            os.makedirs(os.path.dirname(self._path))
        self._f = open(self._path, 'w')
        if os.name == 'nt':
            msvcrt.locking(self._f.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(self._f.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *args):
        if self._f:
            if os.name == 'nt':
                msvcrt.locking(self._f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self._f.fileno(), fcntl.LOCK_UN)
            self._f.close()


def _state_path(filepath):
    """Return the state file path for a given source file."""
    abspath = os.path.abspath(filepath)
    h = hashlib.sha256(abspath.encode('utf-8')).hexdigest()
    return os.path.join(STATE_DIR, h + '.json')


def _save_state(filepath, encoding):
    """Save conversion state: records that filepath was converted to UTF-8."""
    if not os.path.isdir(STATE_DIR):
        os.makedirs(STATE_DIR)
    state = {
        'path': os.path.abspath(filepath),
        'encoding': encoding,
        'timestamp': time.time(),
    }
    state_file = _state_path(filepath)
    json_str = json.dumps(state, ensure_ascii=False)
    if isinstance(json_str, bytes):
        json_str = json_str.decode('utf-8')
    with _FileLock(state_file):
        with io.open(state_file, 'w', encoding='utf-8') as f:
            f.write(json_str)
    _debug('State saved: %s -> %s' % (filepath, encoding))


def _load_state(filepath):
    """Load conversion state. Returns dict or None."""
    state_file = _state_path(filepath)
    if not os.path.exists(state_file):
        return None
    try:
        with _FileLock(state_file):
            with io.open(state_file, 'r', encoding='utf-8') as f:
                return json.loads(f.read())
    except (IOError, ValueError):
        return None


def _remove_state(filepath):
    """Remove state file and its lock file."""
    state_file = _state_path(filepath)
    try:
        with _FileLock(state_file):
            os.remove(state_file)
        _debug('State removed: %s' % filepath)
    except OSError:
        pass
    # Clean up lock file
    try:
        os.remove(state_file + '.lock')
    except OSError:
        pass




def _atomic_write(filepath, data, encoding='utf-8', newline=''):
    """Write data to filepath atomically via a temp file + os.replace.

    Writes to a temporary file in the same directory, then atomically replaces
    the target. This prevents file corruption if the process is killed mid-write.
    """
    dirpath = os.path.dirname(os.path.abspath(filepath))
    fd, tmp_path = tempfile.mkstemp(dir=dirpath, suffix='.tmp')
    try:
        with io.open(fd, 'w', encoding=encoding, newline=newline) as f:
            f.write(data)
        os.replace(tmp_path, filepath)
    except BaseException:
        _try_remove(tmp_path)
        raise


def _convert_to_utf8(filepath, encoding):
    """Convert file from `encoding` to plain UTF-8 atomically.

    Returns True on success, False on failure.
    Preserves the file's original mtime so that tools (e.g. Edit) don't detect
    a spurious modification after a Pre-hook conversion.
    """
    eu = _get_eu()

    orig_mtime = os.path.getmtime(filepath)

    try:
        content = eu.read_with_encoding(filepath, encoding, newline='')
    except (IOError, UnicodeDecodeError) as e:
        _debug('Failed to read %s as %s: %s' % (filepath, encoding, e))
        return False

    try:
        _atomic_write(filepath, content, encoding='utf-8', newline='')
    except (IOError, UnicodeEncodeError) as e:
        _debug('Failed to write %s as UTF-8: %s' % (filepath, e))
        return False

    os.utime(filepath, (orig_mtime, orig_mtime))
    _debug('Converted %s: %s -> utf-8' % (filepath, encoding))
    return True


def _convert_from_utf8(filepath, encoding):
    """Convert file from UTF-8 back to `encoding` atomically.

    Returns True on success, False on failure.
    Preserves the file's mtime so that tools don't detect a spurious modification.
    """
    eu = _get_eu()

    orig_mtime = os.path.getmtime(filepath)

    try:
        with io.open(filepath, 'r', encoding='utf-8', newline='') as f:
            content = f.read()
    except (IOError, UnicodeDecodeError) as e:
        _debug('Failed to read %s as UTF-8: %s' % (filepath, e))
        return False

    # Atomic write: write to temp file, then replace original
    dirpath = os.path.dirname(os.path.abspath(filepath))
    fd, tmp_path = tempfile.mkstemp(dir=dirpath, suffix='.tmp')
    try:
        os.close(fd)
        eu.write_with_encoding(tmp_path, content, encoding, newline='')
        os.replace(tmp_path, filepath)
    except (IOError, UnicodeEncodeError, OSError) as e:
        _try_remove(tmp_path)
        _debug('Failed to write %s as %s: %s' % (filepath, encoding, e))
        return False

    os.utime(filepath, (orig_mtime, orig_mtime))
    _debug('Converted %s: utf-8 -> %s' % (filepath, encoding))
    return True


def _try_remove(path):
    """Remove a file, ignoring errors if it doesn't exist."""
    try:
        os.remove(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Hook handlers
# ---------------------------------------------------------------------------

def handle_pre(tool_name, tool_input):
    """PreToolUse handler: convert non-UTF-8 files to UTF-8 before tool runs."""
    file_path = tool_input.get('file_path', '')
    if not file_path:
        return

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in MONITORED_EXTENSIONS:
        return

    # File doesn't exist yet (Write creating new file) — let it through
    if not os.path.exists(file_path):
        return

    # Already converted by a previous Pre call (e.g. Read followed by Edit)
    state = _load_state(file_path)
    if state is not None:
        _debug('Already converted (state exists): %s' % file_path)
        return

    # Detect encoding
    eu = _get_eu()
    encoding = eu.detect_encoding(file_path)

    if not encoding or encoding in SAFE_ENCODINGS:
        return

    # Non-UTF-8: convert to UTF-8 and save state
    if _convert_to_utf8(file_path, encoding):
        _save_state(file_path, encoding)
    else:
        # Conversion failed — block the tool call so Claude knows
        msg = ('[encoding_transparent] ERROR: failed to convert %s (%s -> utf-8). '
               'File may be corrupted or locked.' % (file_path, encoding))
        print(msg)
        sys.exit(2)


def handle_post(tool_name, tool_input):
    """PostToolUse handler: convert file back from UTF-8 to original encoding."""
    file_path = tool_input.get('file_path', '')
    if not file_path:
        return

    # Check if we have state for this file (meaning Pre converted it)
    state = _load_state(file_path)
    if state is None:
        return

    encoding = state['encoding']

    if not os.path.exists(file_path):
        # File was deleted by the tool — just clean up state
        _remove_state(file_path)
        return

    if _convert_from_utf8(file_path, encoding):
        _remove_state(file_path)
    else:
        # Conversion back failed — file stays as UTF-8.
        # Output warning to stderr so Claude and the user are informed.
        _remove_state(file_path)
        msg = ('[encoding_transparent] WARNING: could not convert %s back to %s. '
               'File now remains as UTF-8 (likely contains characters not representable in %s).'
               % (file_path, encoding, encoding))
        sys.stderr.write(msg + '\n')
        # Also print to stdout so Claude sees it in hook output
        print(msg)


def handle_recover():
    """Recovery handler: restore any files left in UTF-8 state from crashes."""
    if not os.path.isdir(STATE_DIR):
        print('No state files found.')
        return

    state_files = [f for f in os.listdir(STATE_DIR) if f.endswith('.json')]
    if not state_files:
        print('No state files found.')
        return

    recovered = 0
    failed = 0
    for fname in state_files:
        state_path = os.path.join(STATE_DIR, fname)
        try:
            with _FileLock(state_path):
                with io.open(state_path, 'r', encoding='utf-8') as f:
                    state = json.loads(f.read())
        except (IOError, ValueError):
            continue

        filepath = state.get('path', '')
        encoding = state.get('encoding', '')
        if not filepath or not encoding:
            os.remove(state_path)
            _try_remove(state_path + '.lock')
            continue

        if not os.path.exists(filepath):
            os.remove(state_path)
            _try_remove(state_path + '.lock')
            continue

        # Try to convert back
        if _convert_from_utf8(filepath, encoding):
            os.remove(state_path)
            _try_remove(state_path + '.lock')
            recovered += 1
            print('Recovered: %s -> %s' % (filepath, encoding))
        else:
            failed += 1
            print('FAILED to recover: %s (encoding: %s)' % (filepath, encoding))

    # Clean up any orphaned .lock files
    for fname in os.listdir(STATE_DIR):
        if fname.endswith('.lock'):
            json_file = os.path.join(STATE_DIR, fname[:-5])
            if not os.path.exists(json_file):
                _try_remove(os.path.join(STATE_DIR, fname))

    if recovered == 0 and failed == 0:
        print('No files needed recovery.')
    else:
        print('Recovery complete: %d restored, %d failed' % (recovered, failed))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        sys.stderr.write('Usage: encoding_transparent.py <pre|post|recover>\n')
        sys.exit(1)

    mode = sys.argv[1]

    if mode == 'recover':
        handle_recover()
        sys.exit(0)

    # Pre and Post modes read hook data from stdin
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except (ValueError, IOError):
        # Malformed input — fail open
        sys.exit(0)

    tool_name = data.get('tool_name', '')
    tool_input = data.get('tool_input', {})

    if tool_name not in ('Edit', 'Write', 'Read'):
        sys.exit(0)

    try:
        if mode == 'pre':
            handle_pre(tool_name, tool_input)
        elif mode == 'post':
            handle_post(tool_name, tool_input)
        else:
            sys.stderr.write('Unknown mode: %s\n' % mode)
            sys.exit(1)
    except Exception as e:
        # Fail-open: any unexpected error allows the tool call through
        sys.stderr.write('[encoding_transparent] Unexpected error (fail-open): %s\n' % e)
        sys.exit(0)

    sys.exit(0)


if __name__ == '__main__':
    main()
