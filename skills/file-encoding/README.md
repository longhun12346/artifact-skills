# File Encoding Skill for Claude Code

Transparent encoding handling for Windows C++ projects: ANSI (GBK/Shift-JIS/EUC-KR/Big5), UTF-8 BOM, UTF-16 LE BOM. Files are automatically converted to UTF-8 before Claude's tools run, and restored to original encoding after — no special commands or encoding awareness needed.

> See [Tested Environment](#tested-environment) for validated platforms.

## How It Works

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ PreToolUse  │────▶│  Claude Edit  │────▶│ PostToolUse │
│ GBK → UTF-8 │     │  (normal)    │     │ UTF-8 → GBK │
└─────────────┘     └──────────────┘     └─────────────┘
```

1. **PreToolUse hook** detects file encoding → converts to UTF-8 → saves state
2. **Claude's tool** (Edit/Write/Read) operates on UTF-8 file normally
3. **PostToolUse hook** reads state → converts back to original encoding

Claude never needs to know about encoding. No `safe-edit`, no JSON piping, no triple escaping.

## Installation

### Quick Install

```bash
cd skills/file-encoding/scripts
python setup.py
```

This registers the hooks in `~/.claude/settings.json`. Restart Claude Code to activate.

### Manual

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|Read",
        "hooks": [
          {
            "type": "command",
            "command": "python /path/to/scripts/encoding_transparent.py pre"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write|Read",
        "hooks": [
          {
            "type": "command",
            "command": "python /path/to/scripts/encoding_transparent.py post"
          }
        ]
      }
    ]
  }
}
```

### Uninstall

```bash
python scripts/setup.py --uninstall
```

## Requirements

- Python 2.6+ or Python 3.x
- **Strongly recommended: `chardet`** — without it, encoding detection falls back to a heuristic that can misidentify Shift-JIS / EUC-KR files as GBK on Chinese Windows.

  ```bash
  pip install chardet
  ```

## Tested Environment

| Item | Detail |
|------|--------|
| Agent | Claude Code (Claude Sonnet 4 / Opus 4) |
| OS | Windows 10/11 x64 |
| Python | 2.7, 3.8+ |
| chardet | 5.x |
| Test project | pc-international (C++ / NSIS, mixed GBK + UTF-8 BOM + UTF-16 LE BOM files) |
| Test suite | 56 unit tests (encoding_utils) + 24 hook tests (encoding_transparent) |

> **Note:** Linux / macOS not yet validated. The hook logic is platform-agnostic (only temp dir path and path separators differ).

## Supported Encodings

### Auto-converted (hook converts to/from UTF-8)

| Category | Encodings | Detection | Notes |
|----------|-----------|-----------|-------|
| CJK multibyte | gbk, shift-jis, euc-kr, big5 | High (distinctive byte patterns) | Chinese/Japanese/Korean source code |
| Cyrillic | windows-1251 | High (chardet reliable) | Russian source code |
| Unicode BOM | utf-8-bom | Exact (BOM prefix) | NSIS scripts, some editors add BOM |
| UTF-16 | utf-16-le-bom, utf-16-be-bom | Exact (BOM prefix) | INI files, some Windows tools |

### Pass-through (no conversion, Claude handles natively)

| Category | Encodings | Reason |
|----------|-----------|--------|
| UTF-8 / ASCII | utf-8, ascii | Claude native support |
| Western single-byte | windows-1252, windows-1250, iso-8859-1/2 | High bytes rare in code; detection unreliable between these |
| Other single-byte | windows-1253~1258 (Greek, Turkish, Arabic, Hebrew, Baltic, Vietnamese) | Same as above |
| Binary | binary | Not text, skipped |

### Design rationale

The dividing line between "convert" and "pass-through" is:

- **Convert**: encoding is reliably detectable AND non-ASCII content is substantial (Claude cannot understand without conversion)
- **Pass-through**: encoding is hard to distinguish reliably between similar single-byte variants; incorrect detection → data corruption risk; non-ASCII bytes are rare in typical source code

Without `chardet`, the heuristic fallback may misidentify Shift-JIS / EUC-KR as GBK on Chinese Windows. Always install `chardet`.

## Scope

The hooks only fire when ALL conditions are met:
- File extension is monitored (`.cpp .h .hpp .c .cc .cxx .rc .bat .nsi .ini .xml`)
- File is inside a project root (`.git` / `.svn` / `.hg` / `CMakeLists.txt` / `*.vcxproj` / `*.sln`)
- Encoding is non-UTF-8

All other files pass through untouched with minimal overhead (~70ms for the project-root check).

## New File Creation

The hooks handle **existing** files only. New files created by Write are UTF-8 by default.

To create a new file matching the project's encoding convention:

```bash
# Check encoding of existing files
python scripts/encoding_utils.py detect existing.cpp
# -> gbk

# Create new file with that encoding
echo "content" | python scripts/encoding_utils.py safe-write new.cpp --enc gbk
```

## encoding_utils.py Commands

Standalone utility for manual operations:

```bash
# Detect encoding
python scripts/encoding_utils.py detect main.cpp
# -> gbk

# Read non-UTF-8 file as UTF-8 to stdout
python scripts/encoding_utils.py read main.cpp

# Write stdin to file with specific encoding
python scripts/encoding_utils.py write main.cpp --enc gbk

# Convert encoding in-place
python scripts/encoding_utils.py convert main.cpp --to utf-8

# Auto-detect + overwrite from stdin (preserve encoding)
python scripts/encoding_utils.py safe-write main.cpp < content.txt

# JSON-based replacement (preserves encoding)
echo '{"old":"old_text","new":"new_text"}' | python scripts/encoding_utils.py safe-edit main.cpp
```

## Crash Recovery

If Claude Code crashes mid-operation, files may be left in temporary UTF-8 state. To restore:

```bash
python scripts/encoding_transparent.py recover
```

## Limitations

1. **New files default to UTF-8** — The hooks only convert existing files. Write tool creates new files as UTF-8. If the project convention is GBK (or other encoding), use `encoding_utils.py safe-write --enc` for new files.

2. **Concurrent sessions** — Two Claude sessions editing the same non-UTF-8 file simultaneously may conflict (state file race condition). In practice this is rare.

3. **Process kill** — If Claude Code is killed (not graceful exit) between PreToolUse and PostToolUse, the file stays in temporary UTF-8 state. Use `python scripts/encoding_transparent.py recover` to restore all affected files.

4. **Only monitored extensions** — `.cpp .h .hpp .c .cc .cxx .rc .bat .nsi .ini .xml`. Other file types with non-UTF-8 encoding (e.g. `.txt`, `.properties`) are not automatically handled. Edit `MONITORED_EXTENSIONS` in `encoding_transparent.py` to add more.

5. **Encoding detection accuracy** — Without `chardet`, heuristic detection may misidentify encodings (e.g. Shift-JIS reported as GBK on Chinese Windows). Always install `chardet`.

## Troubleshooting

### Hooks not firing

- Run `python scripts/setup.py --check` to verify installation
- Use full Python path on Windows if `python` is not in PATH
- Set `ENCODING_TRANSPARENT_DEBUG=1` to see hook diagnostics:
  ```bash
  set ENCODING_TRANSPARENT_DEBUG=1 && claude
  ```

### Encoding detected incorrectly

- Install `chardet`: `pip install chardet`
- Verify: `python scripts/encoding_utils.py detect <file>`

### Upgrading from v1.x (encoding_guard)

Run `python scripts/setup.py` — it automatically removes the old blocking hook and installs the new transparent hooks.

## Architecture

```
encoding_transparent.py  - Hook entry point (pre/post/recover modes)
encoding_utils.py        - Encoding detection & file I/O library
setup.py                 - Hook installer/uninstaller
```

## License

MIT
