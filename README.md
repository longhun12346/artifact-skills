# artifact-skills

Claude Code agent skills collection.

## Skills

| Skill | Description |
|-------|-------------|
| [file-encoding](./skills/file-encoding/) | Guard hooks for multi-encoding files (ANSI/GBK/UTF-8/UTF-16): blocks unsafe edits, steers Claude to transcode tools |

## Install

### Claude Code plugin (recommended)

This repository is a [Claude Code plugin marketplace](./.claude-plugin/marketplace.json):

```bash
claude plugin marketplace add longhun12346/artifact-skills
claude plugin install artifact-skills file-encoding
```

The plugin registers the encoding guard hooks automatically. Then install the
Python detection library (required for reliable encoding detection):

```bash
python skills/file-encoding/scripts/install_deps.py
```

### Manual

Copy the skill directory to `~/.claude/skills/` and register hooks manually:

```bash
cp -r skills/file-encoding ~/.claude/skills/
```

## Requirements

- Claude Code
- Python 3.9+
- Windows (tested), Linux/macOS (untested)

## License

MIT
