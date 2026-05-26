---
name: file-encoding
description: Handles multi-encoding files (ANSI/UTF-8/UTF-16 LE BOM) in Windows C++ projects. Detect encoding before editing .cpp/.h/.rc/.nsi/.ini/.xml/.bat files to avoid corruption.
version: 1.6.2
author: longhun12346
license: MIT
tags: [encoding, windows, cpp, ansi, gbk, utf-16, nsis]
---

# file-encoding

## When to trigger

**With hook installed** (`encoding_guard.py` as PreToolUse): automatic — the hook detects project
membership and file encoding, blocking unsafe Edit/Write before any file is touched. No manual
trigger needed.

**Without hook**: apply manually on **Windows + C++ projects** before editing `.cpp`/`.h`/`.rc`/
`.bat`/`.nsi`/`.ini` files. Skip for non-Windows or pure frontend projects (everything is UTF-8).

C++ project detection: `.vcxproj` / `CMakeLists.txt` / `stdafx.h` / `#include <windows.h>` etc.

## Encoding rules

| File type | Encoding | Notes |
|-----------|----------|-------|
| `.cpp` `.h` `.rc` | **System ANSI** | GBK / Shift-JIS / EUC-KR / Big5 depending on system locale |
| `.bat` (build scripts) | **System ANSI** | CMD reads as ANSI; UTF-8 without BOM garbles non-ASCII |
| `.nsi` | UTF-8 BOM or UTF-16 LE BOM | Never assume, always `detect` |
| `.ini` (GetPrivateProfileStringW) | **UTF-16 LE BOM** | Non-ASCII garbled without BOM |
| `.xml` | UTF-8 | |

## Commands

Uses `scripts/encoding_utils.py`. Supports Python 2.6+/3.x.

> **Strongly recommended:** install `chardet` (`pip install chardet`). Without it, encoding detection
> uses a heuristic fallback that can misidentify Shift-JIS / EUC-KR files as GBK on Chinese Windows.

```
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py detect <file>
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py read <file> [--enc E]
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py write <file> --enc E
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py replace <file> --old S --new T [--enc E]
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py safe-edit <file> --old S --new T
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py safe-write <file> [--enc E]
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py convert <file> --to E [--enc F]
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py --version
```

Encoding names: `gbk` `shift-jis` `euc-kr` `big5` `utf-8` `utf-8-bom` `utf-16-le-bom` `utf-16` `windows-1252` `iso-8859-1` etc.

## Edit workflow

### Existing files

```
detect -> utf-8 (no BOM) -> Edit/Write tools OK
detect -> utf-8-bom      -> safe-edit or replace   (BOM ≠ utf-8! Edit tool may strip BOM)
detect -> other (GBK...) -> safe-edit or replace
                          -> read -> edit tmp.txt -> write (complex edits)
```

**`utf-8-bom` is NOT `utf-8`.** The BOM makes them different. Edit/Write tools treat `utf-8-bom` as plain UTF-8 and may strip or corrupt the BOM. NSI/Python build scripts depend on BOM — if stripped, NSIS/MSVC reads garbled text.

```bash
# Partial edit: safe-edit (auto-detect + replace, one command, safe for ALL encodings)
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py safe-edit "file.cpp" --old "old" --new "new"

# Full file rewrite: safe-write (auto-detect + overwrite from stdin)
# NEVER use raw Python open()/write() for non-UTF-8 files — use safe-write instead
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py safe-write "file.ini" < new_content.txt

# Explicit replace (same safety, allows --enc override)
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py replace "file.cpp" --old "old" --new "new"

# utf-8 (no BOM) only: Edit tool shortcuts are fine
# e.g. Edit("file.xml", old, new) or Write("file.xml", content) — XML files are UTF-8
```

### New files

**Do not use Write tool for non-UTF-8 files.** Detect encoding of existing files of the same type first, then create:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py detect "existing.cpp"
echo "content" | python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py safe-write "new.cpp" --enc gbk
```

## Pitfalls

- **`utf-8-bom` ≠ `utf-8`** — Edit/Write tools may strip BOM. `detect` first, use `safe-edit` if result is `utf-8-bom`.
- **Edit/Write on GBK/ANSI/UTF-16** -> garbled text. Use `safe-edit`, `replace`, or read->edit->write.
- **`.nsi` encoding not fixed** -> UTF-8 BOM or UTF-16 LE BOM. Always `detect` first.
- **INI without BOM** -> `GetPrivateProfileStringW` reads as ANSI, corrupting non-ASCII. Must be UTF-16 LE BOM.
- **Python `\6` octal escape** -> in non-raw strings, `Software\kingsoft\Office\6.0` has hidden control chars. Use raw string `r'...'` or `\\\\`.
- **Py2 `open()` no `encoding=`** -> use `io.open()`. encoding_utils.py handles this.
- **Raw Python for full rewrite** -> NEVER use `open(f,'wb').write(b'\xff\xfe' + content.encode('utf-16-le'))` — use `safe-write` instead. It auto-detects encoding, no manual BOM handling needed.

## Hook-based enforcement (recommended)

`scripts/encoding_guard.py` is a Claude Code `PreToolUse` hook that **blocks** Edit/Write at the execution
level before any file is touched. More reliable than prompt-only instructions.

### What it does

- **Existing files**: detects encoding; blocks if non-UTF-8, prints `safe-edit` / `read-write` command.
- **New files**: scans sibling files of same extension to infer project convention; blocks if expected
  encoding is non-UTF-8, prints `write --enc` command. Falls back to per-extension defaults when no
  siblings exist.
- **Project scope**: only monitors files inside a recognised project root (`.git` / `.svn` / `.hg` / `CMakeLists.txt` / `*.vcxproj` / `*.sln` / `setup.py` / `pyproject.toml`); files in temp dirs or outside any project pass through.
- **Scope filter**: only fires on extensions in `MONITORED_EXTENSIONS`; all other files pass through.
- **Fail-open**: any script error → exit 0 (allow), never blocks unrelated edits.

### Installation

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
            "command": "python ${CLAUDE_SKILL_DIR}/scripts/encoding_guard.py"
          }
        ]
      }
    ]
  }
}
```

On Windows, replace `python` with the full Python path if needed (e.g. `C:\\Python39\\python.exe`).