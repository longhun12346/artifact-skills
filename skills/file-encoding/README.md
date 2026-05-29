# File Encoding Skill for Claude Code

Transparent encoding handling for Windows C++ projects: ANSI (GBK/Shift-JIS/EUC-KR/Big5), UTF-8 BOM, UTF-16 LE BOM. Files are automatically converted to UTF-8 before Claude's tools run, and restored to original encoding after.

## How It Works

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ PreToolUse  │────▶│  Claude Edit  │────▶│ PostToolUse │
│ GBK → UTF-8 │     │  (normal)    │     │ UTF-8 → GBK │
└─────────────┘     └──────────────┘     └─────────────┘
```

## Installation

```bash
cd skills/file-encoding/scripts
python install_hook.py
```

Uninstall: `python install_hook.py --uninstall`

Check status: `python install_hook.py --check`

## Requirements

- Python 3.8+ (Python 2.7 compatible but untested in CI)
- **Recommended:** `pip install chardet` for reliable encoding detection

## File Structure

```
encoding_transparent.py  - Hook entry point (pre/post/recover modes)
encoding_utils.py        - Encoding detection & file I/O library
install_hook.py          - Hook installer/uninstaller
```

## Crash Recovery

```bash
python scripts/encoding_transparent.py recover
```

## Debugging

```bash
set ENCODING_TRANSPARENT_DEBUG=1 && claude
```

## Testing

```bash
cd skills/file-encoding/scripts
python -m unittest discover -s . -p "test_*.py" -v
```

## License

MIT
