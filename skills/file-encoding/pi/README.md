# file-encoding for Pi

Pi extension that guards non-UTF-8 files (GBK / Shift-JIS / Big5 / windows-1251 /
UTF-16 BOM) in Windows C++ projects. It **reuses the same Python backend**
(`../scripts/encoding_utils.py`) as the Claude Code version, so detection
behavior and the 104 unit tests carry over.

## Why Pi needs this

Pi's native `read`/`edit` tools assume UTF-8:

- `read` on a GBK file → mojibake (the model cannot understand the file)
- `edit` on a GBK file → **bytes are replaced with U+FFFD and written back —
  the original data is irreversibly lost**

This extension blocks unsafe edits before they happen and rewrites `read`
results so the model sees real content.

## What it does

| Event | Behavior |
|-------|----------|
| `tool_call` on `edit`/`write` | Detect encoding → non-UTF-8 file → **block** with instructions to use `encoding_utils.py replace` / `read` |
| `tool_result` on `read` | Detect encoding → non-UTF-8 file → **rewrite result** with correctly decoded content (fully transparent, no tool switching) |

Detection results are cached per file (mtime+size), so repeat operations skip
the ~200ms Python subprocess + charset-normalizer import.

## Requirements

- Pi (agent harness)
- Python 3.9+ with `charset-normalizer` — install via:

  ```bash
  python ../scripts/install_deps.py
  ```

  (or `pip install -r ../requirements.txt`)

- Override the Python interpreter with `ENCODING_PYTHON` env var if `python` is
  not on PATH.

## Install

### From this repository (git)

```bash
pi install git:github.com/longhun12346/artifact-skills
```

This registers the extension and the `file-encoding` skill. Restart Pi (or
start a new session).

### Local development

```bash
# load the extension + skill for one run
pi -e ./skills/file-encoding/pi/file-encoding.ts

# or copy the extension into project-local location
mkdir -p .pi/extensions && cp skills/file-encoding/pi/file-encoding.ts .pi/extensions/
```

## Publish to the community

Pi packages are distributed through **npm** or **git**; the repository already
declares a `pi` manifest in `package.json` (keyword `pi-package`), which also
makes it appear in the [Pi package gallery](https://pi.dev/packages).

### Via git (already works)

```bash
# anyone can install after a push:
pi install git:github.com/longhun12346/artifact-skills
```

### Via npm

Published as [`@longhun12346/file-encoding`](https://www.npmjs.com/package/@longhun12346/file-encoding):

```bash
npm publish                 # from the repository root (runs prepublish check)
pi install npm:@longhun12346/file-encoding
```

## Limitations

- **Python backend required**: detection runs via subprocess; without Python or
  `charset-normalizer` the extension silently leaves files alone (fail-open).
- **`read` rewrite ignores `offset`/`limit`**: a paged read of a non-UTF-8 file
  is rewritten with the full content (the model should not page GBK files
  anyway).
- Encoding name sets (`MONITORED_EXTENSIONS`, `SAFE_ENCODINGS`) are mirrored
  from `encoding_transparent.py`; keep them in sync when changing either.
