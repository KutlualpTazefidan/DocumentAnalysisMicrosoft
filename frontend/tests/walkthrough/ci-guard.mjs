#!/usr/bin/env node
// CI guard for the walkthrough record scripts.
//
// The recordings themselves can't run in CI (they drive a live GPU/ML
// backend against a processed document), but the two ways a script silently
// rots ARE cheap to catch:
//   1. syntax / import errors        — `node --check`
//   2. selectors that no longer exist — grep each literal data-testid /
//      aria-label / :has-text() / getByLabel() token against frontend/src
//
// Templated selectors (anything with `${`) are skipped — they're built from
// backend data at runtime and can't be checked statically. Playwright's
// :has-text is substring-matched, so a script's partial text still resolves
// as long as it's a substring of the rendered label, which `includes` mirrors.

import { readdirSync, readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const RECORD = join(HERE, "record");
const SRC = join(HERE, "..", "..", "src");

function readAllSrc(dir) {
  let out = "";
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) out += readAllSrc(p);
    else if (/\.(ts|tsx)$/.test(e.name)) out += readFileSync(p, "utf8");
  }
  return out;
}
// Whitespace-collapsed view of all src so a selector text that wraps across
// JSX lines (newline + indentation, which the browser collapses to a single
// space) still matches.
const srcNorm = readAllSrc(SRC).replace(/\s+/g, " ");

const PATTERNS = [
  /data-testid="([^"${}]+)"/g,
  /aria-label="([^"${}]+)"/g,
  /:has-text\("([^"${}]+)"\)/g,
  /getByLabel\(\/([^/${}]+)\//g,
];

const scripts = readdirSync(RECORD).filter((f) => f.endsWith(".mjs")).sort();
let syntaxFails = 0;
const missing = [];

for (const f of scripts) {
  const path = join(RECORD, f);
  const chk = spawnSync("node", ["--check", path], { encoding: "utf8" });
  if (chk.status !== 0) {
    syntaxFails++;
    console.error(`✗ syntax: ${f}\n  ${(chk.stderr || "").trim().split("\n").slice(-2).join("\n  ")}`);
    continue;
  }
  const txt = readFileSync(path, "utf8");
  const seen = new Set();
  for (const re of PATTERNS) {
    for (const m of txt.matchAll(re)) {
      // Unescape regex escapes (e.g. getByLabel(/Warum\?/) -> "Warum?") and
      // collapse whitespace to mirror the normalised src.
      const lit = m[1].replace(/\\(.)/g, "$1").replace(/\s+/g, " ").trim();
      if (!lit || seen.has(lit)) continue;
      seen.add(lit);
      if (!srcNorm.includes(lit)) missing.push({ f, lit });
    }
  }
}

console.log(`Checked ${scripts.length} walkthrough record scripts.`);
if (syntaxFails) console.error(`\n${syntaxFails} script(s) failed node --check.`);
if (missing.length) {
  console.error(`\n${missing.length} literal selector(s) not found in frontend/src:`);
  for (const { f, lit } of missing) console.error(`  [${f}] "${lit}"`);
}
if (syntaxFails || missing.length) {
  console.error("\nWalkthrough guard FAILED.");
  process.exit(1);
}
console.log("Walkthrough guard passed.");
