/**
 * Template for a new walkthrough.
 *
 * 1. Copy this file:
 *      cp _template.walkthrough.ts my-flow.walkthrough.ts
 * 2. Edit the steps below.
 * 3. Run it:
 *      npm run walkthrough my-flow
 *
 * Naming convention: ``<name>.walkthrough.ts`` so the runner finds
 * it by ``npm run walkthrough <name>``.
 */

import type { Walkthrough } from "../walkthrough";

export default async function (w: Walkthrough): Promise<void> {
  await w.step("First step — open something", async (s) => {
    await s.goto("/some-path");
    s.note("Explain what's happening at this step.");
    s.highlight("button.primary", "The button we care about");
    await s.screenshot();
  });

  await w.step("Second step — interact", async (s) => {
    await s.fill('input[name="example"]', "hello");
    await s.click("button.primary");
    await s.waitForUrl(/\/success/);
    s.note("Server should now have a new record.");
    await s.screenshot({ note: "Post-submit state" });
  });

  // Available helpers on the Step builder ``s``:
  //   await s.goto("/path")           navigate (path or absolute URL)
  //   await s.click("selector")       click an element
  //   await s.fill("selector", val)   type into an input
  //   await s.waitForUrl(matcher)     wait for URL to match a substring or regex
  //   await s.expectVisible(selector) assert + wait for visibility
  //   await s.screenshot({ note })    take a full-page screenshot
  //
  //   s.note("text")                  add a side-panel note
  //   s.highlight("selector", "label") cyan box over an element on the next screenshot
  //   s.arrow("from", "to", "label")  pink arrow on the next screenshot
  //   s.error("text")                 red overlay on the next screenshot
  //
  // Console logs, network 4xx/5xx, and JS errors are recorded
  // automatically per step — no manual setup needed.
}
