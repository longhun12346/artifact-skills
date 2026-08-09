#!/usr/bin/env node
// prepublish-check.mjs - validate the package before `npm publish`.
//
// Checks that every resource declared in the `pi` manifest exists and that
// the encoding backend (Python scripts) is present, so a publish never ships
// a broken package.

import { existsSync } from "node:fs";
import { readFileSync } from "node:fs";
import { resolve, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf-8"));
const errors = [];

const manifest = pkg.pi || {};
for (const key of ["extensions", "skills", "prompts", "themes"]) {
  const paths = manifest[key] || [];
  for (const rel of paths) {
    const abs = resolve(root, rel);
    if (!existsSync(abs)) {
      errors.push(`pi.${key}: missing ${rel}`);
    }
  }
}

// Encoding backend the Pi extension depends on at runtime.
for (const rel of [
  "skills/file-encoding/scripts/encoding_utils.py",
  "skills/file-encoding/scripts/encoding_transparent.py",
  "skills/file-encoding/scripts/install_deps.py",
  "skills/file-encoding/SKILL.md",
  "skills/file-encoding/requirements.txt",
]) {
  if (!existsSync(join(root, rel))) {
    errors.push(`missing ${rel}`);
  }
}

// `files` must cover everything the manifest references.
if (!(pkg.files || []).some((f) => f === "skills/file-encoding")) {
  errors.push("files[] must include skills/file-encoding");
}

if (errors.length) {
  console.error("prepublish check FAILED:");
  for (const e of errors) console.error("  - " + e);
  process.exit(1);
}
console.log("prepublish check OK: package structure valid");
