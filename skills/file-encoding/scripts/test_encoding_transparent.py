# -*- coding: utf-8 -*-
"""Tests for encoding_transparent.py - the inform-only encoding guard hook (v3).

Core contract of v3:
  - The hook NEVER modifies file bytes (no conversion, no backup).
  - Edit/Write/MultiEdit on a non-UTF-8 monitored file -> exit 2 (blocked).
  - Read on a non-UTF-8 monitored file -> exit 0 + informational message.
  - UTF-8 / ASCII / safe single-byte files pass through silently.
  - PostToolUse warns if a guarded file's encoding changed.
  - recover only cleans up state files.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# Ensure we can import sibling modules
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import encoding_utils
import encoding_transparent


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _create_temp_project():
    """Create a temporary directory (simulates a project)."""
    return tempfile.mkdtemp(prefix='enc_transparent_test_')


def _write_file_bytes(filepath, raw_bytes):
    """Write raw bytes to a file."""
    with open(filepath, 'wb') as f:
        f.write(raw_bytes)


def _read_file_bytes(filepath):
    """Read raw bytes from a file."""
    with open(filepath, 'rb') as f:
        return f.read()


def _make_gbk_content():
    """Return bytes of a GBK-encoded C++ file with Chinese comments.

    Content must have enough Chinese characters for chardet to reliably
    identify as GBK even on non-Chinese locale systems (English Windows CI).
    """
    content = (u'// 文件描述：测试中文编码处理模块\n'
               u'// 作者：张三  日期：二零二六年\n'
               u'#include <stdio.h>\n'
               u'int main() {\n'
               u'    printf("你好世界\\n");\n'
               u'    return 0;\n'
               u'}\n')
    return content.encode('gbk')


def _make_utf8_content():
    """Return bytes of a plain UTF-8 file with Chinese comments."""
    content = (u'// 文件描述：UTF-8 测试文件\n'
               u'int x = 1;\n')
    return content.encode('utf-8')


def _make_utf8bom_content():
    """Return bytes of a UTF-8 BOM file."""
    content = u'// Hello BOM\nint x = 1;\n'
    return b'\xef\xbb\xbf' + content.encode('utf-8')


def _make_utf16le_content():
    """Return bytes of a UTF-16 LE BOM file."""
    content = u'[Section]\nkey=value\n'
    return b'\xff\xfe' + content.encode('utf-16-le')


def _run_hook(mode, tool_name, file_path):
    """Run encoding_transparent.py with given mode and tool input.

    Returns (exit_code, stdout, stderr).
    """
    script = os.path.join(_SCRIPT_DIR, 'encoding_transparent.py')
    data = {
        'tool_name': tool_name,
        'tool_input': {'file_path': file_path},
    }
    proc = subprocess.Popen(
        [sys.executable, script, mode],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = proc.communicate(json.dumps(data).encode('utf-8'))
    return (proc.returncode,
            stdout.decode('utf-8', errors='replace'),
            stderr.decode('utf-8', errors='replace'))


def _run_hook_inprocess(mode, tool_name, file_path):
    """Run handle_pre/handle_post in-process (allows mocking detection).

    Returns (exit_code, stdout). SystemExit(2) from blocking is captured.
    """
    import io
    saved_out, saved_err = sys.stdout, sys.stderr
    buf_out, buf_err = io.StringIO(), io.StringIO()
    sys.stdout, sys.stderr = buf_out, buf_err
    code = 0
    try:
        try:
            if mode == 'pre':
                encoding_transparent.handle_pre(tool_name, {'file_path': file_path})
            else:
                encoding_transparent.handle_post(tool_name, {'file_path': file_path})
        except SystemExit as e:
            code = e.code
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err
    return code, buf_out.getvalue()


def _clean_state():
    if os.path.isdir(encoding_transparent.STATE_DIR):
        shutil.rmtree(encoding_transparent.STATE_DIR)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPreBlocking(unittest.TestCase):
    """PreToolUse must BLOCK unsafe edits on non-UTF-8 files (exit 2)."""

    def setUp(self):
        self.project_dir = _create_temp_project()
        _clean_state()

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)
        _clean_state()

    def test_edit_gbk_blocked(self):
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_gbk_content())
        code, out, _ = _run_hook('pre', 'Edit', filepath)
        self.assertEqual(code, 2)
        self.assertIn('BLOCKED', out)
        self.assertIn('encoding_utils.py', out)
        self.assertIn('gbk', out)

    def test_write_gbk_blocked(self):
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_gbk_content())
        code, out, _ = _run_hook('pre', 'Write', filepath)
        self.assertEqual(code, 2)
        self.assertIn('BLOCKED', out)

    def test_multiedit_gbk_blocked(self):
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_gbk_content())
        code, out, _ = _run_hook('pre', 'MultiEdit', filepath)
        self.assertEqual(code, 2)
        self.assertIn('BLOCKED', out)

    def test_utf16le_edit_blocked(self):
        filepath = os.path.join(self.project_dir, 'config.ini')
        _write_file_bytes(filepath, _make_utf16le_content())
        code, out, _ = _run_hook('pre', 'Edit', filepath)
        self.assertEqual(code, 2)
        self.assertIn('BLOCKED', out)

    def test_utf8bom_edit_blocked(self):
        filepath = os.path.join(self.project_dir, 'install.nsi')
        _write_file_bytes(filepath, _make_utf8bom_content())
        code, out, _ = _run_hook('pre', 'Edit', filepath)
        self.assertEqual(code, 2)
        self.assertIn('BLOCKED', out)


class TestPreDoesNotModifyFiles(unittest.TestCase):
    """THE core v3 guarantee: file bytes are never touched by the hook."""

    def setUp(self):
        self.project_dir = _create_temp_project()
        _clean_state()

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)
        _clean_state()

    def test_gbk_bytes_unchanged_after_blocked_edit(self):
        filepath = os.path.join(self.project_dir, 'main.cpp')
        raw = _make_gbk_content()
        _write_file_bytes(filepath, raw)
        _run_hook('pre', 'Edit', filepath)
        self.assertEqual(_read_file_bytes(filepath), raw)

    def test_gbk_bytes_unchanged_after_read(self):
        filepath = os.path.join(self.project_dir, 'main.cpp')
        raw = _make_gbk_content()
        _write_file_bytes(filepath, raw)
        _run_hook('pre', 'Read', filepath)
        self.assertEqual(_read_file_bytes(filepath), raw)

    def test_utf16le_bytes_unchanged(self):
        filepath = os.path.join(self.project_dir, 'config.ini')
        raw = _make_utf16le_content()
        _write_file_bytes(filepath, raw)
        _run_hook('pre', 'Edit', filepath)
        self.assertEqual(_read_file_bytes(filepath), raw)

    def test_utf8bom_bytes_unchanged(self):
        filepath = os.path.join(self.project_dir, 'install.nsi')
        raw = _make_utf8bom_content()
        _write_file_bytes(filepath, raw)
        _run_hook('pre', 'Edit', filepath)
        self.assertEqual(_read_file_bytes(filepath), raw)

    def test_no_state_backup_created(self):
        """v3 must not create backup files next to the source."""
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_gbk_content())
        _run_hook('pre', 'Edit', filepath)
        entries = os.listdir(self.project_dir)
        self.assertEqual(entries, ['main.cpp'])


class TestPreReadInfo(unittest.TestCase):
    """Read on non-UTF-8 files is allowed but informs the model."""

    def setUp(self):
        self.project_dir = _create_temp_project()
        _clean_state()

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)
        _clean_state()

    def test_read_gbk_info(self):
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_gbk_content())
        code, out, _ = _run_hook('pre', 'Read', filepath)
        self.assertEqual(code, 0)
        self.assertIn('INFO', out)
        self.assertIn('encoding_utils.py', out)
        self.assertIn('read', out)
        self.assertIn('gbk', out)

    def test_read_utf8_silent(self):
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_utf8_content())
        code, out, _ = _run_hook('pre', 'Read', filepath)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), '')


class TestPrePassThrough(unittest.TestCase):
    """UTF-8 / ASCII / safe single-byte / non-monitored / new files pass."""

    def setUp(self):
        self.project_dir = _create_temp_project()
        _clean_state()

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)
        _clean_state()

    def test_edit_utf8_allowed(self):
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_utf8_content())
        code, out, _ = _run_hook('pre', 'Edit', filepath)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), '')

    def test_edit_ascii_allowed(self):
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, b'int main() { return 0; }\n')
        code, out, _ = _run_hook('pre', 'Edit', filepath)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), '')

    def test_edit_windows1252_allowed(self):
        """Western single-byte encodings are SAFE - no block."""
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, u'int x = 1; // café\n'.encode('windows-1252'))
        code, out, _ = _run_hook('pre', 'Edit', filepath)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), '')

    def test_edit_windows1251_blocked(self):
        """Cyrillic (windows-1251) is NOT safe - native edit would garble it."""
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, u'// Привет мир, тестовая строка\nint x = 1;\n'.encode('windows-1251'))
        code, out, _ = _run_hook('pre', 'Edit', filepath)
        self.assertEqual(code, 2)
        self.assertIn('BLOCKED', out)
        self.assertIn('windows-1251', out)

    def test_non_monitored_extension_ignored(self):
        """.txt is not monitored - GBK file passes through silently."""
        filepath = os.path.join(self.project_dir, 'notes.txt')
        _write_file_bytes(filepath, _make_gbk_content())
        code, out, _ = _run_hook('pre', 'Edit', filepath)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), '')

    def test_new_file_write_allowed(self):
        """Write to a non-existent file (creation) must not be blocked."""
        filepath = os.path.join(self.project_dir, 'new.cpp')
        code, out, _ = _run_hook('pre', 'Write', filepath)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), '')

    def test_no_file_path_allowed(self):
        code, out, _ = _run_hook('pre', 'Edit', '')
        self.assertEqual(code, 0)


class TestDetectionCache(unittest.TestCase):
    """Same-file consecutive calls reuse the cached encoding (skip detection)."""

    def setUp(self):
        self.project_dir = _create_temp_project()
        _clean_state()

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)
        _clean_state()

    def test_second_call_skips_detection(self):
        """Unchanged file: second pre must not call detect_encoding again."""
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_gbk_content())
        calls = {'n': 0}
        orig_detect = encoding_utils.detect_encoding

        def counting_detect(path):
            calls['n'] += 1
            return orig_detect(path)

        encoding_utils.detect_encoding = counting_detect
        try:
            _run_hook_inprocess('pre', 'Edit', filepath)  # first: detects
            _run_hook_inprocess('pre', 'Edit', filepath)  # second: cache hit
            _run_hook_inprocess('pre', 'Read', filepath)  # third: cache hit
        finally:
            encoding_utils.detect_encoding = orig_detect
        self.assertEqual(calls['n'], 1)

    def test_cache_invalidated_after_change(self):
        """File modified -> mtime/size differ -> detection runs again."""
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_gbk_content())
        calls = {'n': 0}
        orig_detect = encoding_utils.detect_encoding

        def counting_detect(path):
            calls['n'] += 1
            return orig_detect(path)

        encoding_utils.detect_encoding = counting_detect
        try:
            _run_hook_inprocess('pre', 'Edit', filepath)
            _write_file_bytes(filepath, _make_gbk_content() + b'// extra line\n')
            _run_hook_inprocess('pre', 'Edit', filepath)
        finally:
            encoding_utils.detect_encoding = orig_detect
        self.assertEqual(calls['n'], 2)

    def test_safe_file_clears_stale_state(self):
        """File rewritten as UTF-8 -> state dropped, no block."""
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_gbk_content())
        _run_hook('pre', 'Edit', filepath)  # block, saves state
        _write_file_bytes(filepath, _make_utf8_content())
        code, out, _ = _run_hook('pre', 'Edit', filepath)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), '')
        self.assertIsNone(encoding_transparent._load_state(filepath))


class TestPostEncodingChange(unittest.TestCase):
    """PostToolUse warns when a guarded file's encoding changed."""

    def setUp(self):
        self.project_dir = _create_temp_project()
        _clean_state()

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)
        _clean_state()

    def test_post_no_state_silent(self):
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_gbk_content())
        code, out, _ = _run_hook('post', 'Edit', filepath)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), '')

    def test_post_encoding_unchanged_silent(self):
        """pre then post with no change: state cleaned, no warning."""
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_gbk_content())
        _run_hook('pre', 'Edit', filepath)  # exit 2, but saves state
        self.assertTrue(encoding_transparent._load_state(filepath))
        code, out, _ = _run_hook('post', 'Edit', filepath)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), '')
        self.assertIsNone(encoding_transparent._load_state(filepath))

    def test_post_encoding_changed_warns(self):
        """GBK -> UTF-8 rewrite by a native tool: warn + restore commands."""
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_gbk_content())
        _run_hook('pre', 'Edit', filepath)
        # Simulate a native tool rewriting the file as UTF-8
        _write_file_bytes(filepath, _make_utf8_content())
        code, out, _ = _run_hook('post', 'Edit', filepath)
        self.assertEqual(code, 0)
        self.assertIn('WARNING', out)
        self.assertIn('gbk', out)
        self.assertIn('convert', out)
        self.assertIsNone(encoding_transparent._load_state(filepath))

    def test_post_file_deleted_cleans_state(self):
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_gbk_content())
        _run_hook('pre', 'Edit', filepath)
        os.remove(filepath)
        code, out, _ = _run_hook('post', 'Edit', filepath)
        self.assertEqual(code, 0)
        self.assertIsNone(encoding_transparent._load_state(filepath))


class TestRecover(unittest.TestCase):
    """recover only cleans state files; never touches project files."""

    def setUp(self):
        self.project_dir = _create_temp_project()
        _clean_state()

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)
        _clean_state()

    def test_recover_cleans_state(self):
        script = os.path.join(_SCRIPT_DIR, 'encoding_transparent.py')
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_gbk_content())
        _run_hook('pre', 'Edit', filepath)
        self.assertTrue(os.listdir(encoding_transparent.STATE_DIR))
        proc = subprocess.Popen(
            [sys.executable, script, 'recover'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, _ = proc.communicate()
        self.assertEqual(proc.returncode, 0)
        self.assertIn('Cleaned', stdout.decode('utf-8', errors='replace'))
        # Source file untouched
        self.assertEqual(_read_file_bytes(filepath), _make_gbk_content())

    def test_recover_empty(self):
        script = os.path.join(_SCRIPT_DIR, 'encoding_transparent.py')
        proc = subprocess.Popen(
            [sys.executable, script, 'recover'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, _ = proc.communicate()
        self.assertEqual(proc.returncode, 0)


class TestMalformedInput(unittest.TestCase):
    """Fail-open on malformed stdin."""

    def test_bad_json_exit_zero(self):
        script = os.path.join(_SCRIPT_DIR, 'encoding_transparent.py')
        proc = subprocess.Popen(
            [sys.executable, script, 'pre'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, _ = proc.communicate(b'not json {{{')
        self.assertEqual(proc.returncode, 0)


if __name__ == '__main__':
    unittest.main()
