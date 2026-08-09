# File Encoding Skill for Claude Code

Encoding guard for Windows C++ projects: ANSI (GBK/Shift-JIS/EUC-KR/Big5), UTF-8 BOM, UTF-16 LE/BE BOM. **Inform-only mode (v3): the hooks NEVER modify files.** They detect non-UTF-8 files, block unsafe native Edit/Write/MultiEdit, and instruct Claude to use the transcode tools (`encoding_utils.py read/replace/safe-write`).

## How It Works

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│ PreToolUse  │────▶│  Claude uses     │────▶│ PostToolUse │
│ detect enc  │     │  encoding_utils  │     │ verify enc  │
│ block unsafe│     │  read/replace    │     │ (warn only) │
└─────────────┘     └──────────────────┘     └─────────────┘
```

- `Read` on non-UTF-8 → informational hint (use `encoding_utils.py read`)
- `Edit`/`Write`/`MultiEdit` on non-UTF-8 → **blocked** (exit 2) with instructions
- UTF-8 / ASCII / safe single-byte files pass through untouched
- Files are never converted, backed up, or locked by the hook

## Why v3 (previously: transparent conversion)

Versions 1–2 converted files to UTF-8 before each tool call and restored them
after. That in-place rewriting carried corruption and data-loss risk (crash
between hooks, Post failure discarding edits, un-matched MultiEdit). v3 trades
hidden conversion for an explicit, auditable workflow.

## Installation (Claude Code plugin)

```bash
claude plugin marketplace add longhun12346/artifact-skills
claude plugin install artifact-skills file-encoding

# Python detection library (required for reliable encoding detection)
python scripts/install_deps.py          # or: pip install -r requirements.txt
python scripts/install_deps.py --check
```

The plugin's `hooks/hooks.json` registers the guard hooks automatically.

## Requirements

- Python 3.9+ (charset-normalizer 3.x)
- **Required:** `charset-normalizer` (auto-installed by `install_deps.py`)
- **Optional:** `chardet` (legacy detection fallback)

## File Structure

```
.claude-plugin/plugin.json  - Plugin manifest (hooks auto-registered)
hooks/hooks.json            - PreToolUse/PostToolUse hook configuration
SKILL.md                    - Skill documentation (this skill's knowledge)
scripts/encoding_transparent.py  - Hook entry point (pre/post/recover modes)
scripts/encoding_utils.py        - Encoding detection, safe read/replace/write tools
scripts/install_deps.py          - Dependency bootstrap (charset-normalizer)
```

## Crash Recovery

Hooks never modify files, so there is nothing to restore. To clean up leftover
state files:

```bash
python scripts/encoding_transparent.py recover
```

## Testing

```bash
cd scripts
python -m unittest discover -s . -p "test_*.py" -v
```

## License

MIT
