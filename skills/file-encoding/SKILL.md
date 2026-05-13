---
name: file-encoding
description: Handles multi-encoding files (ANSI/UTF-8/UTF-16 LE BOM) in Windows C++ projects. Detect encoding before editing .cpp/.h/.py/.nsi/.ini/.xml/.bat files to avoid corruption.
version: 1.0.0
author: longhun12346
license: MIT
tags: [encoding, windows, cpp, ansi, gbk, utf-16, nsis]
---

# file-encoding

## When to trigger

**Windows + C++ project** -> detect encoding before editing any source file. Skip for non-Windows or frontend projects (everything is UTF-8).

C++ project detection: `.vcxproj` / `CMakeLists.txt` / `stdafx.h` / `#include <windows.h>` etc.

## Encoding rules

| File type | Encoding | Notes |
|-----------|----------|-------|
| `.cpp` `.h` `.rc` | **System ANSI** | GBK / Shift-JIS / EUC-KR / Big5 depending on system locale |
| `.bat` (build scripts) | **System ANSI** | CMD reads as ANSI; UTF-8 without BOM garbles non-ASCII |
| `.nsi` | UTF-8 BOM or UTF-16 LE BOM | Never assume, always `detect` |
| `.ini` (GetPrivateProfileStringW) | **UTF-16 LE BOM** | Non-ASCII garbled without BOM |
| `.py` (build scripts) | UTF-8 BOM | |
| `.xml` | UTF-8 | |

## Commands

Uses `scripts/encoding_utils.py`. Supports Python 2.6+/3.x.

```
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py detect <file>
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py read <file> [--enc E]
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py write <file> --enc E
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py replace <file> --old S --new T [--enc E]
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py --version
```

Encoding names: `gbk` `shift-jis` `euc-kr` `big5` `utf-8` `utf-8-bom` `utf-16-le-bom` `utf-16` `windows-1252` `iso-8859-1` etc.

## Edit workflow

### Existing files

```
detect -> utf-8 (no BOM) -> Edit/Write tools
detect -> other          -> encoding_utils.py replace   (simple)
                         -> read -> edit tmp.txt -> write (complex)
```

```bash
# Simple replace
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py replace "file.cpp" --old "old" --new "new"

# Complex edit
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py read "file.cpp" > tmp.txt
# ... edit tmp.txt ...
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py write "file.cpp" --enc gbk < tmp.txt
```

### New files

**Do not use Write tool for non-UTF-8 files.** Detect encoding of existing files of the same type first, then create:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py detect "existing.cpp"
python ${CLAUDE_SKILL_DIR}/scripts/encoding_utils.py write "new.cpp" --enc gbk < content.txt
```

## Pitfalls

- **Edit/Write on non-UTF-8** -> garbled text. Use `replace` or read->edit->write instead.
- **`.nsi` encoding not fixed** -> UTF-8 BOM or UTF-16 LE BOM. Always `detect` first.
- **INI without BOM** -> `GetPrivateProfileStringW` reads as ANSI, corrupting non-ASCII. Must be UTF-16 LE BOM.
- **Python `\6` octal escape** -> in non-raw strings, `Software\kingsoft\Office\6.0` has hidden control chars. Use raw string `r'...'` or `\\\\`.
- **Py2 `open()` no `encoding=`** -> use `io.open()`. encoding_utils.py handles this.