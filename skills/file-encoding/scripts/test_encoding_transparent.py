# -*- coding: utf-8 -*-
"""Tests for encoding_transparent.py - the transparent encoding hook."""

from __future__ import print_function

import io
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
    """Create a temporary directory with a .git marker (simulates a project)."""
    d = tempfile.mkdtemp(prefix='enc_transparent_test_')
    os.makedirs(os.path.join(d, '.git'))
    return d


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


def _make_utf8bom_content():
    """Return bytes of a UTF-8 BOM file."""
    content = u'// Hello BOM\nint x = 1;\n'
    return b'\xef\xbb\xbf' + content.encode('utf-8')


def _make_utf16le_content():
    """Return bytes of a UTF-16 LE BOM file."""
    content = u'[Section]\nkey=value\n'
    return b'\xff\xfe' + content.encode('utf-16-le')


def _run_hook(mode, tool_name, file_path, tool_response=None):
    """Run encoding_transparent.py with given mode and tool input.

    Returns (exit_code, stdout, stderr).
    """
    script = os.path.join(_SCRIPT_DIR, 'encoding_transparent.py')
    data = {
        'tool_name': tool_name,
        'tool_input': {'file_path': file_path},
    }
    if tool_response is not None:
        data['tool_response'] = tool_response

    proc = subprocess.Popen(
        [sys.executable, script, mode],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = proc.communicate(json.dumps(data).encode('utf-8'))
    return proc.returncode, stdout.decode('utf-8', errors='replace'), stderr.decode('utf-8', errors='replace')


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPreToolUseConversion(unittest.TestCase):
    """Test that PreToolUse correctly converts non-UTF-8 files to UTF-8."""

    def setUp(self):
        self.project_dir = _create_temp_project()
        # Clear any leftover state
        if os.path.isdir(encoding_transparent.STATE_DIR):
            shutil.rmtree(encoding_transparent.STATE_DIR)

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)
        if os.path.isdir(encoding_transparent.STATE_DIR):
            shutil.rmtree(encoding_transparent.STATE_DIR)

    def test_gbk_file_converted_to_utf8(self):
        """GBK file should be converted to UTF-8 by Pre hook."""
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_gbk_content())

        rc, stdout, stderr = _run_hook('pre', 'Edit', filepath)
        self.assertEqual(rc, 0)

        # File should now be valid UTF-8
        raw = _read_file_bytes(filepath)
        content = raw.decode('utf-8')
        self.assertIn(u'你好', content)  # 你好

        # State file should exist
        state = encoding_transparent._load_state(filepath)
        self.assertIsNotNone(state)
        self.assertEqual(state['encoding'], 'gbk')

    def test_utf8bom_file_converted_to_plain_utf8(self):
        """UTF-8 BOM file should be converted to plain UTF-8 (BOM stripped)."""
        filepath = os.path.join(self.project_dir, 'test.nsi')
        _write_file_bytes(filepath, _make_utf8bom_content())

        rc, stdout, stderr = _run_hook('pre', 'Read', filepath)
        self.assertEqual(rc, 0)

        # File should be plain UTF-8 without BOM
        raw = _read_file_bytes(filepath)
        self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))
        content = raw.decode('utf-8')
        self.assertIn('Hello BOM', content)

        state = encoding_transparent._load_state(filepath)
        self.assertIsNotNone(state)
        self.assertEqual(state['encoding'], 'utf-8-bom')

    def test_utf16le_file_converted_to_utf8(self):
        """UTF-16 LE BOM file should be converted to UTF-8."""
        filepath = os.path.join(self.project_dir, 'config.ini')
        _write_file_bytes(filepath, _make_utf16le_content())

        rc, stdout, stderr = _run_hook('pre', 'Read', filepath)
        self.assertEqual(rc, 0)

        raw = _read_file_bytes(filepath)
        # Should NOT start with UTF-16 BOM
        self.assertFalse(raw.startswith(b'\xff\xfe'))
        content = raw.decode('utf-8')
        self.assertIn('[Section]', content)
        self.assertIn('key=value', content)

        state = encoding_transparent._load_state(filepath)
        self.assertIsNotNone(state)
        self.assertEqual(state['encoding'], 'utf-16-le-bom')

    def test_utf8_file_not_converted(self):
        """Pure UTF-8 file should pass through without conversion."""
        filepath = os.path.join(self.project_dir, 'clean.cpp')
        content = u'// Pure ASCII\nint main() {}\n'
        _write_file_bytes(filepath, content.encode('utf-8'))

        rc, stdout, stderr = _run_hook('pre', 'Edit', filepath)
        self.assertEqual(rc, 0)

        # No state file should be created
        state = encoding_transparent._load_state(filepath)
        self.assertIsNone(state)

        # File should be unchanged
        raw = _read_file_bytes(filepath)
        self.assertEqual(raw, content.encode('utf-8'))

    def test_non_monitored_extension_skipped(self):
        """Files with non-monitored extensions should pass through."""
        filepath = os.path.join(self.project_dir, 'main.py')
        content = b'# Python file\n'
        _write_file_bytes(filepath, content)

        rc, stdout, stderr = _run_hook('pre', 'Edit', filepath)
        self.assertEqual(rc, 0)

        state = encoding_transparent._load_state(filepath)
        self.assertIsNone(state)

    def test_file_outside_project_still_converted(self):
        """Files outside project roots should still be converted (no project check)."""
        tmp = tempfile.mkdtemp(prefix='enc_no_project_')
        try:
            filepath = os.path.join(tmp, 'test.cpp')
            _write_file_bytes(filepath, _make_gbk_content())

            rc, stdout, stderr = _run_hook('pre', 'Edit', filepath)
            self.assertEqual(rc, 0)

            # Should be converted (project check removed)
            state = encoding_transparent._load_state(filepath)
            self.assertIsNotNone(state)
        finally:
            # Clean up state
            encoding_transparent._remove_state(filepath)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_new_file_write_passes_through(self):
        """Write to a non-existent file should pass through (new file creation)."""
        filepath = os.path.join(self.project_dir, 'new_file.cpp')
        # File does not exist

        rc, stdout, stderr = _run_hook('pre', 'Write', filepath)
        self.assertEqual(rc, 0)

        state = encoding_transparent._load_state(filepath)
        self.assertIsNone(state)

    def test_already_converted_not_double_converted(self):
        """If state already exists, Pre should skip re-conversion."""
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_gbk_content())

        # First conversion
        rc, _, _ = _run_hook('pre', 'Read', filepath)
        self.assertEqual(rc, 0)

        # File is now UTF-8; record the content
        utf8_content = _read_file_bytes(filepath)

        # Second Pre call (e.g. Edit after Read) — should skip
        rc, _, _ = _run_hook('pre', 'Edit', filepath)
        self.assertEqual(rc, 0)

        # File should still be the same UTF-8 content (not double-converted)
        self.assertEqual(_read_file_bytes(filepath), utf8_content)


class TestPostToolUseRestore(unittest.TestCase):
    """Test that PostToolUse correctly restores original encoding."""

    def setUp(self):
        self.project_dir = _create_temp_project()
        if os.path.isdir(encoding_transparent.STATE_DIR):
            shutil.rmtree(encoding_transparent.STATE_DIR)

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)
        if os.path.isdir(encoding_transparent.STATE_DIR):
            shutil.rmtree(encoding_transparent.STATE_DIR)

    def test_gbk_restored_after_edit(self):
        """After Edit, file should be restored to GBK."""
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_gbk_content())

        # Pre: convert to UTF-8
        _run_hook('pre', 'Edit', filepath)

        # Simulate Edit: modify the UTF-8 file
        raw = _read_file_bytes(filepath)
        content = raw.decode('utf-8')
        content = content.replace(u'你好', u'世界')  # 你好 -> 世界
        _write_file_bytes(filepath, content.encode('utf-8'))

        # Post: convert back to GBK
        rc, stdout, stderr = _run_hook('post', 'Edit', filepath)
        self.assertEqual(rc, 0)

        # Verify file is GBK with the new content
        raw = _read_file_bytes(filepath)
        decoded = raw.decode('gbk')
        self.assertIn(u'世界', decoded)  # 世界
        self.assertNotIn(u'你好', decoded)  # 你好 removed

        # State should be cleaned up
        state = encoding_transparent._load_state(filepath)
        self.assertIsNone(state)

    def test_utf8bom_restored_after_edit(self):
        """After Edit, file should be restored to UTF-8 BOM."""
        filepath = os.path.join(self.project_dir, 'script.nsi')
        _write_file_bytes(filepath, _make_utf8bom_content())

        # Pre: strip BOM, convert to plain UTF-8
        _run_hook('pre', 'Edit', filepath)

        # Simulate Edit: modify content
        raw = _read_file_bytes(filepath)
        content = raw.decode('utf-8')
        content = content.replace('Hello BOM', 'Modified BOM')
        _write_file_bytes(filepath, content.encode('utf-8'))

        # Post: restore BOM
        rc, stdout, stderr = _run_hook('post', 'Edit', filepath)
        self.assertEqual(rc, 0)

        # Verify BOM is back
        raw = _read_file_bytes(filepath)
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))
        content = raw[3:].decode('utf-8')
        self.assertIn('Modified BOM', content)

    def test_utf16le_restored_after_edit(self):
        """After Edit, file should be restored to UTF-16 LE BOM."""
        filepath = os.path.join(self.project_dir, 'config.ini')
        _write_file_bytes(filepath, _make_utf16le_content())

        # Pre: convert to UTF-8
        _run_hook('pre', 'Edit', filepath)

        # Simulate Edit: modify content
        raw = _read_file_bytes(filepath)
        content = raw.decode('utf-8')
        content = content.replace('key=value', 'key=newvalue')
        _write_file_bytes(filepath, content.encode('utf-8'))

        # Post: restore to UTF-16 LE BOM
        rc, stdout, stderr = _run_hook('post', 'Edit', filepath)
        self.assertEqual(rc, 0)

        # Verify UTF-16 LE BOM
        raw = _read_file_bytes(filepath)
        self.assertTrue(raw.startswith(b'\xff\xfe'))
        content = raw.decode('utf-16-le')
        # Skip BOM character
        if content and content[0] == u'﻿':
            content = content[1:]
        self.assertIn('key=newvalue', content)

    def test_read_only_restores_without_modification(self):
        """After Read (no modification), file should be restored unchanged."""
        filepath = os.path.join(self.project_dir, 'main.cpp')
        original_bytes = _make_gbk_content()
        _write_file_bytes(filepath, original_bytes)

        # Pre: convert to UTF-8
        _run_hook('pre', 'Read', filepath)
        # Post: convert back (no modification happened)
        _run_hook('post', 'Read', filepath)

        # File should be identical to original
        self.assertEqual(_read_file_bytes(filepath), original_bytes)

    def test_no_state_file_no_action(self):
        """Post with no state file should do nothing."""
        filepath = os.path.join(self.project_dir, 'clean.cpp')
        content = b'// UTF-8 file\n'
        _write_file_bytes(filepath, content)

        rc, stdout, stderr = _run_hook('post', 'Edit', filepath)
        self.assertEqual(rc, 0)

        # File unchanged
        self.assertEqual(_read_file_bytes(filepath), content)

    def test_deleted_file_cleans_up_state(self):
        """If file was deleted by tool, Post should just clean up state."""
        filepath = os.path.join(self.project_dir, 'temp.cpp')
        _write_file_bytes(filepath, _make_gbk_content())

        # Pre: convert
        _run_hook('pre', 'Edit', filepath)
        state = encoding_transparent._load_state(filepath)
        self.assertIsNotNone(state)

        # Simulate tool deleting the file
        os.remove(filepath)

        # Post: should clean up state without error
        rc, stdout, stderr = _run_hook('post', 'Edit', filepath)
        self.assertEqual(rc, 0)

        state = encoding_transparent._load_state(filepath)
        self.assertIsNone(state)


class TestFullRoundTrip(unittest.TestCase):
    """End-to-end tests simulating the full Pre -> Tool -> Post cycle."""

    def setUp(self):
        self.project_dir = _create_temp_project()
        if os.path.isdir(encoding_transparent.STATE_DIR):
            shutil.rmtree(encoding_transparent.STATE_DIR)

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)
        if os.path.isdir(encoding_transparent.STATE_DIR):
            shutil.rmtree(encoding_transparent.STATE_DIR)

    def test_gbk_edit_roundtrip_content_preserved(self):
        """Full cycle: GBK file edited via UTF-8, encoding and content preserved."""
        filepath = os.path.join(self.project_dir, 'src.cpp')
        original = u'// 测试文件\nint x = 1;\nint y = 2;\n'
        _write_file_bytes(filepath, original.encode('gbk'))

        # Pre
        _run_hook('pre', 'Edit', filepath)

        # Verify it's UTF-8 now
        raw = _read_file_bytes(filepath)
        self.assertEqual(raw.decode('utf-8'), original)

        # Simulate Edit: change "int x = 1" to "int x = 42"
        new_content = original.replace(u'int x = 1', u'int x = 42')
        _write_file_bytes(filepath, new_content.encode('utf-8'))

        # Post
        _run_hook('post', 'Edit', filepath)

        # Verify: GBK encoding, new content
        raw = _read_file_bytes(filepath)
        decoded = raw.decode('gbk')
        self.assertEqual(decoded, new_content)
        self.assertIn(u'测试', decoded)  # 测试 still there
        self.assertIn('int x = 42', decoded)

    def test_crlf_preserved_through_roundtrip(self):
        """CRLF line endings should be preserved through conversion cycle."""
        filepath = os.path.join(self.project_dir, 'win.cpp')
        content = u'// 中文\r\nint main() {\r\n    return 0;\r\n}\r\n'
        _write_file_bytes(filepath, content.encode('gbk'))

        # Pre
        _run_hook('pre', 'Edit', filepath)

        # Check that CRLF is preserved in UTF-8 version
        raw = _read_file_bytes(filepath)
        utf8_content = raw.decode('utf-8')
        self.assertIn(u'\r\n', utf8_content)
        self.assertNotIn(u'\n\n', utf8_content.replace(u'\r\n', u'X'))

        # Post (no modification)
        _run_hook('post', 'Edit', filepath)

        # Verify original bytes preserved exactly
        self.assertEqual(_read_file_bytes(filepath), content.encode('gbk'))

    def test_multiple_read_edit_cycles(self):
        """Multiple Pre/Post cycles should work correctly."""
        filepath = os.path.join(self.project_dir, 'multi.cpp')
        _write_file_bytes(filepath, _make_gbk_content())

        # Cycle 1: Read
        _run_hook('pre', 'Read', filepath)
        _run_hook('post', 'Read', filepath)

        # Cycle 2: Edit
        _run_hook('pre', 'Edit', filepath)
        raw = _read_file_bytes(filepath)
        content = raw.decode('utf-8')
        content += u'// added line\n'
        _write_file_bytes(filepath, content.encode('utf-8'))
        _run_hook('post', 'Edit', filepath)

        # Verify still GBK with the addition
        raw = _read_file_bytes(filepath)
        decoded = raw.decode('gbk')
        self.assertIn(u'你好', decoded)
        self.assertIn('// added line', decoded)


class TestWriteOverwrite(unittest.TestCase):
    """Test Write tool overwriting existing non-UTF-8 files."""

    def setUp(self):
        self.project_dir = _create_temp_project()
        if os.path.isdir(encoding_transparent.STATE_DIR):
            shutil.rmtree(encoding_transparent.STATE_DIR)

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)
        if os.path.isdir(encoding_transparent.STATE_DIR):
            shutil.rmtree(encoding_transparent.STATE_DIR)

    def test_write_overwrite_existing_gbk_file(self):
        """Write tool completely replacing a GBK file should preserve encoding."""
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_gbk_content())

        # Pre(Write): converts existing file to UTF-8
        rc, _, _ = _run_hook('pre', 'Write', filepath)
        self.assertEqual(rc, 0)

        # Simulate Write tool: completely replace content with new UTF-8 text
        new_content = u'// 全新内容\nint main() { return 42; }\n'
        _write_file_bytes(filepath, new_content.encode('utf-8'))

        # Post(Write): convert back to GBK
        rc, _, _ = _run_hook('post', 'Write', filepath)
        self.assertEqual(rc, 0)

        # Verify file is GBK with entirely new content
        raw = _read_file_bytes(filepath)
        decoded = raw.decode('gbk')
        self.assertIn(u'全新内容', decoded)
        self.assertIn('return 42', decoded)
        # Old content should be gone
        self.assertNotIn(u'你好', decoded)

        # State cleaned up
        state = encoding_transparent._load_state(filepath)
        self.assertIsNone(state)

    def test_read_then_write_overwrite(self):
        """Read followed by Write (full rewrite) should work correctly."""
        filepath = os.path.join(self.project_dir, 'src.cpp')
        original = u'// 原始代码\nint x = 1;\n'
        _write_file_bytes(filepath, original.encode('gbk'))

        # Cycle 1: Read
        _run_hook('pre', 'Read', filepath)
        # Claude reads the UTF-8 content
        raw = _read_file_bytes(filepath)
        read_content = raw.decode('utf-8')
        self.assertIn(u'原始代码', read_content)
        _run_hook('post', 'Read', filepath)

        # Cycle 2: Write (complete replacement based on what was read)
        _run_hook('pre', 'Write', filepath)
        # Write tool replaces entire file with new content
        new_content = read_content.replace(u'int x = 1', u'int x = 100') + u'// 追加注释\n'
        _write_file_bytes(filepath, new_content.encode('utf-8'))
        _run_hook('post', 'Write', filepath)

        # Verify: GBK encoding, new content
        raw = _read_file_bytes(filepath)
        decoded = raw.decode('gbk')
        self.assertIn(u'原始代码', decoded)
        self.assertIn('int x = 100', decoded)
        self.assertIn(u'追加注释', decoded)


class TestRecovery(unittest.TestCase):
    """Test crash recovery mechanism."""

    def setUp(self):
        self.project_dir = _create_temp_project()
        if os.path.isdir(encoding_transparent.STATE_DIR):
            shutil.rmtree(encoding_transparent.STATE_DIR)

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)
        if os.path.isdir(encoding_transparent.STATE_DIR):
            shutil.rmtree(encoding_transparent.STATE_DIR)

    def test_recover_restores_file(self):
        """Recovery should convert file back from UTF-8 to original encoding."""
        filepath = os.path.join(self.project_dir, 'crash.cpp')
        _write_file_bytes(filepath, _make_gbk_content())

        # Simulate Pre without Post (crash scenario)
        _run_hook('pre', 'Edit', filepath)
        # File is now UTF-8, state exists

        # Run recovery
        script = os.path.join(_SCRIPT_DIR, 'encoding_transparent.py')
        proc = subprocess.Popen(
            [sys.executable, script, 'recover'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        stdout, stderr = proc.communicate()
        self.assertEqual(proc.returncode, 0)
        self.assertIn(b'Recovered', stdout)

        # File should be back to GBK
        raw = _read_file_bytes(filepath)
        decoded = raw.decode('gbk')
        self.assertIn(u'你好', decoded)

        # State should be cleaned up
        state = encoding_transparent._load_state(filepath)
        self.assertIsNone(state)

    def test_recover_handles_deleted_file(self):
        """Recovery should clean up state for files that no longer exist."""
        filepath = os.path.join(self.project_dir, 'gone.cpp')
        _write_file_bytes(filepath, _make_gbk_content())

        # Simulate Pre
        _run_hook('pre', 'Edit', filepath)
        # Delete the file (simulating external deletion)
        os.remove(filepath)

        # Run recovery
        script = os.path.join(_SCRIPT_DIR, 'encoding_transparent.py')
        proc = subprocess.Popen(
            [sys.executable, script, 'recover'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        stdout, stderr = proc.communicate()
        self.assertEqual(proc.returncode, 0)

        # State should be cleaned up
        state = encoding_transparent._load_state(filepath)
        self.assertIsNone(state)

    def test_recover_no_state_files(self):
        """Recovery with no state files should report nothing to do."""
        script = os.path.join(_SCRIPT_DIR, 'encoding_transparent.py')
        proc = subprocess.Popen(
            [sys.executable, script, 'recover'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        stdout, stderr = proc.communicate()
        self.assertEqual(proc.returncode, 0)
        self.assertIn(b'No state files found', stdout)


class TestEdgeCases(unittest.TestCase):
    """Edge cases and error handling."""

    def setUp(self):
        self.project_dir = _create_temp_project()
        if os.path.isdir(encoding_transparent.STATE_DIR):
            shutil.rmtree(encoding_transparent.STATE_DIR)

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)
        if os.path.isdir(encoding_transparent.STATE_DIR):
            shutil.rmtree(encoding_transparent.STATE_DIR)

    def test_non_edit_write_read_tool_passes_through(self):
        """Tools other than Edit/Write/Read should pass through."""
        filepath = os.path.join(self.project_dir, 'main.cpp')
        _write_file_bytes(filepath, _make_gbk_content())

        script = os.path.join(_SCRIPT_DIR, 'encoding_transparent.py')
        data = json.dumps({
            'tool_name': 'Bash',
            'tool_input': {'command': 'ls'},
        })
        proc = subprocess.Popen(
            [sys.executable, script, 'pre'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        stdout, stderr = proc.communicate(data.encode('utf-8'))
        self.assertEqual(proc.returncode, 0)

    def test_empty_file_path_passes_through(self):
        """Empty file_path in tool_input should pass through."""
        rc, stdout, stderr = _run_hook('pre', 'Edit', '')
        self.assertEqual(rc, 0)

    def test_malformed_stdin_fails_open(self):
        """Malformed JSON on stdin should fail open (exit 0)."""
        script = os.path.join(_SCRIPT_DIR, 'encoding_transparent.py')
        proc = subprocess.Popen(
            [sys.executable, script, 'pre'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        stdout, stderr = proc.communicate(b'not json at all')
        self.assertEqual(proc.returncode, 0)

    def test_binary_file_passes_through(self):
        """Binary files should pass through without conversion."""
        filepath = os.path.join(self.project_dir, 'data.rc')
        # Create a file with null bytes (binary)
        _write_file_bytes(filepath, b'\x00\x01\x02\x03' * 200)

        rc, stdout, stderr = _run_hook('pre', 'Edit', filepath)
        self.assertEqual(rc, 0)

        state = encoding_transparent._load_state(filepath)
        self.assertIsNone(state)


class TestPostFailureRecovery(unittest.TestCase):
    """Test automatic recovery when Post conversion fails."""

    def setUp(self):
        self.project_dir = _create_temp_project()
        if os.path.isdir(encoding_transparent.STATE_DIR):
            shutil.rmtree(encoding_transparent.STATE_DIR)

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)
        if os.path.isdir(encoding_transparent.STATE_DIR):
            shutil.rmtree(encoding_transparent.STATE_DIR)

    def test_post_failure_restores_from_backup(self):
        """If Post can't encode back, file should be restored from backup."""
        filepath = os.path.join(self.project_dir, 'fail.cpp')
        original = u'// 测试文件\nint x = 1;\n'
        original_bytes = original.encode('gbk')
        _write_file_bytes(filepath, original_bytes)

        # Pre: convert to UTF-8
        _run_hook('pre', 'Edit', filepath)

        # Simulate Claude writing emoji (not representable in GBK)
        bad_content = u'// 测试文件 \U0001f600\nint x = 1;\n'
        _write_file_bytes(filepath, bad_content.encode('utf-8'))

        # Post: should fail to encode, then restore from backup
        rc, stdout, stderr = _run_hook('post', 'Edit', filepath)
        self.assertEqual(rc, 0)
        self.assertIn('WARNING', stdout)
        self.assertIn('backup', stdout.lower())

        # File should be restored to original GBK bytes
        raw = _read_file_bytes(filepath)
        self.assertEqual(raw, original_bytes)

    def test_backup_cleaned_up_on_success(self):
        """Backup file should be removed after successful Post."""
        filepath = os.path.join(self.project_dir, 'clean.cpp')
        _write_file_bytes(filepath, _make_gbk_content())

        _run_hook('pre', 'Edit', filepath)
        # Don't modify — Post should succeed
        _run_hook('post', 'Edit', filepath)

        # Backup should be cleaned up
        backup = encoding_transparent._backup_path(filepath)
        self.assertFalse(os.path.exists(backup))


class TestNewFileEncodingInheritance(unittest.TestCase):
    """Test that new files inherit encoding from sibling files."""

    def setUp(self):
        self.project_dir = _create_temp_project()
        if os.path.isdir(encoding_transparent.STATE_DIR):
            shutil.rmtree(encoding_transparent.STATE_DIR)

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)
        if os.path.isdir(encoding_transparent.STATE_DIR):
            shutil.rmtree(encoding_transparent.STATE_DIR)

    def test_new_file_inherits_gbk_from_siblings(self):
        """New .cpp file should inherit GBK encoding from sibling .cpp files."""
        # Create 2 GBK sibling files
        for name in ['a.cpp', 'b.cpp']:
            path = os.path.join(self.project_dir, name)
            _write_file_bytes(path, _make_gbk_content())

        # Create new file (Write tool creates UTF-8)
        new_file = os.path.join(self.project_dir, 'new.cpp')
        new_content = u'// 新文件\nint z = 3;\n'
        _write_file_bytes(new_file, new_content.encode('utf-8'))

        # Post(Write): should detect siblings are GBK and convert
        rc, stdout, stderr = _run_hook('post', 'Write', new_file)
        self.assertEqual(rc, 0)
        self.assertIn('inherited', stdout.lower())

        # Verify file is now GBK
        raw = _read_file_bytes(new_file)
        decoded = raw.decode('gbk')
        self.assertIn(u'新文件', decoded)

    def test_new_file_no_siblings_stays_utf8(self):
        """New file with no non-UTF-8 siblings should stay UTF-8."""
        # No sibling files with same extension
        new_file = os.path.join(self.project_dir, 'only.h')
        content = u'#pragma once\n'
        _write_file_bytes(new_file, content.encode('utf-8'))

        # Post(Write): no siblings to inherit from
        rc, stdout, stderr = _run_hook('post', 'Write', new_file)
        self.assertEqual(rc, 0)

        # File should remain UTF-8
        raw = _read_file_bytes(new_file)
        self.assertEqual(raw.decode('utf-8'), content)


if __name__ == '__main__':
    unittest.main()
