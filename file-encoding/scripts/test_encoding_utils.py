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


if __name__ == '__main__':
    unittest.main()