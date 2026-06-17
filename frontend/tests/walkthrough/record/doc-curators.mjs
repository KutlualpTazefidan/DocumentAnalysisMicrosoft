// Walkthrough recording: doc-curators
// Tour per-document curator assignment: each source document can have a set
// of curators who are allowed to work on its goldens. The /curators tab under
// a doc shows two panes — „All curators“ (left, click „+ assign“) and
// „Assigned to this doc“ (right, click „× unassign“). We create a throwaway
// curator via the API, assign it, unassign it in the UI, then revoke the
// curator at the end so re-runs stay pristine (mirrors extract-box-merge).

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8001";

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();

await page.goto(`${BASE}/`);
await page.evaluate(({ t }) => {
  sessionStorage.setItem("goldens.api_token", t);
  sessionStorage.setItem("goldens.role", "admin");
  sessionStorage.setItem("goldens.name", "probe");
  sessionStorage.setItem("goldens.tenant_name", "Fachbereich 3.3");
}, { t: TOKEN });

// Defensive: the UI unassign does NOT trigger window.confirm, but if any
// browser-level dialog ever appears, auto-accept so the recording never hangs.
page.on("dialog", (d) => d.accept().catch(() => {}));

// ── Setup: create a throwaway curator via the API ──────────────────────────
// Timestamped name so a prior run that died before teardown can't leave a
// duplicate (which would make the aria-label locator match two elements).
// Create BEFORE goto so the page's initial listCurators() already includes it.
const CURATOR_NAME = `probe-curator-${Date.now()}`;
let curatorId = null;
{
  const r = await fetch(`${API}/api/admin/curators`, {
    method: "POST",
    headers: { "X-Auth-Token": TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify({ name: CURATOR_NAME }),
  });
  if (r.ok) {
    const created = await r.json();
    curatorId = created.id;
    console.log("Created test curator:", CURATOR_NAME, "->", curatorId);
  } else {
    console.log("curator create failed:", r.status, await r.text());
  }
}

const assignSel = `[aria-label="assign ${CURATOR_NAME}"]`;
const unassignSel = `[aria-label="unassign ${CURATOR_NAME}"]`;

const rec = new Recorder("doc-curators", BASE);

await page.goto(`${BASE}/#/admin/doc/${SLUG}/curators`);
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(1500);

// Step 1: the two-pane curators page (unassigned starting state)
await rec.step(page, "Kuratoren-Tab: zwei Spalten („All curators“ / „Assigned to this doc“)", {
  actions: [`goto /admin/doc/${SLUG}/curators`],
  notes: [
    "Pro Dokument lässt sich festlegen, welche Kuratoren daran arbeiten dürfen — diese Seite (Route /admin/doc/:slug/curators) verwaltet genau diese Zuordnung.",
    "Oben läuft die DocStepTabs-Leiste (Dateien · Extrahieren · Synthese · Vergleich · Provenienz · Statistik) durch; für die Kuratoren-Route ist kein Tab aktiv — sie wird direkt per Route angesteuert.",
    "Links „All curators“ (alle bekannten Kuratoren), rechts „Assigned to this doc“ (die diesem Doc zugewiesenen). Navy-Überschrift „Curators for doc: <slug>“ auf hellem BAM-Surface.",
    `Test-Kurator „${CURATOR_NAME}“ wurde per API angelegt und erscheint links mit „+ assign“ (BAM-Cyan-Link).`,
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'h2:has-text("All curators")', text: "Linke Spalte: alle Kuratoren" },
    { kind: "highlight", selector: 'h2:has-text("Assigned to this doc")', text: "Rechte Spalte: diesem Doc zugewiesen" },
    { kind: "highlight", selector: assignSel, text: "„+ assign“ für den Test-Kurator (Cyan)" },
  ] }],
});

// Step 2: click „+ assign“ → curator moves into the right pane
await page.locator(assignSel).first().click();
// The mutation + invalidateQueries re-render is async — wait for the
// „× unassign“ row to appear instead of a fixed timeout.
await page.locator(unassignSel).first().waitFor({ state: "visible", timeout: 5000 }).catch(() => {});
await page.waitForTimeout(400);

await rec.step(page, "„+ assign“ geklickt → Kurator steht jetzt rechts unter „Assigned“", {
  actions: [`click [aria-label="assign ${CURATOR_NAME}"]`],
  notes: [
    "Der Klick auf „+ assign“ schickt POST /api/admin/docs/<slug>/curators mit { curator_id } — der Server verknüpft Kurator und Dokument.",
    "Nach Erfolg invalidiert React Query die „doc-curators“-Query und zeigt eine Toast-Bestätigung („Assigned …“).",
    "Der Kurator wandert in die rechte Spalte; links wird sein „+ assign“ ausgeblendet (assignedIds-Set blendet bereits zugewiesene aus — keine Doppel-Zuweisung möglich).",
    "Rechts erscheint stattdessen „× unassign“ in BAM-Rot zum Wieder-Entfernen.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: unassignSel, text: "Jetzt zugewiesen → „× unassign“ (rot)" },
  ] }],
});

// Step 3: click „× unassign“ → curator leaves the right pane, „+ assign“ returns left
await page.locator(unassignSel).first().click();
await page.locator(assignSel).first().waitFor({ state: "visible", timeout: 5000 }).catch(() => {});
await page.waitForTimeout(400);

await rec.step(page, "„× unassign“ geklickt → Zuordnung gelöst, Ausgangszustand", {
  actions: [`click [aria-label="unassign ${CURATOR_NAME}"]`],
  notes: [
    "„× unassign“ schickt DELETE /api/admin/docs/<slug>/curators/<curator_id> — direkt, ohne Bestätigungsdialog.",
    "Die rechte Spalte fällt auf „No curators assigned.“ zurück; links taucht „+ assign“ für den Kurator wieder auf — Zustand wie vor der Zuweisung.",
    "Zuweisen und Entfernen sind reine Verknüpfungs-Operationen: der Kurator-Datensatz selbst bleibt unter „All curators“ erhalten.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: assignSel, text: "Wieder „+ assign“ — Zuordnung gelöst" },
    { kind: "note", text: "Rechte Spalte: „No curators assigned.“ (Ausgangszustand)" },
  ] }],
});

const outDir = await rec.finish();
await browser.close();

// ── Teardown: revoke the throwaway curator so re-runs stay pristine ─────────
// At this point the curator is already unassigned (last step), so DELETE on
// the curator record removes it cleanly.
if (curatorId) {
  const r = await fetch(`${API}/api/admin/curators/${curatorId}`, {
    method: "DELETE",
    headers: { "X-Auth-Token": TOKEN },
  });
  if (r.ok || r.status === 204) {
    console.log("Revoked test curator:", curatorId);
  } else {
    console.log("curator revoke failed:", r.status, await r.text());
  }
}

console.log("Wrote walkthrough to", outDir);
