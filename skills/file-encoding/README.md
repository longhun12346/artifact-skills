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
```

Restart Claude Code. The skill auto-loads.

## Requirements

- Python 2.6+ or Python 3.x
- Optional: `chardet` (pip install chardet) for better encoding detection

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

## License

MIT