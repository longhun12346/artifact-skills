# File Encoding Skill for Claude Code

Handles multi-encoding source files in Windows C++ projects: ANSI (GBK/Shift-JIS/EUC-KR/Big5), UTF-8 BOM, UTF-16 LE BOM. Prevents encoding corruption when using Claude Code's Edit/Write tools which default to UTF-8.

> **Note:** Currently tested on Windows only (Python 2.7 & 3.x). Linux/macOS may work but not validated.

## Installation

### gh skill (recommended)

```bash
gh skill install <owner>/artifact-skills file-encoding
```

Or search first:
```bash
gh skill search file-encoding
gh skill preview <owner>/artifact-skills file-encoding
```

### Manual

```bash
mkdir -p ~/.claude/skills/file-encoding/scripts
cp SKILL.md ~/.claude/skills/file-encoding/
cp scripts/encoding_utils.py ~/.claude/skills/file-encoding/scripts/
cp scripts/encoding_guard.py ~/.claude/skills/file-encoding/scripts/
```

Restart Claude Code. The skill auto-loads.

## Hook-based enforcement (recommended)

Install `encoding_guard.py` as a `PreToolUse` hook to enforce encoding rules at the **execution level**,
blocking Edit/Write before any file is touched — more reliable than prompt-only instructions.

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "python ~/.claude/skills/file-encoding/scripts/encoding_guard.py"
          }
        ]
      }
    ]
  }
}
```

**Windows path example:**
```json
"command": "python C:\\Users\\<you>\\.claude\\skills\\file-encoding\\scripts\\encoding_guard.py"
```

The hook:
- Blocks Edit/Write on existing files with non-UTF-8 encodings
- Blocks Write for new files when siblings/defaults indicate non-UTF-8 convention
- Only fires on monitored extensions (`.cpp .h .rc .bat .nsi .ini .py .xml`)
- Fail-open: any script error allows the tool call through

## Requirements

- Python 2.6+ or Python 3.x
- **Strongly recommended: `chardet`** — without it, encoding detection falls back to a heuristic that
  tries each codec in order and accepts the first that doesn't raise an exception. This can misidentify
  Shift-JIS / EUC-KR files as GBK on Chinese Windows, leading to missed blocks or false positives.

  ```bash
  pip install chardet
  ```

## Quick Start

```bash
# Detect encoding
python scripts/encoding_utils.py detect main.cpp
# -> gbk

# Read file with detected encoding
python scripts/encoding_utils.py read main.cpp

# Replace string, preserve encoding
python scripts/encoding_utils.py replace main.cpp --old "old" --new "new"

# Complex edit: read, modify, write back
python scripts/encoding_utils.py read main.cpp > tmp.txt
# ... edit tmp.txt with any UTF-8 editor ...
python scripts/encoding_utils.py write main.cpp --enc gbk < tmp.txt

# Create new file with project encoding
python scripts/encoding_utils.py detect existing.cpp     # -> gbk
python scripts/encoding_utils.py write new.cpp --enc gbk < content.txt
```

## Supported Encodings

| Category | Encodings |
|----------|-----------|
| CJK ANSI | gbk, shift-jis, euc-kr, big5 |
| European | windows-1250 ~ 1258, iso-8859-1, iso-8859-2 |
| Unicode | utf-8, utf-8-bom, utf-16-le-bom, utf-16 |

## How It Works

1. **detect**: Checks BOM first, then tries chardet (if available), then decodes with common code pages
2. **replace**: Detects encoding, reads, applies str.replace, writes back with same encoding
3. **read/write**: stdin/stdout pipeline, UTF-8 in transit, target encoding on disk
4. **Binary guard**: Detects null bytes, returns `binary` instead of corrupting

## Use Cases

- Editing MSVC `.cpp`/`.h` files saved in system ANSI (GBK on Chinese Windows)
- Editing `.bat` build scripts (CMD reads as ANSI, UTF-8 garbles non-ASCII)
- Editing NSIS `.nsi` installer scripts (UTF-8 BOM or UTF-16 LE BOM)
- Editing `.ini` files read by `GetPrivateProfileStringW` (must be UTF-16 LE BOM)
- Editing Python build scripts with BOM-sensitive toolchains
- Converting legacy ANSI project files to UTF-8 (`convert --to utf-8`)

## Troubleshooting

### Hook not firing

- Verify `settings.json` has the correct Python path (use full path on Windows if `python` is not in `PATH`)
- Test the hook manually:
  ```bash
  echo {"tool_name":"Edit","tool_input":{"file_path":"test.cpp"}} | python encoding_guard.py
  ```
- Set `ENCODING_GUARD_DEBUG=1` to echo block messages to stderr:
  ```bash
  set ENCODING_GUARD_DEBUG=1 && claude
  ```

### Encoding detected incorrectly

- Install `chardet` for reliable detection: `pip install chardet`
- Verify detection: `python encoding_utils.py detect <file>`
- Override manually: `python encoding_utils.py read <file> --enc gbk`

### Hook blocks files it shouldn't

- Files outside any project root (no `.git` / `CMakeLists.txt` / `*.vcxproj` etc.) are auto-allowed — check that the project has a recognised root marker
- Files detected as `windows-1252` / `iso-8859-*` are treated as safe (common chardet false positive on near-ASCII UTF-8 content); if a file is genuinely Windows-1252, add it to your project with a recognised root marker

### Python 2 notes

- `open()` has no `encoding=` parameter in Python 2; use `io.open()` instead
- `encoding_utils.py` handles this internally for all its commands

## License

MIT