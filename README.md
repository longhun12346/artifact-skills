# artifact-skills

Claude Code agent skills collection.

## Skills

| Skill | Description |
|-------|-------------|
| [file-encoding](./skills/file-encoding/) | Detect & edit multi-encoding files (ANSI/UTF-8/UTF-16) in Windows C++ projects |

## Install

### gh skill (recommended)

```bash
gh skill install longhun12346/artifact-skills file-encoding
```

Search available skills:

```bash
gh skill search file-encoding
```

### Manual

Copy the skill directory to `~/.claude/skills/`:

```bash
cp -r skills/file-encoding ~/.claude/skills/
```

## Requirements

- Claude Code
- Python 2.7+ or Python 3.x
- Windows (tested), Linux/macOS (untested)

## License

MIT