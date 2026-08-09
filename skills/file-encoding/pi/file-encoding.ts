/**
 * file-encoding.ts - Pi extension: encoding guard for non-UTF-8 files.
 *
 * Reuses the Python implementation (encoding_utils.py) for detection and
 * transcoding, so behavior stays identical to the Claude Code version.
 *
 * Behavior:
 *  - tool_call (edit/write): detect encoding; non-UTF-8 (GBK, Shift-JIS,
 *    Big5, windows-1251, UTF-16 BOM, ...) -> BLOCK with instructions to use
 *    `encoding_utils.py replace` / `safe-write`.
 *  - tool_result (read): if the file is non-UTF-8, rewrite the result with
 *    properly decoded content (native read shows mojibake and, worse, native
 *    edit would corrupt the file irreversibly - bytes replaced by U+FFFD).
 *
 * Detection results are cached per file (mtime+size), so repeat operations
 * skip the ~200ms python subprocess + charset-normalizer import.
 *
 * Install: see README.md in this directory.
 */

import { isToolCallEventType } from "@earendil-works/pi-coding-agent";
import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";

// ---------------------------------------------------------------------------
// Configuration - MUST stay in sync with encoding_transparent.py
// ---------------------------------------------------------------------------

// Files whose encoding matters (same as MONITORED_EXTENSIONS in Python).
const MONITORED_EXTENSIONS = new Set([
  ".cpp", ".h", ".hpp", ".c", ".cc", ".cxx",
  ".rc", ".bat", ".nsi", ".ini", ".xml",
]);

// Encodings native tools handle safely (same as SAFE_ENCODINGS in Python).
const SAFE_ENCODINGS = new Set([
  "utf-8", "ascii", "binary",
  "windows-1250", "windows-1252", "windows-1253",
  "windows-1254", "windows-1255", "windows-1256", "windows-1257",
  "windows-1258", "iso-8859-1", "iso-8859-2",
]);

// ---------------------------------------------------------------------------
// Python backend (reuse encoding_utils.py)
// ---------------------------------------------------------------------------

const SCRIPT_DIR = path.join(__dirname, "..", "scripts");
const EU_SCRIPT = path.join(SCRIPT_DIR, "encoding_utils.py");
const PYTHON = process.env.ENCODING_PYTHON ?? "python";

interface CacheEntry {
  enc: string;
  mtimeMs: number;
  size: number;
}

// Per-process detection cache (pi extensions are long-running).
const detectCache = new Map<string, CacheEntry>();

/**
 * Detect a file's encoding by shelling out to encoding_utils.py.
 * Returns friendly name (e.g. "gbk", "shift-jis") or null on any failure
 * (missing file, no python, detection error) - null means "leave alone".
 */
function detectEncoding(filePath: string): string | null {
  try {
    const st = fs.statSync(filePath);
    if (!st.isFile()) return null;
    const hit = detectCache.get(filePath);
    if (hit && hit.mtimeMs === st.mtimeMs && hit.size === st.size) {
      return hit.enc;
    }
    const out = execFileSync(PYTHON, [EU_SCRIPT, "detect", filePath], {
      encoding: "utf-8",
      timeout: 10000,
      windowsHide: true,
    });
    const enc = out.trim();
    detectCache.set(filePath, { enc, mtimeMs: st.mtimeMs, size: st.size });
    return enc;
  } catch {
    return null;
  }
}

/** Read a file as UTF-8 text using its real encoding. */
function readWithEncoding(filePath: string, enc: string): string {
  return execFileSync(PYTHON, [EU_SCRIPT, "read", filePath, "--enc", enc], {
    encoding: "utf-8",
    timeout: 30000,
    windowsHide: true,
    maxBuffer: 64 * 1024 * 1024,
  });
}

function isMonitored(filePath: string): boolean {
  return MONITORED_EXTENSIONS.has(path.extname(filePath).toLowerCase());
}

function isUnsafe(filePath: string): boolean {
  const enc = detectEncoding(filePath);
  return !!enc && !SAFE_ENCODINGS.has(enc);
}

// ---------------------------------------------------------------------------
// Extension
// ---------------------------------------------------------------------------

export default function (pi: ExtensionAPI): void {
  // Block unsafe native edits on non-UTF-8 files.
  pi.on("tool_call", (event) => {
    if (!isToolCallEventType("edit", event) && !isToolCallEventType("write", event)) {
      return;
    }
    const filePath = event.input.path;
    if (!filePath || !isMonitored(filePath)) return;
    const enc = detectEncoding(filePath);
    if (!enc || SAFE_ENCODINGS.has(enc)) return;
    return {
      block: true,
      reason:
        `[encoding] ${filePath} is ${enc} (not UTF-8). Native edit/write would corrupt it.\n` +
        `  read:  python "${EU_SCRIPT}" read "${filePath}" --enc ${enc}\n` +
        `  edit:  python "${EU_SCRIPT}" replace "${filePath}" --old "<old>" --new "<new>" --enc ${enc}`,
    };
  });

  // Rewrite read results for non-UTF-8 files so the model sees real content.
  pi.on("tool_result", (event) => {
    if (!isToolCallEventType("read", event)) return;
    const filePath = event.input.path;
    if (!filePath || !isMonitored(filePath) || event.isError) return;
    const enc = detectEncoding(filePath);
    if (!enc || SAFE_ENCODINGS.has(enc)) return;
    try {
      const text = readWithEncoding(filePath, enc);
      return { content: [{ type: "text", text }] };
    } catch {
      return; // leave the original (mojibake) result - better than nothing
    }
  });
}
