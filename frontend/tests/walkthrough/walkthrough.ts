/**
 * Walkthrough recorder — a Playwright wrapper that captures a UI
 * workflow as a Figma-style storyboard: screenshots + annotations +
 * console/network/JS-error overlays.
 *
 * Usage:
 *
 *   const w = await Walkthrough.start({ name: "login", page });
 *   await w.step("Open login", async (s) => {
 *     await s.goto("/login");
 *     await s.screenshot();
 *     await s.expectVisible("text=Local-PDF");
 *   });
 *   await w.save();
 *
 * Output: ``output/<name>_<timestamp>/{screenshots/,data.json}``.
 * Render the report via ``compose-report.ts``.
 */

import fs from "node:fs";
import path from "node:path";
import type { ConsoleMessage, Page, Response } from "@playwright/test";

// ---- Data shapes (also persisted as data.json) ----

export interface ConsoleEntry {
  type: string; // 'log' | 'warn' | 'error' | …
  text: string;
  location?: { url: string; lineNumber?: number };
  stepIndex: number; // attaches to the step that was active when it fired
}

export interface NetworkErrorEntry {
  url: string;
  method: string;
  status: number;
  statusText: string;
  stepIndex: number;
}

export interface PageErrorEntry {
  name: string;
  message: string;
  stack?: string;
  stepIndex: number;
}

export interface Annotation {
  kind: "note" | "highlight" | "error" | "arrow";
  text?: string;
  selector?: string; // for highlight
  fromSelector?: string; // for arrow
  toSelector?: string; // for arrow
  // Resolved bounding box (filled in at screenshot time):
  box?: { x: number; y: number; width: number; height: number };
  boxFrom?: { x: number; y: number; width: number; height: number };
  boxTo?: { x: number; y: number; width: number; height: number };
}

export interface ScreenshotEntry {
  filename: string; // relative to output dir
  width: number;
  height: number;
  annotations: Annotation[];
  note?: string;
}

export interface StepData {
  index: number;
  title: string;
  startedAtMs: number;
  endedAtMs: number;
  actions: string[]; // human-readable trace: "goto /login", "fill foo", …
  screenshots: ScreenshotEntry[];
  notes: string[];
  status: "ok" | "failed";
  errorMessage?: string;
}

export interface WalkthroughData {
  name: string;
  startedAt: string; // ISO
  endedAt: string;
  baseUrl: string;
  steps: StepData[];
  console: ConsoleEntry[];
  networkErrors: NetworkErrorEntry[];
  pageErrors: PageErrorEntry[];
}

// ---- Builders ----

interface StartOptions {
  name: string;
  page: Page;
  outputRoot?: string; // defaults to frontend/tests/walkthrough/output
  baseUrl?: string;
}

export class Walkthrough {
  private steps: StepData[] = [];
  private consoleEntries: ConsoleEntry[] = [];
  private networkErrors: NetworkErrorEntry[] = [];
  private pageErrors: PageErrorEntry[] = [];
  private startedAt = new Date();
  private currentStepIndex = -1;
  private screenshotsDir: string;

  private constructor(
    public name: string,
    public page: Page,
    public outputDir: string,
    public baseUrl: string,
  ) {
    this.screenshotsDir = path.join(outputDir, "screenshots");
    fs.mkdirSync(this.screenshotsDir, { recursive: true });

    // Subscribe to events that fire OUTSIDE the explicit step blocks
    // too -- attach to whatever step happens to be active (or -1 for
    // 'before any step').
    page.on("console", (msg: ConsoleMessage) => {
      this.consoleEntries.push({
        type: msg.type(),
        text: msg.text(),
        location: msg.location(),
        stepIndex: this.currentStepIndex,
      });
    });
    page.on("pageerror", (err) => {
      this.pageErrors.push({
        name: err.name,
        message: err.message,
        stack: err.stack,
        stepIndex: this.currentStepIndex,
      });
    });
    page.on("response", (resp: Response) => {
      const status = resp.status();
      if (status >= 400) {
        this.networkErrors.push({
          url: resp.url(),
          method: resp.request().method(),
          status,
          statusText: resp.statusText(),
          stepIndex: this.currentStepIndex,
        });
      }
    });
  }

  static async start(opts: StartOptions): Promise<Walkthrough> {
    const root =
      opts.outputRoot ?? path.join(process.cwd(), "tests", "walkthrough", "output");
    const ts = new Date()
      .toISOString()
      .replace(/[:.]/g, "-")
      .replace(/T/, "_")
      .replace(/Z$/, "");
    const dir = path.join(root, `${opts.name}_${ts}`);
    fs.mkdirSync(dir, { recursive: true });
    return new Walkthrough(
      opts.name,
      opts.page,
      dir,
      opts.baseUrl ?? "http://127.0.0.1:5173",
    );
  }

  async step(title: string, fn: (s: Step) => Promise<void>): Promise<void> {
    this.currentStepIndex = this.steps.length;
    const step: StepData = {
      index: this.currentStepIndex,
      title,
      startedAtMs: Date.now(),
      endedAtMs: 0,
      actions: [],
      screenshots: [],
      notes: [],
      status: "ok",
    };
    const builder = new Step(this, step);
    try {
      await fn(builder);
    } catch (err) {
      step.status = "failed";
      step.errorMessage = err instanceof Error ? err.message : String(err);
      // Capture a failure screenshot so the report shows WHY the step
      // broke, not just the error text.
      try {
        await builder.screenshot({ note: `FAILURE: ${step.errorMessage}` });
      } catch {
        /* best-effort */
      }
      // Re-throw so the runner can decide whether to abort or continue.
      step.endedAtMs = Date.now();
      this.steps.push(step);
      throw err;
    }
    step.endedAtMs = Date.now();
    this.steps.push(step);
  }

  /** Persist data.json. Screenshots have already been written during steps. */
  async save(): Promise<string> {
    const data: WalkthroughData = {
      name: this.name,
      startedAt: this.startedAt.toISOString(),
      endedAt: new Date().toISOString(),
      baseUrl: this.baseUrl,
      steps: this.steps,
      console: this.consoleEntries,
      networkErrors: this.networkErrors,
      pageErrors: this.pageErrors,
    };
    const out = path.join(this.outputDir, "data.json");
    fs.writeFileSync(out, JSON.stringify(data, null, 2));
    return this.outputDir;
  }

  // Used internally by Step.screenshot.
  nextScreenshotFilename(): string {
    const stepIdx = String(this.currentStepIndex + 1).padStart(2, "0");
    const inStepIdx = this.steps[this.currentStepIndex]?.screenshots.length ?? 0;
    const subIdx = String(inStepIdx + 1).padStart(2, "0");
    return path.join("screenshots", `${stepIdx}_${subIdx}.png`);
  }

  get screenshotsAbsolute(): string {
    return this.screenshotsDir;
  }
}

export class Step {
  constructor(
    private readonly w: Walkthrough,
    private readonly data: StepData,
  ) {}

  private get page(): Page {
    return this.w.page;
  }

  /** Navigate to a path (absolute URL or path relative to baseUrl). */
  async goto(target: string): Promise<void> {
    const url = target.startsWith("http") ? target : `${this.w.baseUrl}${target}`;
    this.data.actions.push(`goto ${target}`);
    await this.page.goto(url);
  }

  /** Click an element by Playwright selector. */
  async click(selector: string): Promise<void> {
    this.data.actions.push(`click ${selector}`);
    await this.page.click(selector);
  }

  /** Type into an input by selector. */
  async fill(selector: string, value: string): Promise<void> {
    this.data.actions.push(`fill ${selector} = ${value}`);
    await this.page.fill(selector, value);
  }

  /** Hard wait until the URL matches (substring or regex). */
  async waitForUrl(target: string | RegExp, timeoutMs = 10_000): Promise<void> {
    this.data.actions.push(`waitForUrl ${target}`);
    await this.page.waitForURL(target, { timeout: timeoutMs });
  }

  /** Assert a selector / text is visible; throws if not. */
  async expectVisible(selector: string, timeoutMs = 5_000): Promise<void> {
    this.data.actions.push(`expectVisible ${selector}`);
    await this.page.waitForSelector(selector, {
      state: "visible",
      timeout: timeoutMs,
    });
  }

  /** Take a full-page screenshot and record it as part of this step.
   *  Annotations queued via highlight/note/arrow/error since the last
   *  screenshot are attached to this one and then cleared. */
  async screenshot(opts: { note?: string } = {}): Promise<void> {
    const rel = this.w.nextScreenshotFilename();
    const abs = path.join(this.w.outputDir, rel);
    fs.mkdirSync(path.dirname(abs), { recursive: true });
    await this.page.screenshot({ path: abs, fullPage: true });
    const vp = this.page.viewportSize() ?? { width: 1280, height: 720 };
    // Resolve any pending annotations (selectors -> bounding boxes).
    const resolved: Annotation[] = [];
    for (const a of this.pending) {
      const out: Annotation = { ...a };
      if (a.selector) {
        out.box = await this.boundingBox(a.selector);
      }
      if (a.fromSelector) {
        out.boxFrom = await this.boundingBox(a.fromSelector);
      }
      if (a.toSelector) {
        out.boxTo = await this.boundingBox(a.toSelector);
      }
      resolved.push(out);
    }
    this.pending = [];
    this.data.screenshots.push({
      filename: rel,
      width: vp.width,
      height: vp.height,
      annotations: resolved,
      note: opts.note,
    });
  }

  private async boundingBox(
    selector: string,
  ): Promise<Annotation["box"] | undefined> {
    try {
      const el = this.page.locator(selector).first();
      const b = await el.boundingBox();
      if (!b) return undefined;
      return { x: b.x, y: b.y, width: b.width, height: b.height };
    } catch {
      return undefined;
    }
  }

  // ---- Annotation queue (consumed by the next screenshot) ----

  private pending: Annotation[] = [];

  note(text: string): void {
    this.pending.push({ kind: "note", text });
    this.data.notes.push(text);
  }

  highlight(selector: string, label?: string): void {
    this.pending.push({ kind: "highlight", selector, text: label });
  }

  error(message: string): void {
    this.pending.push({ kind: "error", text: message });
  }

  arrow(fromSelector: string, toSelector: string, label?: string): void {
    this.pending.push({
      kind: "arrow",
      fromSelector,
      toSelector,
      text: label,
    });
  }
}
