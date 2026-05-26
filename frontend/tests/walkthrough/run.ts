/**
 * Walkthrough runner.
 *
 *   npm run walkthrough <flow>            # headed (default; you see the browser)
 *   npm run walkthrough <flow> -- --headless
 *
 * The runner imports ``flows/<flow>.walkthrough.ts``, calls its
 * ``default`` export with a fresh Playwright Page, then composes the
 * report.html + report.png from the recorded data.
 */

import fs from "node:fs";
import path from "node:path";
import url from "node:url";
import { chromium } from "@playwright/test";
import { composeReport } from "./compose-report";
import { Walkthrough } from "./walkthrough";

// package.json declares "type":"module" so __dirname / __filename
// don't exist out of the box; reconstruct from import.meta.url.
const __filename = url.fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

interface Args {
  flow: string;
  headless: boolean;
  baseUrl: string;
}

function parseArgs(argv: string[]): Args {
  // Skip node + script path.
  const a = argv.slice(2);
  let flow = "";
  let headless = false;
  let baseUrl = "http://127.0.0.1:5173";
  for (let i = 0; i < a.length; i++) {
    const v = a[i]!;
    if (v === "--headless") headless = true;
    else if (v === "--headed") headless = false;
    else if (v === "--base-url") {
      baseUrl = a[++i] ?? baseUrl;
    } else if (!v.startsWith("-")) {
      flow = v;
    }
  }
  if (!flow) {
    console.error(
      "Usage: tsx run.ts <flow> [--headless] [--base-url http://…]",
    );
    process.exit(2);
  }
  return { flow, headless, baseUrl };
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv);

  // Resolve the flow module path. Allow either bare name or
  // "<flow>.walkthrough" or even an absolute file path.
  const flowsDir = path.join(__dirname, "flows");
  const candidates = [
    path.join(flowsDir, `${args.flow}.walkthrough.ts`),
    path.join(flowsDir, `${args.flow}.ts`),
    path.resolve(args.flow),
  ];
  const flowPath = candidates.find((p) => fs.existsSync(p));
  if (!flowPath) {
    console.error(`Flow not found. Tried:\n  ${candidates.join("\n  ")}`);
    process.exit(2);
  }
  // Dynamic import via the file URL so tsx resolves the loader hook.
  const flowMod = await import(url.pathToFileURL(flowPath).href);
  const flowFn = flowMod.default ?? flowMod.walkthrough;
  if (typeof flowFn !== "function") {
    console.error(
      `Flow ${flowPath} must default-export an async (w: Walkthrough) => Promise<void>.`,
    );
    process.exit(2);
  }

  console.log(`[walkthrough] starting "${args.flow}" — headless=${args.headless}`);
  console.log(`[walkthrough] baseUrl: ${args.baseUrl}`);

  const browser = await chromium.launch({
    headless: args.headless,
    slowMo: args.headless ? 0 : 200, // slow enough to read along when headed
  });
  try {
    const ctx = await browser.newContext({
      viewport: { width: 1400, height: 900 },
    });
    const page = await ctx.newPage();
    const w = await Walkthrough.start({
      name: args.flow,
      page,
      baseUrl: args.baseUrl,
      outputRoot: path.join(__dirname, "output"),
    });

    let runErr: unknown = null;
    try {
      await flowFn(w);
    } catch (err) {
      runErr = err;
      console.error("[walkthrough] step failed — composing report anyway");
    }
    const dir = await w.save();
    const { htmlPath, pngPath } = await composeReport(dir);

    console.log(`[walkthrough] data:   ${path.join(dir, "data.json")}`);
    console.log(`[walkthrough] HTML:   ${htmlPath}`);
    console.log(`[walkthrough] PNG:    ${pngPath}`);

    if (runErr) {
      console.error("[walkthrough] flow failed:", runErr);
      process.exitCode = 1;
    }
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
