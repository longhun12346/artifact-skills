---
name: file-encoding
description: Encoding guard for Windows C++ projects. Detects non-UTF-8 files (ANSI/GBK/UTF-16) and instructs Claude to use safe transcode tools instead of native Edit/Write — files are NEVER modified by the hook. Prevents mojibake corruption of GBK sources.
version: 3.1.0
author: longhun12346
license: MIT
tags: [encoding, windows, cpp, ansi, gbk, utf-16, nsis, hook]
---

# file-encoding

## How it works (v3 - inform-only, no conversion)

This skill installs **guard hooks** that protect non-UTF-8 files from being
corrupted by native Edit/Write/MultiEdit:

1. **PreToolUse** detects the file's encoding (only monitored extensions).
2. File is non-UTF-8 (GBK, Shift-JIS, Big5, windows-1251, UTF-16 BOM, ...):
   - `Read` → informational message: use `encoding_utils.py read` instead.
   - `Edit` / `Write` / `MultiEdit` → **BLOCKED** with instructions to use
     `encoding_utils.py replace` / `safe-write`.
3. UTF-8 / ASCII / safe single-byte files pass through untouched.

**The hook never converts, rewrites, backs up, or locks any file.** The only
thing on disk is a tiny state file (in the temp dir) used by PostToolUse to
detect whether a guarded file was later rewritten into another encoding.

## The workflow Claude should follow

When the hook reports that a file is non-UTF-8 (e.g. `gbk`):

```bash
# 1. Read (instead of native Read)
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py read "file.cpp" --enc gbk

# 2. Make a precise edit (instead of native Edit)
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py replace "file.cpp" \
    --old "旧文本" --new "新文本" --enc gbk

# 3. Or rewrite the whole file (instead of native Write)
#    (pipe full content via stdin; encoding auto-preserved from the file)
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py safe-write "file.cpp"
```

`replace` is the safe edit channel:

- reads with the file's **real encoding** and writes back with the same one
- **never modifies the file** if `old_string` is not found, if the occurrence
  count differs from `--expect`, or if `new_string` contains characters the
  target charset cannot represent
- use `--all` to replace every occurrence, `--expect N` to verify the count

## Manual commands (encoding_utils.py)

```
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py detect <file>
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py read <file> [--enc E] [--max-lines N]
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py write <file> --enc E
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py safe-write <file> [--enc E]
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py replace <file> --old S --new S [--enc E] [--all] [--expect N]
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py convert <file> --to E [--enc F]
```

## New file creation

New files created with native Write are UTF-8, which is fine unless the
project requires another encoding. To create a GBK file matching its siblings:

```bash
echo "content" | python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py safe-write "new_file.cpp" --enc gbk
```

## Crash recovery

Since the hooks never modify files, **there is nothing to recover**. If state
files accumulate (harmless), clean them:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/encoding_transparent.py recover
```

If the model ever does write a non-UTF-8 file with a native tool anyway, the
PostToolUse hook warns and gives restore commands (`encoding_utils.py convert`
back to the original encoding, or `git checkout -- <file>`).

## Installation (Claude Code plugin)

```bash
claude plugin marketplace add longhun12346/artifact-skills
claude plugin install artifact-skills file-encoding

# Python detection library (required for reliable encoding detection)
python ${CLAUDE_SKILL_DIR}/scripts/install_deps.py
python ${CLAUDE_SKILL_DIR}/scripts/install_deps.py --check
```

The plugin's `hooks/hooks.json` registers the guard hooks automatically
(matching `Edit|Write|MultiEdit|Read|NotebookEdit`).

`install_deps.py` installs **`charset-normalizer`** (required) and **`chardet`**
(optional legacy fallback) via `pip` if missing. If `pip` is unavailable,
detection falls back to heuristics (less reliable between Shift-JIS /
EUC-KR / GBK).

## When it activates

- Monitored extensions: `.cpp` `.h` `.hpp` `.c` `.cc` `.cxx` `.rc` `.bat` `.nsi` `.ini` `.xml`
- UTF-8 / ASCII files pass through with ~70ms subprocess startup

## Supported encodings

### Guarded (block Edit/Write, instruct to use tools)

| Category | Encodings | Typical file types | Detection reliability |
|----------|-----------|-------------------|---------------------|
| CJK multibyte | gbk, shift-jis, euc-kr, big5 | `.cpp` `.h` `.rc` `.bat` | High (distinctive byte patterns) |
| Cyrillic | windows-1251 | `.cpp` `.h` `.rc` | High (charset-normalizer reliable for Cyrillic) |
| Unicode BOM | utf-8-bom | `.nsi` | Exact (BOM prefix) |
| UTF-16 | utf-16-le-bom, utf-16-be-bom | `.ini` | Exact (BOM prefix) |

### Pass-through (no warning, native tools safe)

| Category | Encodings | Reason |
|----------|-----------|--------|
| UTF-8 / ASCII | utf-8, ascii | Claude native support |
| Western single-byte | windows-1252, windows-1250, iso-8859-1/2 | High bytes rare in source code |
| Other single-byte | windows-1253~1258 | Same; detection unreliable between these |
| Binary | binary | Not text |

## Limitations

1. **Model compliance** — the design relies on the model following the
   instructions; native Edit/Write/MultiEdit on non-UTF-8 files are blocked,
   which enforces compliance. The PostToolUse hook is a second line of defense.

2. **`replace` is exact-match** — `old_string` must match the file content
   including whitespace and newlines (`\r\n` vs `\n`). Read with
   `encoding_utils.py read` first and copy the exact text.

3. **Charset ceiling** — characters not representable in the target charset
   (e.g. emoji in GBK) cannot be written; `replace` fails safely and explains.

4. **Encoding detection without a detection library** — without
   `charset-normalizer`/`chardet`, heuristic fallback may misidentify
   Shift-JIS/EUC-KR as GBK on Chinese Windows. Run `install_deps.py` for
   reliable results.

5. **Only monitored extensions** — files outside
   `.cpp/.h/.hpp/.c/.cc/.cxx/.rc/.bat/.nsi/.ini/.xml` are not guarded.
   Add extensions to `MONITORED_EXTENSIONS` in `encoding_transparent.py`.

## Requirements

- Python 3.9+ (charset-normalizer 3.x)
- `charset-normalizer` for reliable encoding detection — installed
  automatically by `install_deps.py`; `chardet` optional as legacy fallback
