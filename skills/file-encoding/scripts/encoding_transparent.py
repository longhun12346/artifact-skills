# -*- coding: utf-8 -*-
"""encoding_transparent.py - Encoding guard hook (inform-only mode, v3).

IMPORTANT DESIGN CHANGE (v3): this hook NEVER modifies files.

Previous versions transparently converted non-UTF-8 files to UTF-8 before
Edit/Write/Read and converted them back afterwards. That in-place rewriting
carried corruption and data-loss risk (crash between Pre/Post, Post failure
discarding edits, MultiEdit not matched, etc.).

v3 instead *informs* the model and blocks unsafe operations:

  PreToolUse:
    - Read on a non-UTF-8 file  -> informational message (tool allowed), tells
      the model to use `encoding_utils.py read` instead of seeing mojibake.
    - Edit/Write/MultiEdit on a non-UTF-8 file -> BLOCKED (exit code 2) with
      instructions to use `encoding_utils.py replace` / `safe-write`.
    - UTF-8 / ASCII / safe single-byte files pass through untouched.

  PostToolUse:
    - Light-weight guard: if a previously non-UTF-8 file now detects as UTF-8,
      a native tool likely rewrote it; print a warning with recovery commands.

  Recover:
    - Only cleans up leftover state files. Nothing on disk was ever modified
      by this hook, so there is nothing to restore.

Exit codes:
  0 - allow tool call / success
  2 - block tool call (non-UTF-8 file targeted by Edit/Write/MultiEdit)
"""

import hashlib
import json
import os
import sys
import tempfile
import time

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MONITORED_EXTENSIONS = {
    '.cpp', '.h', '.hpp', '.c', '.cc', '.cxx',
    '.rc', '.bat', '.nsi', '.ini', '.xml',
}

# Encodings Claude's tools handle natively - no need to warn or block.
SAFE_ENCODINGS = {
    'utf-8', 'ascii', 'binary',
    # Single-byte western encodings: bytes < 0x80 are identical to ASCII and
    # high bytes are rare in source code, so native tools round-trip safely.
    # windows-1251 (Cyrillic) is deliberately NOT safe: Cyrillic comments are
    # common in source code, so a native tool would garble them.
    'windows-1250', 'windows-1252', 'windows-1253',
    'windows-1254', 'windows-1255', 'windows-1256', 'windows-1257',
    'windows-1258', 'iso-8859-1', 'iso-8859-2',
}

# Minimal state: records the encoding of files we warned about, so PostToolUse
# can detect if a native tool rewrote them. No backup, no lock - losing this
# file is harmless (worst case: one missed warning).
STATE_DIR = os.path.join(tempfile.gettempdir(), 'claude-encoding-hook-state')

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


def _state_path(filepath):
    """Return the state file path for a given source file."""
    abspath = os.path.abspath(filepath)
    h = hashlib.sha256(abspath.encode('utf-8')).hexdigest()
    return os.path.join(STATE_DIR, h + '.json')


def _save_state(filepath, encoding):
    """Record that `filepath` is `encoding` (also serves as detection cache).

    Stores mtime+size so a later PreToolUse can reuse the cached encoding
    without re-running the (slow ~200ms) detection library import.
    """
    if not os.path.isdir(STATE_DIR):
        try:
            os.makedirs(STATE_DIR)
        except OSError:
            return
    try:
        st = os.stat(filepath)
        mtime, size = st.st_mtime_ns, st.st_size
    except OSError:
        mtime, size = 0, 0
    state = {
        'path': os.path.abspath(filepath),
        'encoding': encoding,
        'mtime': mtime,
        'size': size,
        'timestamp': time.time(),
    }
    try:
        with open(_state_path(filepath), 'w') as f:
            json.dump(state, f, ensure_ascii=False)
    except IOError:
        pass


def _state_matches_file(state, filepath):
    """True if the cached state still describes the current file content."""
    try:
        st = os.stat(filepath)
    except OSError:
        return False
    return (state.get('mtime') == st.st_mtime_ns and
            state.get('size') == st.st_size)


def _load_state(filepath):
    """Return saved state dict or None."""
    try:
        with open(_state_path(filepath), 'r') as f:
            return json.load(f)
    except (IOError, ValueError):
        return None


def _remove_state(filepath):
    """Remove the state file if present."""
    try:
        os.remove(_state_path(filepath))
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Hook handlers
# ---------------------------------------------------------------------------

def _tool_file(tool_input):
    """Extract the target file path from tool_input (Edit/Write/MultiEdit/...)."""
    for key in ('file_path', 'notebook_path'):
        val = tool_input.get(key)
        if val:
            return val
    return ''


def _print_msg(msg):
    """Emit a message to stdout (seen by the model) and stderr (debug)."""
    sys.stderr.write(msg + '\n')
    print(msg)


def handle_pre(tool_name, tool_input):
    """PreToolUse: inform about non-UTF-8 files; block unsafe edits."""
    file_path = _tool_file(tool_input)
    if not file_path:
        return

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in MONITORED_EXTENSIONS:
        return

    # New file (Write creating it) - nothing to detect yet
    if not os.path.exists(file_path):
        return

    eu = _get_eu()

    # Detection cache: reuse the encoding recorded by an earlier call on the
    # same unchanged file, skipping the ~200ms detection-library import.
    state = _load_state(file_path)
    if state and _state_matches_file(state, file_path):
        encoding = state.get('encoding')
    else:
        encoding = eu.detect_encoding(file_path)

    if not encoding or encoding in SAFE_ENCODINGS:
        # File changed to a safe encoding - drop any stale state
        if state:
            _remove_state(file_path)
        return

    _save_state(file_path, encoding)

    eu_script = os.path.join(_SCRIPT_DIR, 'encoding_utils.py')

    if tool_name == 'Read':
        # Read is non-destructive: allow it, but steer the model to the
        # transcode-read so it sees real content instead of mojibake.
        _print_msg(
            f'[encoding] INFO: {file_path} is {encoding} (not UTF-8). Direct Read shows mojibake.\n'
            f'  Read with:    python "{eu_script}" read "{file_path}" --enc {encoding}')
        return

    # Edit / Write / MultiEdit on a non-UTF-8 file: BLOCK.
    _print_msg(
        f'[encoding] BLOCKED: {file_path} is {encoding} (not UTF-8). Native Edit/Write would\n'
        f'  write UTF-8 bytes into a {encoding} file and corrupt it. Use the encoding\n'
        '  tools instead:\n'
        f'  Read:    python "{eu_script}" read "{file_path}" --enc {encoding}\n'
        f'  Edit:    python "{eu_script}" replace "{file_path}" --old "<old>" --new "<new>" --enc {encoding}\n'
        f'  Rewrite: python "{eu_script}" safe-write "{file_path}" --enc {encoding}   (pipe content via stdin)\n'
        '  Do NOT use native Edit/Write/MultiEdit on this file.')
    sys.exit(2)


def handle_post(tool_name, tool_input):
    """PostToolUse: detect if a guarded file was rewritten into another encoding."""
    file_path = _tool_file(tool_input)
    if not file_path:
        return

    state = _load_state(file_path)
    if state is None:
        return

    if not os.path.exists(file_path):
        _remove_state(file_path)  # deleted - nothing to check
        return

    eu = _get_eu()
    current = eu.detect_encoding(file_path)

    if current == state.get('encoding'):
        _remove_state(file_path)
        return

    _remove_state(file_path)
    eu_script = os.path.join(_SCRIPT_DIR, 'encoding_utils.py')
    msg = (
        f'[encoding] WARNING: {file_path} encoding changed from {state.get("encoding")} to {current} - it was probably\n'
        '  rewritten by a native tool. If unintended, restore it:\n'
        f'    python "{eu_script}" convert "{file_path}" --to {state.get("encoding")}\n'
        f'  or from git: git checkout -- "{file_path}"')
    _print_msg(msg)


def handle_recover():
    """Clean up leftover state files. No file was ever modified by this hook."""
    if not os.path.isdir(STATE_DIR):
        print('No state files found.')
        return
    state_files = [f for f in os.listdir(STATE_DIR) if f.endswith('.json')]
    if not state_files:
        print('No state files found.')
        return
    for fname in state_files:
        try:
            os.remove(os.path.join(STATE_DIR, fname))
        except OSError:
            pass
    print('Cleaned %d leftover state file(s). No files needed recovery '
          '(inform-only mode never modifies files).' % len(state_files))


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
        # Malformed input - fail open
        sys.exit(0)

    tool_name = data.get('tool_name', '')
    tool_input = data.get('tool_input', {})

    try:
        if mode == 'pre':
            handle_pre(tool_name, tool_input)
        elif mode == 'post':
            handle_post(tool_name, tool_input)
        else:
            sys.stderr.write('Unknown mode: %s\n' % mode)
            sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        # Fail-open: any unexpected error allows the tool call through
        sys.stderr.write('[encoding_transparent] Unexpected error (fail-open): %s\n' % e)
        sys.exit(0)

    sys.exit(0)


if __name__ == '__main__':
    main()
