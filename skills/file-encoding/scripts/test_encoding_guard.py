# -*- coding: utf-8 -*-
"""Tests for encoding_guard.py -- compatible with Python 2.6+ and 3.x.

Usage:
  python test_encoding_guard.py
  python -m pytest test_encoding_guard.py  # if pytest available
"""

from __future__ import print_function
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
GUARD_SCRIPT = os.path.join(SCRIPTS_DIR, 'encoding_guard.py')


# ---------------------------------------------------------------------------
# Helper: run the hook as a subprocess
# ---------------------------------------------------------------------------

def run_hook(tool_name, file_path):
    """Return (exit_code, stdout_text)."""
    data = json.dumps({'tool_name': tool_name,
                       'tool_input': {'file_path': file_path}})
    proc = subprocess.Popen(
        [sys.executable, GUARD_SCRIPT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout, _ = proc.communicate(input=data.encode('utf-8'))
    except TypeError:
        stdout, _ = proc.communicate(data.encode('utf-8'))
    return proc.returncode, stdout.decode('utf-8', errors='replace')


# ---------------------------------------------------------------------------
# In-process import (faster for unit tests)
# ---------------------------------------------------------------------------

sys.path.insert(0, SCRIPTS_DIR)
import encoding_guard as eg


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class TempProject(object):
    """Context manager: temp dir with a .git marker (simulates project root)."""

    def __enter__(self):
        self.root = tempfile.mkdtemp(prefix='guard_proj_')
        os.makedirs(os.path.join(self.root, '.git'))
        return self.root

    def __exit__(self, *_):
        shutil.rmtree(self.root, ignore_errors=True)


class TempDir(object):
    """Context manager: plain temp dir without any project markers."""

    def __enter__(self):
        self.root = tempfile.mkdtemp(prefix='guard_tmp_')
        return self.root

    def __exit__(self, *_):
        shutil.rmtree(self.root, ignore_errors=True)


def write_raw(path, raw_bytes):
    with open(path, 'wb') as f:
        f.write(raw_bytes)


# ---------------------------------------------------------------------------
# Unit tests: _has_nonascii()
# ---------------------------------------------------------------------------

class TestHasNonAscii(unittest.TestCase):

    def _temp(self, raw_bytes):
        fd, path = tempfile.mkstemp()
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(raw_bytes)
        except Exception:
            os.close(fd)
            raise
        return path

    def test_ascii_only(self):
        path = self._temp(b'int main() { return 0; }\n')
        try:
            self.assertFalse(eg._has_nonascii(path))
        finally:
            os.unlink(path)

    def test_gbk_chinese(self):
        path = self._temp(u'// \u6ce8\u91ca'.encode('gbk'))
        try:
            self.assertTrue(eg._has_nonascii(path))
        finally:
            os.unlink(path)

    def test_utf16_le_bom(self):
        path = self._temp(b'\xff\xfe' + u'hello'.encode('utf-16-le'))
        try:
            self.assertTrue(eg._has_nonascii(path))
        finally:
            os.unlink(path)

    def test_empty_file(self):
        path = self._temp(b'')
        try:
            self.assertFalse(eg._has_nonascii(path))
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Unit tests: _in_project()
# ---------------------------------------------------------------------------

class TestInProject(unittest.TestCase):

    def test_git_marker(self):
        with TempProject() as root:
            target = os.path.join(root, 'src', 'foo.cpp')
            os.makedirs(os.path.dirname(target))
            self.assertTrue(eg._in_project(target))

    def test_no_marker(self):
        with TempDir() as root:
            target = os.path.join(root, 'foo.cpp')
            self.assertFalse(eg._in_project(target))

    def test_cmake_marker(self):
        with TempDir() as root:
            open(os.path.join(root, 'CMakeLists.txt'), 'w').close()
            target = os.path.join(root, 'sub', 'foo.cpp')
            os.makedirs(os.path.dirname(target))
            self.assertTrue(eg._in_project(target))

    def test_vcxproj_marker(self):
        with TempDir() as root:
            open(os.path.join(root, 'myapp.vcxproj'), 'w').close()
            target = os.path.join(root, 'foo.h')
            self.assertTrue(eg._in_project(target))


# ---------------------------------------------------------------------------
# Integration tests: Read tool via subprocess
# ---------------------------------------------------------------------------

class TestReadToolHook(unittest.TestCase):

    def test_non_monitored_tool_allowed(self):
        with TempProject() as root:
            path = os.path.join(root, 'run.sh')
            write_raw(path, b'#!/bin/sh\n')
            code, _ = run_hook('Bash', path)
            self.assertEqual(code, 0)

    def test_non_monitored_extension_allowed(self):
        with TempProject() as root:
            path = os.path.join(root, 'notes.txt')
            write_raw(path, u'\u4e2d\u6587'.encode('gbk'))
            code, _ = run_hook('Read', path)
            self.assertEqual(code, 0)

    def test_outside_project_allowed(self):
        with TempDir() as root:
            path = os.path.join(root, 'temp.cpp')
            write_raw(path, u'// \u6ce8\u91ca\n'.encode('gbk'))
            code, _ = run_hook('Read', path)
            self.assertEqual(code, 0)

    def test_nonexistent_file_allowed(self):
        with TempProject() as root:
            path = os.path.join(root, 'ghost.cpp')
            code, _ = run_hook('Read', path)
            self.assertEqual(code, 0)

    def test_utf8_file_allowed(self):
        with TempProject() as root:
            path = os.path.join(root, 'main.cpp')
            write_raw(path, u'// comment\nint main(){}'.encode('utf-8'))
            code, _ = run_hook('Read', path)
            self.assertEqual(code, 0)

    def test_gbk_ascii_only_allowed(self):
        """GBK file with only ASCII bytes should not be blocked."""
        with TempProject() as root:
            path = os.path.join(root, 'ascii.cpp')
            write_raw(path, b'int x = 1; // no chinese\n')
            code, _ = run_hook('Read', path)
            self.assertEqual(code, 0)

    def test_utf16_le_bom_blocked(self):
        with TempProject() as root:
            path = os.path.join(root, 'config.ini')
            write_raw(path, b'\xff\xfe' + u'[section]\nkey=value\n'.encode('utf-16-le'))
            code, out = run_hook('Read', path)
            self.assertEqual(code, 2)
            self.assertIn('python $EU read', out)

    def test_gbk_with_chinese_blocked(self):
        with TempProject() as root:
            path = os.path.join(root, 'dialog.rc')
            write_raw(path, u'// \u5bf9\u8bdd\u6846\u8d44\u6e90\nIDD_DIALOG1\n'.encode('gbk'))
            code, out = run_hook('Read', path)
            self.assertEqual(code, 2)
            self.assertIn('python $EU read', out)

    def test_gbk_subdir_blocked(self):
        """File in a subdirectory of a project should still be blocked."""
        with TempProject() as root:
            subdir = os.path.join(root, 'src', 'ui')
            os.makedirs(subdir)
            path = os.path.join(subdir, 'main.cpp')
            write_raw(path, u'// \u4e3b\u7a97\u53e3\n'.encode('gbk'))
            code, out = run_hook('Read', path)
            self.assertEqual(code, 2)
            self.assertIn('python $EU read', out)


# ---------------------------------------------------------------------------
# Regression tests: Edit/Write tool (existing behaviour unchanged)
# ---------------------------------------------------------------------------

class TestEditWriteHook(unittest.TestCase):

    def test_edit_utf8_allowed(self):
        with TempProject() as root:
            path = os.path.join(root, 'util.cpp')
            write_raw(path, b'int foo() { return 1; }\n')
            code, _ = run_hook('Edit', path)
            self.assertEqual(code, 0)

    def test_edit_gbk_blocked(self):
        with TempProject() as root:
            path = os.path.join(root, 'res.rc')
            write_raw(path, u'// \u8d44\u6e90\u6587\u4ef6\n'.encode('gbk'))
            code, out = run_hook('Edit', path)
            self.assertEqual(code, 2)
            self.assertIn('safe-edit', out)

    def test_write_new_ini_blocked(self):
        """New .ini file should be blocked (expected utf-16-le-bom)."""
        with TempProject() as root:
            path = os.path.join(root, 'settings.ini')
            code, out = run_hook('Write', path)
            self.assertEqual(code, 2)
            self.assertIn('utf-16-le-bom', out)

    def test_edit_outside_project_allowed(self):
        with TempDir() as root:
            path = os.path.join(root, 'scratch.cpp')
            write_raw(path, u'// \u6d4b\u8bd5\n'.encode('gbk'))
            code, _ = run_hook('Edit', path)
            self.assertEqual(code, 0)


# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------

if __name__ == '__main__':
    unittest.main(verbosity=2)
