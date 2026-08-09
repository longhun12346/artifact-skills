# -*- coding: utf-8 -*-
"""Tests for install_deps.py - dependency bootstrap (charset-normalizer etc.)."""

import os
import shutil
import sys
import tempfile
import unittest

try:
    from unittest import mock
except ImportError:
    mock = None  # very old Python without backport

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import install_deps


class TestDependencyBootstrap(unittest.TestCase):
    """ensure_deps installs missing detection packages, never raises."""

    @unittest.skipIf(mock is None, 'mock not available')
    def test_missing_package_triggers_pip(self):
        """charset_normalizer missing -> pip install attempted."""
        with mock.patch.object(install_deps, '_importable', return_value=False), \
             mock.patch.object(install_deps, '_pip_install', return_value=(True, 'pip install x')) as m_install:
            rc = install_deps.ensure_deps()
        self.assertEqual(rc, 0)
        self.assertEqual(m_install.call_count, 2)  # charset-normalizer + chardet

    @unittest.skipIf(mock is None, 'mock not available')
    def test_installed_package_skips_pip(self):
        with mock.patch.object(install_deps, '_importable', return_value=True), \
             mock.patch.object(install_deps, '_pip_install') as m_install:
            rc = install_deps.ensure_deps()
        self.assertEqual(rc, 0)
        m_install.assert_not_called()

    @unittest.skipIf(mock is None, 'mock not available')
    def test_install_failure_non_fatal(self):
        """pip missing -> warning only, exit 0."""
        with mock.patch.object(install_deps, '_importable', return_value=False), \
             mock.patch.object(install_deps, '_pip_install', return_value=(False, 'pip install x')):
            rc = install_deps.ensure_deps()  # must not raise
        self.assertEqual(rc, 0)

    @unittest.skipIf(mock is None, 'mock not available')
    def test_pip_install_fallback_strategies(self):
        fake_proc = mock.Mock(returncode=0)
        with mock.patch('subprocess.Popen', return_value=fake_proc) as m_popen:
            ok, detail = install_deps._pip_install('charset-normalizer')
        self.assertTrue(ok)
        self.assertEqual(m_popen.call_count, 1)  # first strategy succeeded
        self.assertIn('python', detail)

    @unittest.skipIf(mock is None, 'mock not available')
    def test_pip_install_all_strategies_fail(self):
        with mock.patch('subprocess.Popen', side_effect=OSError('no pip')):
            ok, detail = install_deps._pip_install('x')
        self.assertFalse(ok)
        self.assertTrue(detail)

    @unittest.skipIf(mock is None, 'mock not available')
    def test_check_exits_1_when_missing(self):
        """--check exits 1 when dependencies are missing."""
        with mock.patch.object(install_deps, '_importable', return_value=False):
            with self.assertRaises(SystemExit) as ctx:
                install_deps.main(['--check'])
        self.assertEqual(ctx.exception.code, 1)

    @unittest.skipIf(mock is None, 'mock not available')
    def test_check_exits_0_when_ok(self):
        with mock.patch.object(install_deps, '_importable', return_value=True):
            with self.assertRaises(SystemExit) as ctx:
                install_deps.main(['--check'])
        self.assertEqual(ctx.exception.code, 0)


if __name__ == '__main__':
    unittest.main()
