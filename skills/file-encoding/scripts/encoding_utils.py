# -*- coding: utf-8 -*-
"""encoding_utils.py - File encoding detection & conversion toolkit.

Usage:
  python encoding_utils.py detect <file>              # print encoding name
  python encoding_utils.py read <file> [--enc E]      # print decoded content to stdout
  python encoding_utils.py write <file> --enc E       # read stdin, write with encoding E
  python encoding_utils.py safe-write <file> [--enc E]  # auto-detect + overwrite from stdin
  python encoding_utils.py replace <file> --old S --new S [--enc E] [--all] [--expect N]
                                                    # precise single/multi replacement
  python encoding_utils.py convert <file> --to E [--enc F]  # convert encoding in-place
  python encoding_utils.py --version                  # print version

replace is the safe edit channel for non-UTF-8 files: it reads with the file's
real encoding, replaces the old string, and writes back with the SAME encoding.
It never modifies the file unless old_string is found exactly once (or --all
is given) and every new character is encodable in the target charset.

Supported encoding names (friendly -> Python):
  gbk, shift-jis, euc-kr, big5, utf-8, utf-8-bom, utf-16-le-bom, utf-16-be-bom,
  windows-1250 ~ windows-1258, iso-8859-1, iso-8859-2

This module is also imported by encoding_transparent.py (the hook) for its
detect_encoding(), read_with_encoding(), write_with_encoding() functions.
"""

__version__ = "3.1.0"

import argparse
import io
import os
import sys
import locale
import tempfile


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------
_IS_WINDOWS = (os.name == 'nt')


def _get_sys_encoding():
    """Get system ANSI encoding. Returns a valid Python encoding name."""
    try:
        if sys.version_info >= (3, 11):
            return locale.getencoding()
        return locale.getpreferredencoding(False) or 'utf-8'
    except (ValueError, TypeError):
        return 'utf-8'



def _read_stdin_unicode(binary_mode=False):
    """Read stdin and return a unicode string.

    binary_mode=True: read via sys.stdin.buffer (Py3) so non-ASCII survives
    on Windows regardless of console code page. Use for raw file content.
    binary_mode=False: read via sys.stdin in text mode. Use for JSON/metadata.
    """
    if binary_mode:
        return sys.stdin.buffer.read().decode('utf-8')
    return sys.stdin.read()


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------

_BINARY_NULL_THRESHOLD = 512  # check first 512 bytes for null bytes
_MAX_DETECT_BYTES = 8192     # read at most 8 KB for encoding detection


def _is_binary(raw):
    """Return True if raw looks like binary data."""
    return raw[: _BINARY_NULL_THRESHOLD].find(b'\x00') >= 0


def _detect_bom(raw_head):
    """Return encoding name if BOM found, else None."""
    if raw_head[:2] == b'\xff\xfe':
        return 'utf-16-le-bom'
    if raw_head[:2] == b'\xfe\xff':
        return 'utf-16-be-bom'
    if raw_head[:3] == b'\xef\xbb\xbf':
        return 'utf-8-bom'
    return None


# Map Windows code page numbers to friendly names.
# Extended beyond CJK to cover common European/Cyrillic code pages.
_CODE_PAGE_MAP = {
    # CJK
    'cp936': 'gbk', 'gb2312': 'gbk', 'gb18030': 'gbk',
    'cp932': 'shift-jis', 'shift_jis': 'shift-jis',
    'cp949': 'euc-kr', 'euc_kr': 'euc-kr', 'ks_c_5601-1987': 'euc-kr',
    'cp950': 'big5', 'big5-hkscs': 'big5', 'euc-tw': 'big5',
    # European
    'cp1250': 'windows-1250', 'cp1251': 'windows-1251', 'cp1252': 'windows-1252',
    'cp1253': 'windows-1253', 'cp1254': 'windows-1254', 'cp1255': 'windows-1255',
    'cp1256': 'windows-1256', 'cp1257': 'windows-1257', 'cp1258': 'windows-1258',
    'iso-8859-1': 'iso-8859-1', 'iso-8859-2': 'iso-8859-2',
    'latin1': 'iso-8859-1', 'latin2': 'iso-8859-2',
}


def _normalize_encoding_name(enc):
    """Normalize a detector's encoding name to our friendly names.

    charset-normalizer reports Python codec names (utf_8, gb18030, cp932,
    cp949, big5hkscs...); chardet reports uppercase/legacy names
    (GB18030, CP949, Windows-1251...). Both are mapped to the friendly
    names used across this project (gbk, shift-jis, euc-kr, big5, ...).
    """
    if not enc:
        return None
    enc = enc.lower().replace('_', '-')
    if enc in ('utf-8', 'ascii'):
        return enc
    return _CODE_PAGE_MAP.get(enc, enc)


def _detect_with_charset_normalizer(raw):
    """Detect via charset-normalizer (modern, fast). Returns friendly name or None.

    Only accepts the result when the match has statistical coherence
    (percent_coherence > 0): on very short inputs charset-normalizer falls back
    to guessing (coherence 0.0) and frequently misreports, e.g. a 3-character
    GBK comment as big5 or a Windows-1251 comment as big5. Those cases are
    left to chardet / the heuristic fallback, which handle short CJK better.
    """
    try:
        from charset_normalizer import from_bytes
        match = from_bytes(raw).best()
        if match and match.encoding and match.percent_coherence > 0:
            enc = _normalize_encoding_name(match.encoding)
            # Verify the reported encoding actually decodes the bytes; this
            # rejects cross-family misreports (e.g. Cyrillic bytes as big5).
            try:
                raw.decode(_friendly_to_python(enc))
                return enc
            except (UnicodeDecodeError, LookupError):
                pass
    except Exception:
        pass
    return None


def _detect_with_chardet(raw):
    """Detect via chardet (legacy fallback). Returns friendly name or None."""
    try:
        import chardet
        result = chardet.detect(raw)
        if result['encoding']:
            enc = result['encoding'].lower()
            friendly = _CODE_PAGE_MAP.get(enc, enc)
            # CJK multi-byte encodings are reliable at lower confidence;
            # single-byte encodings need higher confidence to avoid false positives.
            _CJK_ENCODINGS = {'gbk', 'gb2312', 'gb18030', 'shift-jis', 'euc-kr', 'big5'}
            threshold = 0.4 if friendly in _CJK_ENCODINGS else 0.7
            if result['confidence'] > threshold:
                return friendly
    except ImportError:
        pass
    return None


def _cyrillic_distinct(text):
    """Count DISTINCT Cyrillic characters (U+0400-U+04FF) in decoded text.

    Distinctness (not raw count) is the discriminator: in windows-1251 every
    accented Latin char maps to a Cyrillic char (é -> й), so 'café déjà vu'
    decodes to just 2 distinct Cyrillic chars, while real Cyrillic text has
    many. Requiring >= 3 distinct chars separates the two reliably.
    """
    return len(set(ch for ch in text if u'\u0400' <= ch <= u'\u04ff'))


def detect_encoding(filepath):
    """Detect text file encoding. Returns friendly name, or 'binary'."""
    with open(filepath, 'rb') as f:
        raw = f.read(_MAX_DETECT_BYTES)

    # BOM check first - a file with BOM is text by definition,
    # even if it contains null bytes (e.g. UTF-16 LE of ASCII text)
    bom_enc = _detect_bom(raw[:4])
    if bom_enc:
        return bom_enc

    if _is_binary(raw):
        return 'binary'

    # Pure ASCII -> UTF-8 (avoids false positives from ANSI code pages)
    try:
        raw.decode('ascii')
        return 'utf-8'
    except UnicodeDecodeError:
        pass

    # No BOM, not binary, not pure ASCII - try UTF-8 first (strict),
    # then charset-normalizer, then chardet, then heuristic ANSI fallback.
    # The UTF-8 check must come first: single-byte ANSI encodings accept
    # almost any byte sequence, so they would win the race otherwise.
    try:
        raw.decode('utf-8')
        return 'utf-8'
    except UnicodeDecodeError:
        pass

    enc = _detect_with_charset_normalizer(raw)
    if enc:
        return enc
    enc = _detect_with_chardet(raw)
    if enc:
        return enc

    # Heuristic fallback: try multi-byte CJK encodings first (they reject
    # invalid byte sequences), then single-byte encodings last (they accept
    # almost any byte sequence and are essentially "universal decoders").
    sys_enc = _get_sys_encoding()
    _PERMISSIVE = {'cp1252', 'windows-1252', 'cp1250', 'windows-1250',
                   'cp1251', 'windows-1251', 'cp1253', 'windows-1253',
                   'cp1254', 'windows-1254', 'iso-8859-1', 'latin1',
                   'iso-8859-2', 'latin2'}
    multi_byte = ['gbk', 'shift-jis', 'euc-kr', 'big5']
    if _IS_WINDOWS:
        # windows-1251 first: single-byte decoders accept almost any bytes, so
        # without priority the permissive windows-1252 would always win and
        # Cyrillic files would be misreported as 1252 (which is SAFE and lets
        # native tools garble them). The Cyrillic check below disambiguates.
        single_byte = ['windows-1251', 'windows-1252', 'windows-1250']
    else:
        single_byte = ['iso-8859-1', 'windows-1252']
    # System encoding goes first ONLY if it's multi-byte (restrictive);
    # permissive single-byte system encodings go with the single-byte group.
    seen = set()
    candidates = []
    if sys_enc and sys_enc not in ('utf-8', 'ascii') and sys_enc not in _PERMISSIVE:
        candidates.append(sys_enc)
        seen.add(sys_enc)
    for enc in multi_byte + single_byte + ([sys_enc] if sys_enc in _PERMISSIVE else []):
        if enc and enc not in seen:
            seen.add(enc)
            candidates.append(enc)
    for enc in candidates:
        try:
            text = raw.decode(enc)
        except Exception:
            continue
        if enc in ('windows-1251', 'cp1251'):
            # Only accept 1251 when the decoded text actually contains
            # enough distinct Cyrillic characters; otherwise it is probably
            # Latin-1/1252 text (where accents map to Cyrillic chars).
            if _cyrillic_distinct(text) >= 3:
                return 'windows-1251'
            continue
        if enc in ('windows-1252', 'cp1252') and _cyrillic_distinct(text) >= 3:
            # Decodes, but the result is mostly Cyrillic - windows-1251 is a
            # better guess; don't return a SAFE encoding for it.
            continue
        return _CODE_PAGE_MAP.get(enc, enc)

    return 'utf-8'


def _friendly_to_python(enc):
    """Map friendly encoding name to Python encoding string.

    Note: utf-16-le-bom and utf-16-be-bom use explicit LE/BE codecs
    (without BOM) because Python's 'utf-16' always writes native-endian
    on output, which would lose the original byte order for BE files.
    BOM is handled manually by the read/write helpers below.
    """
    mapping = {
        'gbk': 'gbk',
        'shift-jis': 'shift-jis',
        'euc-kr': 'euc-kr',
        'big5': 'big5',
        'windows-1250': 'windows-1250',
        'windows-1251': 'windows-1251',
        'windows-1252': 'windows-1252',
        'windows-1253': 'windows-1253',
        'windows-1254': 'windows-1254',
        'windows-1255': 'windows-1255',
        'windows-1256': 'windows-1256',
        'windows-1257': 'windows-1257',
        'windows-1258': 'windows-1258',
        'iso-8859-1': 'iso-8859-1',
        'iso-8859-2': 'iso-8859-2',
        'utf-8': 'utf-8',
        'utf-8-bom': 'utf-8-sig',
        'utf-16-le-bom': 'utf-16-le',
        'utf-16-be-bom': 'utf-16-be',
        'utf-16': 'utf-16',
    }
    return mapping.get(enc, enc)


# BOM bytes for UTF-16 variants (used by read/write helpers)
_BOM_FOR_ENCODING = {
    'utf-16-le-bom': b'\xff\xfe',
    'utf-16-be-bom': b'\xfe\xff',
}


def read_with_encoding(filepath, enc, newline=''):
    """Read file content as unicode, handling BOM for utf-16-le-bom/be-bom.

    Returns the file content as a unicode string (without BOM character).
    """
    if enc in _BOM_FOR_ENCODING:
        # Read raw, skip BOM bytes, decode with explicit LE/BE codec
        bom = _BOM_FOR_ENCODING[enc]
        with open(filepath, 'rb') as f:
            raw = f.read()
        if raw[:len(bom)] == bom:
            raw = raw[len(bom):]
        pyenc = _friendly_to_python(enc)
        content = raw.decode(pyenc)
        if newline == '':
            return content
        # Default newline handling: translate \r\n → \n
        return content.replace(u'\r\n', u'\n')
    else:
        pyenc = _friendly_to_python(enc)
        with io.open(filepath, 'r', encoding=pyenc, newline=newline) as f:
            return f.read()


def _atomic_write_bytes(filepath, data):
    """Write bytes to filepath atomically (temp file + os.replace).

    A crash mid-write can never leave a half-written file behind.
    """
    dirpath = os.path.dirname(os.path.abspath(filepath))
    fd, tmp_path = tempfile.mkstemp(dir=dirpath, suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.replace(tmp_path, filepath)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def write_with_encoding(filepath, content, enc, newline=''):
    """Write unicode content to file, handling BOM for utf-16-le-bom/be-bom.

    Encodes the content fully in memory BEFORE touching the file, so a
    UnicodeEncodeError never truncates or corrupts an existing file, and
    writes atomically so a crash never leaves a half-written file.
    """
    if enc in _BOM_FOR_ENCODING:
        bom = _BOM_FOR_ENCODING[enc]
        pyenc = _friendly_to_python(enc)
        encoded = content.encode(pyenc)
        _atomic_write_bytes(filepath, bom + encoded)
    else:
        pyenc = _friendly_to_python(enc)
        encoded = content.encode(pyenc)
        _atomic_write_bytes(filepath, encoded)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_detect(args):
    enc = detect_encoding(args.file)
    print(enc)
    return 0


def cmd_read(args):
    enc = args.encoding or detect_encoding(args.file)
    if enc == 'binary':
        sys.stderr.write("ERROR: cannot read binary file\n")
        return 1

    try:
        content = read_with_encoding(args.file, enc, newline='')
    except UnicodeDecodeError:
        fallbacks = ['utf-8', 'gbk', 'shift-jis', 'euc-kr', 'big5',
                     'windows-1252', 'iso-8859-1']
        for fb in fallbacks:
            if fb == enc:
                continue
            try:
                content = read_with_encoding(args.file, fb, newline='')
                sys.stderr.write("[encoding_utils] WARN: decode failed with %s, fell back to %s\n" % (enc, fb))
                break
            except UnicodeDecodeError:
                continue
        else:
            raise

    max_lines = getattr(args, 'max_lines', None)
    if max_lines is not None:
        lines = content.split('\n')
        total = len(lines)
        if total > max_lines:
            content = '\n'.join(lines[:max_lines])
            sys.stderr.write(
                "[encoding_utils] WARN: output truncated to first %d of %d lines "
                "(--max-lines %d)\n" % (max_lines, total, max_lines))

    sys.stdout.write(content)
    return 0


def cmd_write(args):
    if not args.encoding:
        sys.stderr.write("ERROR: --encoding required for write\n")
        return 1

    content = _read_stdin_unicode(binary_mode=True)
    try:
        write_with_encoding(args.file, content, args.encoding, newline='')
    except UnicodeEncodeError as e:
        sys.stderr.write(
            "ERROR: content contains character(s) not representable in %s: %s\n"
            "File NOT modified. Use a different wording or convert the file to UTF-8.\n"
            % (args.encoding, e))
        return 1

    print("OK: %s written with encoding %s" % (args.file, args.encoding))
    return 0


def cmd_safe_write(args):
    """Auto-detect existing file encoding + write stdin content, preserving encoding.
    For new files (not yet existing), --enc is required.
    If --enc is supplied and file exists, it overrides auto-detection."""
    if args.encoding:
        enc = args.encoding
    elif os.path.exists(args.file):
        enc = detect_encoding(args.file)
        if enc == 'binary':
            sys.stderr.write("ERROR: cannot overwrite binary file\n")
            return 1
    else:
        sys.stderr.write("ERROR: file does not exist; --enc required\n")
        return 1

    # Read stdin via buffer so non-ASCII survives Windows console code page
    content = _read_stdin_unicode(binary_mode=True)
    write_with_encoding(args.file, content, enc, newline='')

    print("OK: written, encoding '%s' preserved" % enc)
    return 0


def cmd_replace(args):
    """Precise replacement in a file, preserving its original encoding.

    Safe edit channel for non-UTF-8 files. The file is NOT modified unless:
      - old_string is found (exactly once by default, or all with --all)
      - every character in new_string is encodable in the target charset
    """
    if not os.path.exists(args.file):
        sys.stderr.write("ERROR: file does not exist: %s\n" % args.file)
        return 1
    if not os.path.isfile(args.file):
        sys.stderr.write("ERROR: not a file: %s\n" % args.file)
        return 1
    enc = args.encoding or detect_encoding(args.file)
    if enc == 'binary':
        sys.stderr.write("ERROR: cannot edit binary file\n")
        return 1
    if args.old == u'':
        sys.stderr.write("ERROR: --old must not be empty\n")
        return 1

    try:
        content = read_with_encoding(args.file, enc, newline='')
    except UnicodeDecodeError as e:
        sys.stderr.write("ERROR: cannot decode %s as %s: %s\n" % (args.file, enc, e))
        return 1

    count = content.count(args.old)
    if count == 0:
        sys.stderr.write(
            "ERROR: old_string not found in %s (encoding %s). File NOT modified.\n"
            "Check exact text, whitespace and newline differences (\\r\\n vs \\n).\n"
            % (args.file, enc))
        return 1
    if args.expect is not None and count != args.expect:
        sys.stderr.write(
            "ERROR: old_string found %d time(s), expected %d. File NOT modified.\n"
            "Use --all to replace every occurrence, or adjust --expect.\n"
            % (count, args.expect))
        return 1

    n = count if args.all else 1
    new_content = content.replace(args.old, args.new, n)

    try:
        write_with_encoding(args.file, new_content, enc, newline='')
    except UnicodeEncodeError as e:
        sys.stderr.write(
            "ERROR: new_string contains character(s) not representable in %s: %s\n"
            "File NOT modified. Use a different wording or convert the file to UTF-8.\n"
            % (enc, e))
        return 1

    print("OK: replaced %d occurrence(s) in %s (encoding %s preserved)"
          % (n, args.file, enc))
    return 0


def cmd_convert(args):
    """Convert a file from its current encoding to a different encoding in-place."""
    enc = args.encoding or detect_encoding(args.file)
    if enc == 'binary':
        sys.stderr.write("ERROR: cannot convert binary file\n")
        return 1
    if enc == args.to:
        print("OK: already %s, no conversion needed" % enc)
        return 0

    content = read_with_encoding(args.file, enc, newline='')
    try:
        write_with_encoding(args.file, content, args.to, newline='')
    except UnicodeEncodeError as e:
        sys.stderr.write(
            "ERROR: content contains character(s) not representable in %s: %s\n"
            "File NOT modified (atomic write left the original intact).\n"
            % (args.to, e))
        return 1

    print("OK: converted %s -> %s" % (enc, args.to))
    return 0


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

def main():
    # Ensure stdout is UTF-8 even on Windows console/pipe (default code page
    # cp936/cp1252 would mojibake the decoded Chinese content Claude reads).
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description='File encoding detection & conversion toolkit')
    parser.add_argument('--version', action='version', version='encoding_utils.py ' + __version__)
    sub = parser.add_subparsers(dest='command')

    p_detect = sub.add_parser('detect', help='Detect file encoding')
    p_detect.add_argument('file', help='File path')

    p_read = sub.add_parser('read', help='Read file, print to stdout as UTF-8')
    p_read.add_argument('file', help='File path')
    p_read.add_argument('--encoding', '--enc', default=None, dest='encoding',
                        help='Encoding override (default: auto-detect)')
    p_read.add_argument('--max-lines', type=int, default=None, dest='max_lines',
                        help='Only print the first N lines (saves tokens on large files)')

    p_write = sub.add_parser('write', help='Write stdin to file with specified encoding')
    p_write.add_argument('file', help='File path')
    p_write.add_argument('--encoding', '--enc', required=True, dest='encoding',
                         help='Target encoding (e.g. gbk, utf-8-bom, utf-16-le-bom)')

    p_safe_write = sub.add_parser('safe-write', help='Auto-detect encoding + full file rewrite from stdin')
    p_safe_write.add_argument('file', help='File path')
    p_safe_write.add_argument('--encoding', '--enc', default=None, dest='encoding',
                              help='Encoding for new files (required if file does not exist)')

    p_convert = sub.add_parser('convert', help='Convert file to a different encoding in-place')
    p_convert.add_argument('file', help='File path')
    p_convert.add_argument('--to', required=True, dest='to',
                           help='Target encoding (e.g. utf-8, gbk, utf-8-bom)')
    p_convert.add_argument('--encoding', '--enc', default=None, dest='encoding',
                           help='Source encoding override (default: auto-detect)')

    p_replace = sub.add_parser('replace', help='Precise replacement preserving file encoding')
    p_replace.add_argument('file', help='File path')
    p_replace.add_argument('--old', required=True, help='Text to find (exact match)')
    p_replace.add_argument('--new', required=True, help='Replacement text')
    p_replace.add_argument('--encoding', '--enc', default=None, dest='encoding',
                           help='Encoding override (default: auto-detect)')
    p_replace.add_argument('--all', action='store_true',
                           help='Replace every occurrence (default: first only)')
    p_replace.add_argument('--expect', type=int, default=None,
                           help='Expected number of occurrences; abort if different')

    args = parser.parse_args()

    if args.command == 'detect':
        return cmd_detect(args)
    elif args.command == 'read':
        return cmd_read(args)
    elif args.command == 'write':
        return cmd_write(args)
    elif args.command == 'safe-write':
        return cmd_safe_write(args)
    elif args.command == 'convert':
        return cmd_convert(args)
    elif args.command == 'replace':
        return cmd_replace(args)
    else:
        parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main())