---
name: file-encoding
description: Transparent encoding handling for Windows C++ projects. Automatically converts non-UTF-8 files (ANSI/GBK/UTF-8 BOM/UTF-16 LE BOM) before Edit/Write/Read and restores encoding after — no special commands needed.
version: 2.0.0
author: longhun12346
license: MIT
tags: [encoding, windows, cpp, ansi, gbk, utf-16, nsis, hook]
---

# file-encoding

## How it works

This skill installs **transparent hooks** that handle file encoding automatically:

1. **Before** Edit/Write/Read: detects encoding → converts non-UTF-8 files to UTF-8 in place
2. Claude's tool runs normally on the UTF-8 file
3. **After** Edit/Write/Read: converts back to original encoding

**You don't need to do anything special.** Just use Edit/Write/Read normally — the hooks handle encoding invisibly.

## When it activates

- Only on monitored extensions: `.cpp` `.h` `.hpp` `.c` `.cc` `.cxx` `.rc` `.bat` `.nsi` `.ini` `.xml`
- Only when encoding is non-UTF-8 (GBK, Shift-JIS, EUC-KR, Big5, UTF-8 BOM, UTF-16 LE BOM)
- UTF-8 files pass through with minimal overhead (~70ms subprocess startup)

## Supported encodings

### Auto-converted (hook converts to/from UTF-8)

| Category | Encodings | Typical file types | Detection reliability |
|----------|-----------|-------------------|---------------------|
| CJK multibyte | gbk, shift-jis, euc-kr, big5 | `.cpp` `.h` `.rc` `.bat` | High (distinctive byte patterns) |
| Cyrillic | windows-1251 | `.cpp` `.h` `.rc` | High (chardet reliable for Cyrillic) |
| Unicode BOM | utf-8-bom | `.nsi` | Exact (BOM prefix) |
| UTF-16 | utf-16-le-bom, utf-16-be-bom | `.ini` | Exact (BOM prefix) |

### Pass-through (no conversion needed)

| Category | Encodings | Reason |
|----------|-----------|--------|
| UTF-8 / ASCII | utf-8, ascii | Claude native support |
| Western single-byte | windows-1252, windows-1250, iso-8859-1/2 | High bytes rare in source code |
| Other single-byte | windows-1253~1258 | Same; detection unreliable between these |
| Binary | binary | Not text |

### Design rationale

- **CJK + Cyrillic → convert**: byte patterns distinctive, chardet reliable, non-ASCII content is substantial (Claude cannot understand without conversion)
- **Western single-byte → pass-through**: hard to distinguish between these encodings reliably; incorrect conversion risks data corruption; non-ASCII bytes rare in source code (occasional accented chars in comments)
- If `chardet` is not installed, heuristic fallback may misidentify Shift-JIS / EUC-KR as GBK on Chinese Windows. Install `chardet` for reliable results.

## New file creation

The hooks only convert **existing** files. When creating new files with Write, the file will be UTF-8 by default.

If the project requires a different encoding for new files (e.g., GBK for `.cpp`), use encoding_utils.py:

```bash
# Check what encoding siblings use
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py detect "existing_file.cpp"

# Write new file with that encoding
echo "content" | python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py safe-write "new_file.cpp" --enc gbk
```

## Manual commands (encoding_utils.py)

For operations outside the hook cycle (batch conversion, explicit encoding control):

```
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py detect <file>
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py read <file> [--enc E]
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py write <file> --enc E
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py convert <file> --to E [--enc F]
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py safe-write <file> [--enc E]
```

## Crash recovery

If Claude Code crashes mid-operation (file left in UTF-8 state):

```bash
python ${CLAUDE_SKILL_DIR}/scripts/encoding_transparent.py recover
```

## Installation

```bash
python ${CLAUDE_SKILL_DIR}/scripts/install_hook.py           # install hooks
python ${CLAUDE_SKILL_DIR}/scripts/install_hook.py --check   # verify installation
python ${CLAUDE_SKILL_DIR}/scripts/install_hook.py --uninstall  # remove hooks
```

## Limitations

1. **New files default to UTF-8** — Write creates files as UTF-8. If the project requires GBK/other encoding for new `.cpp`/`.h` files, you must explicitly use `encoding_utils.py safe-write --enc`.

2. **Concurrent sessions** — File locking prevents state corruption, but two sessions converting the same file simultaneously may still produce unexpected results. In practice this is rare (one session per project).

3. **Process kill without PostToolUse** — If Claude Code is forcefully killed between Pre and Post, the file remains in temporary UTF-8 state. Run `encoding_transparent.py recover` to restore, or the file will stay UTF-8 until the next Pre/Post cycle.

4. **Only monitored extensions** — Files outside `.cpp/.h/.hpp/.c/.cc/.cxx/.rc/.bat/.nsi/.ini/.xml` are not handled, even if they have non-UTF-8 encoding. Add extensions to `MONITORED_EXTENSIONS` in `encoding_transparent.py` if needed.

5. **Encoding detection without chardet** — Without `chardet`, detection uses a heuristic fallback that tries codecs in order. This can misidentify Shift-JIS/EUC-KR as GBK on Chinese Windows. Install `chardet` for reliable results.

## Debugging

Set `ENCODING_TRANSPARENT_DEBUG=1` to see conversion details on stderr:

```bash
set ENCODING_TRANSPARENT_DEBUG=1 && claude
```

## Tested environment

| Item | Detail |
|------|--------|
| Agent | Claude Code (Claude Sonnet 4 / Opus 4) |
| OS | Windows 10/11 x64 |
| Python | 2.7, 3.8+  |
| chardet | 5.x (recommended) |
| Test project | pc-international (C++ / NSIS, mixed GBK + UTF-8 BOM + UTF-16 LE BOM) |

> Linux / macOS not yet validated. The hook logic is platform-agnostic; only path separators and temp dir differ.

## Requirements

- Python 2.6+ or 3.x
- **Recommended:** `chardet` for reliable encoding detection (`pip install chardet`)
