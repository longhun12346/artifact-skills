# -*- coding: utf-8 -*-
"""encoding_utils.py - File encoding detection & conversion toolkit.

Usage:
  python encoding_utils.py detect <file>              # print encoding name
  python encoding_utils.py read <file> [--enc E]      # print decoded content to stdout
  python encoding_utils.py write <file> --enc E       # read stdin, write with encoding E
  python encoding_utils.py safe-write <file> [--enc E]  # auto-detect + overwrite from stdin
  python encoding_utils.py convert <file> --to E [--enc F]  # convert encoding in-place
  python encoding_utils.py --version                  # print version

Supported encoding names (friendly -> Python):
  gbk, shift-jis, euc-kr, big5, utf-8, utf-8-bom, utf-16-le-bom, utf-16-be-bom,
  windows-1250 ~ windows-1258, iso-8859-1, iso-8859-2

This module is also imported by encoding_transparent.py (the hook) for its
detect_encoding(), read_with_encoding(), write_with_encoding() functions.
"""

__version__ = "2.0.0"

import argparse
import io
import os
import sys
import locale


# ---------------------------------------------------------------------------
# Python 2 compat
# ---------------------------------------------------------------------------
_IS_PY2 = (sys.version_info[0] == 2)
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
    if _IS_PY2:
        raw = sys.stdin.read()
        return raw.decode('utf-8') if isinstance(raw, bytes) else raw
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
    # then chardet, then heuristic ANSI fallback.
    # UTF-8 check must come before chardet/heuristic: single-byte ANSI encodings
    # (e.g. windows-1251) accept almost any byte sequence, so they would win the
    # heuristic race even when the file is valid UTF-8.
    try:
        raw.decode('utf-8')
        return 'utf-8'
    except UnicodeDecodeError:
        pass

    # Try chardet, then heuristic
    try:
        import chardet
        result = chardet.detect(raw)
        if result['confidence'] > 0.7 and result['encoding']:
            enc = result['encoding'].lower()
            return _CODE_PAGE_MAP.get(enc, enc)
    except ImportError:
        pass

    # Heuristic: try system ANSI code page first, then common encodings
    sys_enc = _get_sys_encoding()
    if _IS_WINDOWS:
        fallbacks = ['gbk', 'shift-jis', 'euc-kr', 'big5',
                     'windows-1252', 'windows-1251', 'windows-1250']
    else:
        fallbacks = ['gbk', 'shift-jis', 'euc-kr', 'big5',
                     'iso-8859-1', 'windows-1252']
    seen = set()
    candidates = []
    for enc in ([sys_enc] if sys_enc and sys_enc not in ('utf-8', 'ascii') else []) + fallbacks:
        if enc not in seen:
            seen.add(enc)
            candidates.append(enc)
    for enc in candidates:
        try:
            raw.decode(enc)
            return _CODE_PAGE_MAP.get(enc, enc)
        except Exception:
            pass

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


def write_with_encoding(filepath, content, enc, newline=''):
    """Write unicode content to file, handling BOM for utf-16-le-bom/be-bom.

    Writes BOM prefix + encoded content for UTF-16 BOM variants.
    """
    if enc in _BOM_FOR_ENCODING:
        bom = _BOM_FOR_ENCODING[enc]
        pyenc = _friendly_to_python(enc)
        encoded = content.encode(pyenc)
        with open(filepath, 'wb') as f:
            f.write(bom)
            f.write(encoded)
    else:
        pyenc = _friendly_to_python(enc)
        with io.open(filepath, 'w', encoding=pyenc, newline=newline) as f:
            f.write(content)


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

    if _IS_PY2:
        content = content.encode('utf-8')
    sys.stdout.write(content)
    return 0


def cmd_write(args):
    if not args.encoding:
        sys.stderr.write("ERROR: --encoding required for write\n")
        return 1

    content = _read_stdin_unicode()
    write_with_encoding(args.file, content, args.encoding, newline='')

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
    write_with_encoding(args.file, content, args.to, newline='')

    print("OK: converted %s -> %s" % (enc, args.to))
    return 0


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='File encoding detection & conversion toolkit')
    parser.add_argument('--version', action='version', version='encoding_utils.py ' + __version__)
    sub = parser.add_subparsers(dest='command')

    p_detect = sub.add_parser('detect', help='Detect file encoding')
    p_detect.add_argument('file', help='File path')

    p_read = sub.add_parser('read', help='Read file, print to stdout as UTF-8')
    p_read.add_argument('file', help='File path')
    p_read.add_argument('--encoding', '--enc', default=None, dest='encoding',
                        help='Encoding override (default: auto-detect)')

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
    else:
        parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main())