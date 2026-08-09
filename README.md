# artifact-skills

Claude Code agent skills collection.

## Skills

| Skill | Description |
|-------|-------------|
| [file-encoding](./skills/file-encoding/) | Guard hooks for multi-encoding files (ANSI/GBK/UTF-8/UTF-16): blocks unsafe edits, steers Claude to transcode tools |

## Install

### Pi (coding agent)

This repository is also a [Pi package](./package.json) (`pi-package` keyword).
The Pi extension (`skills/file-encoding/pi/file-encoding.ts`) blocks unsafe
native edits on non-UTF-8 files and rewrites `read` results with decoded
content. Install the Python detection library first:

```bash
python skills/file-encoding/scripts/install_deps.py
```

```bash
pi install git:github.com/longhun12346/artifact-skills
# or, via npm:
pi install npm:@longhun12346/file-encoding
```

See [pi/README.md](./skills/file-encoding/pi/README.md) for details.

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
- Windows 10/11 (tested), Linux/WSL2 Fedora (tested), macOS (untested)

## License

MIT
