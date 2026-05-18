# -*- coding: utf-8 -*-
"""Tests for encoding_utils.py — compatible with Python 2.6+ and 3.x.

Usage:
  python test_encoding_utils.py
  python -m pytest test_encoding_utils.py  # if pytest available
"""

from __future__ import print_function
import io
import os
import sys
import tempfile
import unittest

# Add parent dir to path so we can import encoding_utils as module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import encoding_utils as eu


class TestDetectBOM(unittest.TestCase):

    def test_utf16_le_bom(self):
        self.assertEqual(eu._detect_bom(b'\xff\xfe\x00\x00'), 'utf-16-le-bom')

    def test_utf16_be_bom(self):
        self.assertEqual(eu._detect_bom(b'\xfe\xff\x00\x00'), 'utf-16-be-bom')

    def test_utf8_bom(self):
        self.assertEqual(eu._detect_bom(b'\xef\xbb\xbf\x00'), 'utf-8-bom')

    def test_no_bom(self):
        self.assertIsNone(eu._detect_bom(b'\x00\x00\x00\x00'))
        self.assertIsNone(eu._detect_bom(b'hello'))


class TestIsBinary(unittest.TestCase):

    def test_text(self):
        self.assertFalse(eu._is_binary(b'hello world\n'))

    def test_binary_null(self):
        self.assertTrue(eu._is_binary(b'PK\x03\x04\x00\x00'))

    def test_empty(self):
        self.assertFalse(eu._is_binary(b''))


class TestDetectEncoding(unittest.TestCase):

    def _write_temp(self, raw_bytes):
        fd, path = tempfile.mkstemp(suffix='.txt')
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(raw_bytes)
            return path
        finally:
            pass  # keep fd open, caller cleans up

    def test_utf8_no_bom(self):
        raw = u'hello world'.encode('utf-8')
        path = self._write_temp(raw)
        try:
            self.assertEqual(eu.detect_encoding(path), 'utf-8')
        finally:
            os.unlink(path)

    def test_utf8_bom(self):
        raw = b'\xef\xbb\xbf' + u'hello'.encode('utf-8')
        path = self._write_temp(raw)
        try:
            self.assertEqual(eu.detect_encoding(path), 'utf-8-bom')
        finally:
            os.unlink(path)

    def test_utf16_le_bom(self):
        raw = b'\xff\xfe' + u'hello world'.encode('utf-16-le')
        path = self._write_temp(raw)
        try:
            self.assertEqual(eu.detect_encoding(path), 'utf-16-le-bom')
        finally:
            os.unlink(path)

    def test_gbk_chinese(self):
        raw = u'hello 测试中文 world'.encode('gbk')
        path = self._write_temp(raw)
        try:
            self.assertEqual(eu.detect_encoding(path), 'gbk')
        finally:
            os.unlink(path)

    def test_binary_file(self):
        raw = b'PK\x03\x04' + b'\x00' * 100
        path = self._write_temp(raw)
        try:
            self.assertEqual(eu.detect_encoding(path), 'binary')
        finally:
            os.unlink(path)


class TestFriendlyToPython(unittest.TestCase):

    def test_gbk(self):
        self.assertEqual(eu._friendly_to_python('gbk'), 'gbk')

    def test_utf8_bom(self):
        self.assertEqual(eu._friendly_to_python('utf-8-bom'), 'utf-8-sig')

    def test_utf16_le_bom(self):
        self.assertEqual(eu._friendly_to_python('utf-16-le-bom'), 'utf-16')

    def test_unknown_passthrough(self):
        self.assertEqual(eu._friendly_to_python('cp936'), 'cp936')


class TestRoundTrip(unittest.TestCase):
    """Test that write+read preserves content for each encoding."""

    def _roundtrip(self, encoding, text):
        fd, path = tempfile.mkstemp(suffix='.txt')
        try:
            # Write
            if sys.version_info[0] == 2:
                stdin_content = text.encode('utf-8')
            else:
                stdin_content = text
            saved_stdin = sys.stdin
            try:
                if sys.version_info[0] == 2:
                    import StringIO
                    sys.stdin = StringIO.StringIO(stdin_content)
                else:
                    sys.stdin = io.StringIO(stdin_content)
                Args = type('Args', (), {'encoding': encoding, 'file': path})
                eu.cmd_write(Args())
            finally:
                sys.stdin = saved_stdin

            # Verify encoding detection
            detected = eu.detect_encoding(path)
            self.assertEqual(detected, encoding,
                             'Expected %s, got %s' % (encoding, detected))

            # Read back and verify content
            ReadArgs = type('ReadArgs', (), {'encoding': encoding, 'file': path})
            saved_stdout = sys.stdout
            try:
                if sys.version_info[0] == 2:
                    import StringIO
                    sys.stdout = StringIO.StringIO()
                else:
                    sys.stdout = io.StringIO()
                ret = eu.cmd_read(ReadArgs())
                self.assertEqual(ret, 0)
                result = sys.stdout.getvalue()
            finally:
                sys.stdout = saved_stdout

            if sys.version_info[0] == 2:
                result = result.decode('utf-8')
            self.assertEqual(result, text)
        finally:
            try:
                os.close(fd)
            except Exception:
                pass
            os.unlink(path)

    def test_utf8(self):
        self._roundtrip('utf-8', u'hello world\nline 2\n')

    def test_utf8_bom(self):
        self._roundtrip('utf-8-bom', u'hello world\n')

    def test_utf16_le_bom(self):
        self._roundtrip('utf-16-le-bom', u'hello unicode: \u4f60\u597d\n')

    def test_gbk_with_chinese(self):
        self._roundtrip('gbk', u'hello world: \u4f60\u597d\u4e16\u754c\n')


# ---------------------------------------------------------------------------
# Tests: safe-write command
# ---------------------------------------------------------------------------

class TestSafeWrite(unittest.TestCase):

    def _write_file(self, raw_bytes, suffix='.cpp'):
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, 'wb') as f:
            f.write(raw_bytes)
        return path

    def _run(self, path, stdin_text, enc_arg=None):
        """Run cmd_safe_write with UTF-8 encoded stdin_text."""
        raw = stdin_text.encode('utf-8')
        saved = sys.stdin
        try:
            if sys.version_info[0] >= 3:
                buf = io.BytesIO(raw)
                text_stdin = io.TextIOWrapper(buf, encoding='utf-8')
                text_stdin.buffer = io.BytesIO(raw)
                sys.stdin = text_stdin
            else:
                import StringIO as _sio
                sys.stdin = _sio.StringIO(raw)
            Args = type('Args', (), {'file': path, 'encoding': enc_arg})
            return eu.cmd_safe_write(Args())
        finally:
            sys.stdin = saved

    def test_existing_gbk_preserved(self):
        # Use content that chardet reliably identifies as GB2312/GBK (not EUC-TW)
        gbk_content = u'\u6ce8\u91ca\u4e2d\u6587\u6587\u4ef6\u5904\u7406' * 10
        path = self._write_file(gbk_content.encode('gbk'))
        try:
            ret = self._run(path, gbk_content)
            self.assertEqual(ret, 0)
            # File should still be GBK (encoding inherited from original)
            self.assertEqual(eu.detect_encoding(path), 'gbk')
        finally:
            os.unlink(path)

    def test_existing_utf8_bom_preserved(self):
        raw = b'\xef\xbb\xbf' + u'hello'.encode('utf-8')
        path = self._write_file(raw, suffix='.nsi')
        try:
            ret = self._run(path, u'new content')
            self.assertEqual(ret, 0)
            self.assertEqual(eu.detect_encoding(path), 'utf-8-bom')
        finally:
            os.unlink(path)

    def test_new_file_with_enc_arg(self):
        fd, path = tempfile.mkstemp(suffix='.cpp')
        os.close(fd)
        os.unlink(path)
        try:
            ret = self._run(path, u'int x = 1;', enc_arg='utf-8')
            self.assertEqual(ret, 0)
            self.assertEqual(eu.detect_encoding(path), 'utf-8')
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_new_file_no_enc_fails(self):
        fd, path = tempfile.mkstemp(suffix='.cpp')
        os.close(fd)
        os.unlink(path)
        try:
            ret = self._run(path, u'int x = 1;')
            self.assertEqual(ret, 1)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_enc_arg_overrides_detection(self):
        """--enc on existing file skips auto-detect."""
        path = self._write_file(u'\u6ce8'.encode('gbk'))
        try:
            ret = self._run(path, u'// replaced', enc_arg='utf-8')
            self.assertEqual(ret, 0)
            self.assertEqual(eu.detect_encoding(path), 'utf-8')
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Tests: convert command
# ---------------------------------------------------------------------------

class TestConvert(unittest.TestCase):

    def _write_file(self, raw_bytes, suffix='.cpp'):
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, 'wb') as f:
            f.write(raw_bytes)
        return path

    def test_convert_gbk_to_utf8(self):
        path = self._write_file((u'hello \u4e2d\u6587 ' * 20).encode('gbk'))
        try:
            Args = type('Args', (), {'file': path, 'to': 'utf-8', 'encoding': None})
            ret = eu.cmd_convert(Args())
            self.assertEqual(ret, 0)
            # Verify content round-trips correctly as UTF-8
            with io.open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn(u'\u4e2d\u6587', content)
        finally:
            os.unlink(path)

    def test_convert_already_target_enc(self):
        path = self._write_file(u'hello'.encode('utf-8'))
        try:
            Args = type('Args', (), {'file': path, 'to': 'utf-8', 'encoding': None})
            ret = eu.cmd_convert(Args())
            self.assertEqual(ret, 0)
        finally:
            os.unlink(path)

    def test_convert_utf8_to_utf8_bom(self):
        path = self._write_file(u'hello'.encode('utf-8'))
        try:
            Args = type('Args', (), {'file': path, 'to': 'utf-8-bom', 'encoding': None})
            ret = eu.cmd_convert(Args())
            self.assertEqual(ret, 0)
            self.assertEqual(eu.detect_encoding(path), 'utf-8-bom')
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Tests: safe-edit error path
# ---------------------------------------------------------------------------

class TestSafeEditErrors(unittest.TestCase):

    def test_pattern_not_found_returns_error_exit1(self):
        fd, path = tempfile.mkstemp(suffix='.cpp')
        with os.fdopen(fd, 'wb') as f:
            f.write(b'int x = 1;')
        try:
            saved_err = sys.stderr
            if sys.version_info[0] >= 3:
                sys.stderr = io.StringIO()
            else:
                import StringIO as _sio
                sys.stderr = _sio.StringIO()
            try:
                Args = type('Args', (), {'file': path, 'old': 'NO_MATCH', 'new': 'X'})
                ret = eu.cmd_safe_edit(Args())
                msg = sys.stderr.getvalue()
            finally:
                sys.stderr = saved_err
            self.assertEqual(ret, 1)
            self.assertIn('ERROR', msg)
        finally:
            os.unlink(path)


if __name__ == '__main__':
    unittest.main()