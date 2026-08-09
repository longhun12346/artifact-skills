# -*- coding: utf-8 -*-
"""Tests for encoding_utils.py.

Usage:
  python test_encoding_utils.py
  python -m pytest test_encoding_utils.py  # if pytest available
"""

import io
import os
import sys
import tempfile
import unittest

# Add parent dir to path so we can import encoding_utils as module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import encoding_utils as eu



def _write_temp(raw_bytes, suffix='.txt'):
    """Write raw bytes to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, 'wb') as f:
        f.write(raw_bytes)
    return path


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

    def test_utf8_no_bom(self):
        raw = u'hello world'.encode('utf-8')
        path = _write_temp(raw)
        try:
            self.assertEqual(eu.detect_encoding(path), 'utf-8')
        finally:
            os.unlink(path)

    def test_utf8_bom(self):
        raw = b'\xef\xbb\xbf' + u'hello'.encode('utf-8')
        path = _write_temp(raw)
        try:
            self.assertEqual(eu.detect_encoding(path), 'utf-8-bom')
        finally:
            os.unlink(path)

    def test_utf16_le_bom(self):
        raw = b'\xff\xfe' + u'hello world'.encode('utf-16-le')
        path = _write_temp(raw)
        try:
            self.assertEqual(eu.detect_encoding(path), 'utf-16-le-bom')
        finally:
            os.unlink(path)

    def test_utf16_be_bom(self):
        raw = b'\xfe\xff' + u'hello world'.encode('utf-16-be')
        path = _write_temp(raw)
        try:
            self.assertEqual(eu.detect_encoding(path), 'utf-16-be-bom')
        finally:
            os.unlink(path)

    def test_gbk_chinese(self):
        # Enough Chinese for chardet to reliably identify on any locale
        raw = (u'文件描述：测试中文编码检测功能模块 '
               u'作者：张三 日期：二零二六年').encode('gbk')
        path = _write_temp(raw)
        try:
            self.assertEqual(eu.detect_encoding(path), 'gbk')
        finally:
            os.unlink(path)

    def test_binary_file(self):
        raw = b'PK\x03\x04' + b'\x00' * 100
        path = _write_temp(raw)
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
        self.assertEqual(eu._friendly_to_python('utf-16-le-bom'), 'utf-16-le')

    def test_utf16_be_bom(self):
        self.assertEqual(eu._friendly_to_python('utf-16-be-bom'), 'utf-16-be')

    def test_unknown_passthrough(self):
        self.assertEqual(eu._friendly_to_python('cp936'), 'cp936')


# ---------------------------------------------------------------------------
# Tests: read_with_encoding / write_with_encoding
# ---------------------------------------------------------------------------

class TestReadWriteWithEncoding(unittest.TestCase):
    """Test the read_with_encoding / write_with_encoding public API."""

    def test_read_gbk(self):
        text = u'你好世界'
        path = _write_temp(text.encode('gbk'))
        try:
            result = eu.read_with_encoding(path, 'gbk', newline='')
            self.assertEqual(result, text)
        finally:
            os.unlink(path)

    def test_read_utf8_bom(self):
        text = u'hello world'
        raw = b'\xef\xbb\xbf' + text.encode('utf-8')
        path = _write_temp(raw)
        try:
            result = eu.read_with_encoding(path, 'utf-8-bom', newline='')
            self.assertEqual(result, text)
        finally:
            os.unlink(path)

    def test_read_utf16_le_bom(self):
        text = u'hello 你好'
        raw = b'\xff\xfe' + text.encode('utf-16-le')
        path = _write_temp(raw)
        try:
            result = eu.read_with_encoding(path, 'utf-16-le-bom', newline='')
            self.assertEqual(result, text)
        finally:
            os.unlink(path)

    def test_read_utf16_be_bom(self):
        text = u'hello 你好'
        raw = b'\xfe\xff' + text.encode('utf-16-be')
        path = _write_temp(raw)
        try:
            result = eu.read_with_encoding(path, 'utf-16-be-bom', newline='')
            self.assertEqual(result, text)
        finally:
            os.unlink(path)

    def test_write_gbk(self):
        text = u'你好世界'
        fd, path = tempfile.mkstemp(suffix='.cpp')
        os.close(fd)
        try:
            eu.write_with_encoding(path, text, 'gbk', newline='')
            with open(path, 'rb') as f:
                raw = f.read()
            self.assertEqual(raw, text.encode('gbk'))
        finally:
            os.unlink(path)

    def test_write_utf8_bom(self):
        text = u'hello world'
        fd, path = tempfile.mkstemp(suffix='.nsi')
        os.close(fd)
        try:
            eu.write_with_encoding(path, text, 'utf-8-bom', newline='')
            with open(path, 'rb') as f:
                raw = f.read()
            self.assertEqual(raw, b'\xef\xbb\xbf' + text.encode('utf-8'))
        finally:
            os.unlink(path)

    def test_write_utf16_le_bom(self):
        text = u'hello 你好'
        fd, path = tempfile.mkstemp(suffix='.ini')
        os.close(fd)
        try:
            eu.write_with_encoding(path, text, 'utf-16-le-bom', newline='')
            with open(path, 'rb') as f:
                raw = f.read()
            self.assertEqual(raw, b'\xff\xfe' + text.encode('utf-16-le'))
        finally:
            os.unlink(path)

    def test_write_utf16_be_bom(self):
        text = u'hello 你好'
        fd, path = tempfile.mkstemp(suffix='.ini')
        os.close(fd)
        try:
            eu.write_with_encoding(path, text, 'utf-16-be-bom', newline='')
            with open(path, 'rb') as f:
                raw = f.read()
            self.assertEqual(raw, b'\xfe\xff' + text.encode('utf-16-be'))
        finally:
            os.unlink(path)

    def test_roundtrip_utf16_le_bom(self):
        """Write then read preserves content for UTF-16 LE BOM."""
        text = u'[Section]\r\nkey=value\r\n'
        fd, path = tempfile.mkstemp(suffix='.ini')
        os.close(fd)
        try:
            eu.write_with_encoding(path, text, 'utf-16-le-bom', newline='')
            result = eu.read_with_encoding(path, 'utf-16-le-bom', newline='')
            self.assertEqual(result, text)
        finally:
            os.unlink(path)

    def test_roundtrip_utf16_be_bom(self):
        """Write then read preserves content for UTF-16 BE BOM."""
        text = u'[Section]\r\nkey=value\r\n'
        fd, path = tempfile.mkstemp(suffix='.ini')
        os.close(fd)
        try:
            eu.write_with_encoding(path, text, 'utf-16-be-bom', newline='')
            result = eu.read_with_encoding(path, 'utf-16-be-bom', newline='')
            self.assertEqual(result, text)
        finally:
            os.unlink(path)

    def test_roundtrip_gbk_crlf(self):
        """Write then read preserves CRLF for GBK."""
        text = u'注释\r\n代码\r\n'
        fd, path = tempfile.mkstemp(suffix='.cpp')
        os.close(fd)
        try:
            eu.write_with_encoding(path, text, 'gbk', newline='')
            result = eu.read_with_encoding(path, 'gbk', newline='')
            self.assertEqual(result, text)
        finally:
            os.unlink(path)

    def test_roundtrip_utf8_bom_crlf(self):
        """Write then read preserves CRLF for UTF-8 BOM."""
        text = u'line1\r\nline2\r\n'
        fd, path = tempfile.mkstemp(suffix='.nsi')
        os.close(fd)
        try:
            eu.write_with_encoding(path, text, 'utf-8-bom', newline='')
            result = eu.read_with_encoding(path, 'utf-8-bom', newline='')
            self.assertEqual(result, text)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Tests: cmd_read / cmd_write round trip via CLI API
# ---------------------------------------------------------------------------

class TestRoundTrip(unittest.TestCase):
    """Test that write+read preserves content for each encoding."""

    def _roundtrip(self, encoding, text):
        fd, path = tempfile.mkstemp(suffix='.txt')
        os.close(fd)
        try:
            # Write
            stdin_content = text.encode('utf-8')
            saved_stdin = sys.stdin
            try:
                class _FakeStdin(object):
                    def __init__(self, data):
                        self.buffer = io.BytesIO(data)
                sys.stdin = _FakeStdin(stdin_content)
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
                sys.stdout = io.StringIO()
                ret = eu.cmd_read(ReadArgs())
                self.assertEqual(ret, 0)
                result = sys.stdout.getvalue()
            finally:
                sys.stdout = saved_stdout

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
        self._roundtrip('utf-16-le-bom', u'hello unicode: 你好\n')

    def test_gbk_with_chinese(self):
        # Enough Chinese for reliable detection on any locale
        self._roundtrip('gbk', u'文件描述：测试中文编码处理\n你好世界\n')


# ---------------------------------------------------------------------------
# Tests: safe-write command
# ---------------------------------------------------------------------------

class TestSafeWrite(unittest.TestCase):

    def _run(self, path, stdin_text, enc_arg=None):
        """Run cmd_safe_write with UTF-8 encoded stdin_text."""
        raw = stdin_text.encode('utf-8')
        saved = sys.stdin
        try:
            # cmd_safe_write reads sys.stdin.buffer.read()
            class _FakeStdin(object):
                def __init__(self, data):
                    self.buffer = io.BytesIO(data)
            sys.stdin = _FakeStdin(raw)
            Args = type('Args', (), {'file': path, 'encoding': enc_arg})
            return eu.cmd_safe_write(Args())
        finally:
            sys.stdin = saved

    def test_existing_gbk_preserved(self):
        # Use content that chardet reliably identifies as GB2312/GBK
        gbk_content = u'注释中文文件处理' * 10
        path = _write_temp(gbk_content.encode('gbk'))
        try:
            ret = self._run(path, gbk_content)
            self.assertEqual(ret, 0)
            # File should still be GBK (encoding inherited from original)
            self.assertEqual(eu.detect_encoding(path), 'gbk')
        finally:
            os.unlink(path)

    def test_existing_utf8_bom_preserved(self):
        raw = b'\xef\xbb\xbf' + u'hello'.encode('utf-8')
        path = _write_temp(raw, suffix='.nsi')
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
        path = _write_temp(u'注'.encode('gbk'))
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

    def test_convert_gbk_to_utf8(self):
        path = _write_temp((u'中文编码转换测试内容 ' * 20).encode('gbk'))
        try:
            Args = type('Args', (), {'file': path, 'to': 'utf-8', 'encoding': None})
            ret = eu.cmd_convert(Args())
            self.assertEqual(ret, 0)
            # Verify content round-trips correctly as UTF-8
            with io.open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn(u'中文', content)
        finally:
            os.unlink(path)

    def test_convert_already_target_enc(self):
        path = _write_temp(u'hello'.encode('utf-8'))
        try:
            Args = type('Args', (), {'file': path, 'to': 'utf-8', 'encoding': None})
            ret = eu.cmd_convert(Args())
            self.assertEqual(ret, 0)
        finally:
            os.unlink(path)

    def test_convert_utf8_to_utf8_bom(self):
        path = _write_temp(u'hello'.encode('utf-8'))
        try:
            Args = type('Args', (), {'file': path, 'to': 'utf-8-bom', 'encoding': None})
            ret = eu.cmd_convert(Args())
            self.assertEqual(ret, 0)
            self.assertEqual(eu.detect_encoding(path), 'utf-8-bom')
        finally:
            os.unlink(path)

    def test_convert_utf8_to_utf16_le_bom(self):
        path = _write_temp(u'hello 你好'.encode('utf-8'))
        try:
            Args = type('Args', (), {'file': path, 'to': 'utf-16-le-bom', 'encoding': None})
            ret = eu.cmd_convert(Args())
            self.assertEqual(ret, 0)
            self.assertEqual(eu.detect_encoding(path), 'utf-16-le-bom')
            content = eu.read_with_encoding(path, 'utf-16-le-bom', newline='')
            self.assertIn(u'你好', content)
        finally:
            os.unlink(path)

    def test_convert_utf8_to_utf16_be_bom(self):
        path = _write_temp(u'hello 你好'.encode('utf-8'))
        try:
            Args = type('Args', (), {'file': path, 'to': 'utf-16-be-bom', 'encoding': None})
            ret = eu.cmd_convert(Args())
            self.assertEqual(ret, 0)
            self.assertEqual(eu.detect_encoding(path), 'utf-16-be-bom')
            content = eu.read_with_encoding(path, 'utf-16-be-bom', newline='')
            self.assertIn(u'你好', content)
        finally:
            os.unlink(path)

    def test_convert_utf16_le_to_utf16_be(self):
        """Convert from UTF-16 LE BOM to UTF-16 BE BOM preserves content."""
        text = u'hello 世界 world'
        raw = b'\xff\xfe' + text.encode('utf-16-le')
        path = _write_temp(raw, suffix='.ini')
        try:
            Args = type('Args', (), {'file': path, 'to': 'utf-16-be-bom', 'encoding': None})
            ret = eu.cmd_convert(Args())
            self.assertEqual(ret, 0)
            self.assertEqual(eu.detect_encoding(path), 'utf-16-be-bom')
            content = eu.read_with_encoding(path, 'utf-16-be-bom', newline='')
            self.assertEqual(content, text)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Tests: UTF-16 BE BOM specific
# ---------------------------------------------------------------------------

class TestUtf16BeBom(unittest.TestCase):
    """Specific tests for UTF-16 BE BOM endianness preservation."""

    def test_detect_utf16_be_bom(self):
        """UTF-16 BE BOM file correctly detected."""
        text = u'[Section]\nkey=value\n'
        raw = b'\xfe\xff' + text.encode('utf-16-be')
        path = _write_temp(raw)
        try:
            self.assertEqual(eu.detect_encoding(path), 'utf-16-be-bom')
        finally:
            os.unlink(path)

    def test_read_preserves_crlf(self):
        """Reading UTF-16 BE BOM with newline='' preserves CRLF."""
        text = u'line1\r\nline2\r\n'
        raw = b'\xfe\xff' + text.encode('utf-16-be')
        path = _write_temp(raw)
        try:
            result = eu.read_with_encoding(path, 'utf-16-be-bom', newline='')
            self.assertEqual(result, text)
            self.assertIn(u'\r\n', result)
        finally:
            os.unlink(path)

    def test_write_produces_correct_bom(self):
        """Writing UTF-16 BE BOM produces FE FF BOM followed by big-endian bytes."""
        text = u'AB'
        fd, path = tempfile.mkstemp(suffix='.ini')
        os.close(fd)
        try:
            eu.write_with_encoding(path, text, 'utf-16-be-bom', newline='')
            with open(path, 'rb') as f:
                raw = f.read()
            # FE FF + 'A' in BE (00 41) + 'B' in BE (00 42)
            expected = b'\xfe\xff\x00\x41\x00\x42'
            self.assertEqual(raw, expected)
        finally:
            os.unlink(path)

    def test_endianness_not_flipped(self):
        """Ensure BE stays BE through write+read cycle (no LE contamination)."""
        text = u'你好'  # U+4F60 U+597D
        fd, path = tempfile.mkstemp(suffix='.ini')
        os.close(fd)
        try:
            eu.write_with_encoding(path, text, 'utf-16-be-bom', newline='')
            with open(path, 'rb') as f:
                raw = f.read()
            # BOM: FE FF
            self.assertEqual(raw[:2], b'\xfe\xff')
            # U+4F60 in BE: 4F 60
            self.assertEqual(raw[2:4], b'\x4f\x60')
            # U+597D in BE: 59 7D
            self.assertEqual(raw[4:6], b'\x59\x7d')
        finally:
            os.unlink(path)

    def test_roundtrip_chinese_content(self):
        """Full write+read roundtrip with Chinese content preserves everything."""
        text = u'注释中文文件\r\n第二行\r\n'
        fd, path = tempfile.mkstemp(suffix='.ini')
        os.close(fd)
        try:
            eu.write_with_encoding(path, text, 'utf-16-be-bom', newline='')
            result = eu.read_with_encoding(path, 'utf-16-be-bom', newline='')
            self.assertEqual(result, text)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases(unittest.TestCase):
    """Edge cases for encoding detection and I/O."""

    def test_empty_file_detected_as_utf8(self):
        """Empty file should be detected as utf-8 (pure ASCII)."""
        path = _write_temp(b'')
        try:
            # Empty file: no BOM, no null (not binary), decodes as ascii
            self.assertEqual(eu.detect_encoding(path), 'utf-8')
        finally:
            os.unlink(path)

    def test_ascii_only_detected_as_utf8(self):
        """Pure ASCII content should be detected as utf-8."""
        path = _write_temp(b'int main() { return 0; }\n')
        try:
            self.assertEqual(eu.detect_encoding(path), 'utf-8')
        finally:
            os.unlink(path)

    def test_read_utf16_le_bom_without_bom_in_file(self):
        """Reading as utf-16-le-bom when file has no BOM should still work."""
        text = u'no bom here'
        raw = text.encode('utf-16-le')  # no BOM prefix
        path = _write_temp(raw)
        try:
            # Should decode without error (no BOM to skip)
            result = eu.read_with_encoding(path, 'utf-16-le-bom', newline='')
            self.assertEqual(result, text)
        finally:
            os.unlink(path)

    def test_write_read_windows_1251(self):
        """Windows-1251 (Cyrillic) write+read roundtrip."""
        text = u'Привет'  # Привет
        fd, path = tempfile.mkstemp(suffix='.txt')
        os.close(fd)
        try:
            eu.write_with_encoding(path, text, 'windows-1251', newline='')
            result = eu.read_with_encoding(path, 'windows-1251', newline='')
            self.assertEqual(result, text)
        finally:
            os.unlink(path)

    def test_cmd_read_binary_rejected(self):
        """cmd_read on binary file should return error."""
        path = _write_temp(b'PK\x03\x04' + b'\x00' * 100)
        try:
            saved_stderr = sys.stderr
            try:
                sys.stderr = io.StringIO()
                Args = type('Args', (), {'file': path, 'encoding': None})
                ret = eu.cmd_read(Args())
                self.assertEqual(ret, 1)
            finally:
                sys.stderr = saved_stderr
        finally:
            os.unlink(path)

    def test_cmd_convert_binary_rejected(self):
        """cmd_convert on binary file should return error."""
        path = _write_temp(b'PK\x03\x04' + b'\x00' * 100)
        try:
            saved_stderr = sys.stderr
            try:
                sys.stderr = io.StringIO()
                Args = type('Args', (), {'file': path, 'to': 'utf-8', 'encoding': None})
                ret = eu.cmd_convert(Args())
                self.assertEqual(ret, 1)
            finally:
                sys.stderr = saved_stderr
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Tests: replace command (safe edit channel for non-UTF-8 files)
# ---------------------------------------------------------------------------

class TestReplace(unittest.TestCase):
    """cmd_replace: precise replacement preserving original encoding."""

    def _args(self, path, old, new, enc=None, all_=False, expect=None):
        return type('Args', (), {
            'file': path, 'old': old, 'new': new,
            'encoding': enc, 'all': all_, 'expect': expect,
        })()

    def test_replace_first_occurrence_gbk(self):
        """Replace first occurrence in a GBK file; encoding preserved."""
        text = u'int x = 1; // 旧注释\nint y = 2; // 旧注释\n'
        path = _write_temp(text.encode('gbk'))
        try:
            ret = eu.cmd_replace(self._args(path, u'旧注释', u'新注释'))
            self.assertEqual(ret, 0)
            self.assertEqual(eu.detect_encoding(path), 'gbk')
            content = eu.read_with_encoding(path, 'gbk', newline='')
            self.assertEqual(content, u'int x = 1; // 新注释\nint y = 2; // 旧注释\n')
        finally:
            os.unlink(path)

    def test_replace_all_gbk(self):
        text = u'旧注释 旧注释 旧注释\n'
        path = _write_temp(text.encode('gbk'))
        try:
            ret = eu.cmd_replace(self._args(path, u'旧注释', u'新', all_=True))
            self.assertEqual(ret, 0)
            content = eu.read_with_encoding(path, 'gbk', newline='')
            self.assertEqual(content, u'新 新 新\n')
        finally:
            os.unlink(path)

    def test_replace_old_not_found_no_modify(self):
        """old_string missing -> error, file byte-identical."""
        raw = u'int x = 1;\n'.encode('gbk')
        path = _write_temp(raw)
        try:
            saved_stderr = sys.stderr
            try:
                sys.stderr = io.StringIO()
                ret = eu.cmd_replace(self._args(path, u'不存在的文本', u'X'))
                self.assertEqual(ret, 1)
            finally:
                sys.stderr = saved_stderr
            with open(path, 'rb') as f:
                self.assertEqual(f.read(), raw)
        finally:
            os.unlink(path)

    def test_replace_expect_mismatch_no_modify(self):
        """Occurrence count != --expect -> error, file untouched."""
        raw = u'AAA BBB AAA\n'.encode('gbk')
        path = _write_temp(raw)
        try:
            saved_stderr = sys.stderr
            try:
                sys.stderr = io.StringIO()
                ret = eu.cmd_replace(self._args(path, u'AAA', u'X', expect=3))
                self.assertEqual(ret, 1)
            finally:
                sys.stderr = saved_stderr
            with open(path, 'rb') as f:
                self.assertEqual(f.read(), raw)
        finally:
            os.unlink(path)

    def test_replace_unencodable_new_no_modify(self):
        """New text with chars GBK cannot represent -> error, file untouched."""
        raw = u'int x = 1; // 中文注释\n'.encode('gbk')
        path = _write_temp(raw)
        try:
            saved_stderr = sys.stderr
            try:
                sys.stderr = io.StringIO()
                ret = eu.cmd_replace(self._args(path, u'中文注释', u'注释\U0001F600'))
                self.assertEqual(ret, 1)
            finally:
                sys.stderr = saved_stderr
            with open(path, 'rb') as f:
                self.assertEqual(f.read(), raw)
        finally:
            os.unlink(path)

    def test_replace_preserves_crlf(self):
        """CRLF line endings preserved through replace."""
        text = u'line1\r\nline2\r\n'
        path = _write_temp(text.encode('gbk'))
        try:
            ret = eu.cmd_replace(self._args(path, u'line1', u'LINE1'))
            self.assertEqual(ret, 0)
            content = eu.read_with_encoding(path, 'gbk', newline='')
            self.assertEqual(content, u'LINE1\r\nline2\r\n')
        finally:
            os.unlink(path)

    def test_replace_utf16le_bom(self):
        """Replace works on UTF-16 LE BOM files and preserves BOM."""
        text = u'[Section]\nkey=value\n'
        path = _write_temp(b'\xff\xfe' + text.encode('utf-16-le'), suffix='.ini')
        try:
            ret = eu.cmd_replace(self._args(path, u'value', u'新值', enc='utf-16-le-bom'))
            self.assertEqual(ret, 0)
            self.assertEqual(eu.detect_encoding(path), 'utf-16-le-bom')
            content = eu.read_with_encoding(path, 'utf-16-le-bom', newline='')
            self.assertIn(u'新值', content)
        finally:
            os.unlink(path)

    def test_replace_binary_rejected(self):
        path = _write_temp(b'PK\x03\x04' + b'\x00' * 100)
        try:
            saved_stderr = sys.stderr
            try:
                sys.stderr = io.StringIO()
                ret = eu.cmd_replace(self._args(path, u'a', u'b'))
                self.assertEqual(ret, 1)
            finally:
                sys.stderr = saved_stderr
        finally:
            os.unlink(path)

    def test_replace_missing_file_rejected(self):
        path = os.path.join(tempfile.gettempdir(), 'definitely_missing_xyz.cpp')
        saved_stderr = sys.stderr
        try:
            sys.stderr = io.StringIO()
            ret = eu.cmd_replace(self._args(path, u'a', u'b'))
            self.assertEqual(ret, 1)
        finally:
            sys.stderr = saved_stderr

    def test_write_preserves_crlf_from_stdin(self):
        """cmd_write must NOT translate CRLF -> LF when reading piped stdin."""
        text = u'line1\r\nline2\r\n'
        fd, path = tempfile.mkstemp(suffix='.cpp')
        os.close(fd)
        try:
            saved = sys.stdin
            try:
                class _FakeStdin(object):
                    def __init__(self, data):
                        self.buffer = io.BytesIO(data)
                sys.stdin = _FakeStdin(text.encode('utf-8'))
                Args = type('Args', (), {'file': path, 'encoding': 'gbk'})
                ret = eu.cmd_write(Args())
                self.assertEqual(ret, 0)
            finally:
                sys.stdin = saved
            content = eu.read_with_encoding(path, 'gbk', newline='')
            self.assertEqual(content, text)  # CRLF preserved
        finally:
            os.unlink(path)

    def test_read_max_lines(self):
        """cmd_read --max-lines truncates output to N lines."""
        text = u'\n'.join(u'line %d' % i for i in range(100))
        fd, path = tempfile.mkstemp(suffix='.txt')
        os.close(fd)
        try:
            eu.write_with_encoding(path, text, 'utf-8', newline='')
            saved_out, saved_err = sys.stdout, sys.stderr
            try:
                sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
                Args = type('Args', (), {'file': path, 'encoding': None, 'max_lines': 10})
                ret = eu.cmd_read(Args())
                out, err = sys.stdout.getvalue(), sys.stderr.getvalue()
            finally:
                sys.stdout, sys.stderr = saved_out, saved_err
            self.assertEqual(ret, 0)
            self.assertEqual(out.count('\n'), 9)  # 10 lines
            self.assertIn('truncated', err)
        finally:
            os.unlink(path)

    def test_write_unencodable_fails_cleanly(self):
        """cmd_write with chars outside target charset -> friendly error, no traceback."""
        fd, path = tempfile.mkstemp(suffix='.cpp')
        os.close(fd)
        try:
            saved = sys.stdin
            try:
                class _FakeStdin(object):
                    def __init__(self, data):
                        self.buffer = io.BytesIO(data)
                sys.stdin = _FakeStdin(u'int x; // \U0001F600'.encode('utf-8'))
                saved_err = sys.stderr
                try:
                    sys.stderr = io.StringIO()
                    Args = type('Args', (), {'file': path, 'encoding': 'gbk'})
                    ret = eu.cmd_write(Args())
                finally:
                    sys.stderr = saved_err
            finally:
                sys.stdin = saved
            self.assertEqual(ret, 1)
            with open(path, 'rb') as f:
                self.assertEqual(f.read(), b'')  # untouched (atomic)
        finally:
            os.unlink(path)


if __name__ == '__main__':
    unittest.main()
