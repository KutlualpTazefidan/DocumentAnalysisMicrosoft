// Walkthrough recording: provenienz-plan-override
// Tour the expert-override capture path on a plan_proposal (Phase-3
// shape: expert_step_override + expert_method_request kinds):
//   ① Sitzung + /next-step liefert einen plan_proposal-Vorschlag
//   ② Verwerfen-Klick morpht den Button in eine Inline-Form
//      (Stattdessen-Combobox + Warum-Textarea + Submit + Doch löschen)
//   ③ Bekannten Step wählen → /decide spawnt expert_step_override-Tile
//      (rose, Purpose 1 — teach the agent) mit dotted "stattdessen"-Edge
//   ④ Unbekannten Step (free-text) → /decide spawnt EIN
//      expert_method_request-Tile (amber, Purpose 2 — capability gap);
//      kein separater capability_request-Node mehr (Daten gefaltet)
//   ⑤ Leere Reason → Submit ist disabled (kein Network-Call)
//   ⑥ Esc kollabiert die Form zurück auf den Verwerfen-Button
//
// Setup über die API, UI nur für visuelle Storyboard-Captures. Cleanup
// löscht die Test-Sitzung am Ende; vLLM muss laufen, damit /next-step
// einen echten plan_proposal liefert.

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8001";

async function findRootChunk() {
  const seg = await (await fetch(`${API}/api/admin/docs/${SLUG}/segments`, { headers: { "X-Auth-Token": TOKEN } })).json();
  return seg.boxes.find(b => b.kind === "paragraph" && b.page === 2)?.box_id;
}
async function createSession(rootChunkId) {
  const r = await fetch(`${API}/api/admin/provenienz/sessions`, {
    method: "POST",
    headers: { "X-Auth-Token": TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify({ slug: SLUG, root_chunk_id: rootChunkId }),
  });
  if (!r.ok) throw new Error(`create session: ${r.status} ${await r.text()}`);
  return r.json();
}
async function getSession(sid) {
  const r = await fetch(`${API}/api/admin/provenienz/sessions/${sid}`, { headers: { "X-Auth-Token": TOKEN } });
  return r.ok ? r.json() : null;
}
async function triggerNextStep(sid, anchorNodeId) {
  const r = await fetch(`${API}/api/admin/provenienz/sessions/${sid}/next-step`, {
    method: "POST",
    headers: { "X-Auth-Token": TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify({ anchor_node_id: anchorNodeId }),
  });
  if (!r.ok) throw new Error(`next-step: ${r.status} ${await r.text()}`);
  return r.json();
}
async function fetchCapabilityRequests() {
  const r = await fetch(`${API}/api/admin/provenienz/capability-requests`, { headers: { "X-Auth-Token": TOKEN } });
  return r.ok ? (await r.json()).requests : [];
}
async function deleteSession(sid) {
  await fetch(`${API}/api/admin/provenienz/sessions/${sid}`, {
    method: "DELETE", headers: { "X-Auth-Token": TOKEN },
  }).catch(() => {});
}

// Activates the test session by clicking its entry in the left rail.
// The Provenienz view opens with no session selected; the canvas only
// renders once one is picked, so this must run before any tile click.
async function selectSessionInRail(page, sessionId) {
  const shortId = sessionId.slice(0, 10);
  const entry = page.locator(`aside`).getByText(shortId, { exact: false }).first();
  await entry.click();
}

// Selects the plan_proposal tile on the ReactFlow canvas via its
// rendered data-id attribute (ReactFlow attaches one per node). Falls
// back to clicking any visible plan_proposal tile if the targeted
// node_id changed after a /next-step rerun.
async function clickPlanTile(page, planNodeId) {
  const byId = page.locator(`.react-flow__node[data-id="view:${planNodeId}"]`);
  await byId.first().waitFor({ state: "visible", timeout: 8000 }).catch(() => {});
  if ((await byId.count()) > 0) {
    await byId.first().click();
    return;
  }
  // Fallback: any plan_proposal-typed node (data-type set by ReactFlow).
  const fallback = page.locator(`.react-flow__node[data-type="plan_proposal"]`);
  if ((await fallback.count()) > 0) {
    await fallback.first().click();
  }
}

// ── Setup ────────────────────────────────────────────────────────────────
const rootChunk = await findRootChunk();
if (!rootChunk) throw new Error("no paragraph box on page 2");
const session = await createSession(rootChunk);
console.log("Created session", session.session_id, "anchored at", rootChunk);
const chunkNodeId = (await getSession(session.session_id)).nodes[0].node_id;
const proposal = await triggerNextStep(session.session_id, chunkNodeId);
const proposalId = proposal.node_id;
console.log("AI proposed:", proposal.payload?.name, "(node_id:", proposalId, ")");

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 } });
const page = await ctx.newPage();
// Surface the /decide network calls in the recording log so we can
// cross-check them in the final report.
const decideCalls = [];
page.on("request", (req) => {
  if (/\/api\/admin\/provenienz\/sessions\/[^/]+\/decide$/.test(req.url())) {
    decideCalls.push({ method: req.method(), body: req.postDataJSON() ?? null });
  }
});

await page.goto(`${BASE}/`);
await page.evaluate(({ t }) => {
  sessionStorage.setItem("goldens.api_token", t);
  sessionStorage.setItem("goldens.role", "admin");
  sessionStorage.setItem("goldens.name", "probe");
}, { t: TOKEN });

const rec = new Recorder("provenienz-plan-override", BASE);

// ── Step 1: Canvas zeigt den plan_proposal-Vorschlag ─────────────────────
await page.goto(`${BASE}/#/admin/doc/${SLUG}/provenienz`);
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(2500);
await selectSessionInRail(page, session.session_id);
await page.waitForTimeout(2000);
await clickPlanTile(page, proposalId);
await page.waitForTimeout(800);
await rec.step(page, `Sitzung + Plan-Vorschlag „${proposal.payload?.name}“ — Panel offen, Verwerfen sichtbar`, {
  actions: [
    `POST /sessions {slug, root_chunk_id:"${rootChunk}"}`,
    `POST /sessions/${session.session_id}/next-step`,
    "click plan_proposal-Tile im Canvas",
  ],
  notes: [
    "Setup: Sitzung über die API + /next-step liefert einen plan_proposal-Vorschlag.",
    "Klick auf die Tile öffnet das PlanProposalPanel rechts: Step-Name, Begründung, Alternativen, Akzeptieren + Verwerfen.",
    `LLM-Wahl: ${proposal.payload?.name} (${(proposal.payload?.reasoning || "").slice(0,110)}…)`,
    "Verwerfen ist der Eintrittspunkt für die Korrektur-Capture — ein einzelner Klick öffnet die Inline-Form.",
  ],
  shots: [{ annotations: [
    { kind: "note", text: "Plan-Proposal-Panel im Idle-Zustand: Akzeptieren + Verwerfen sichtbar." },
  ] }],
});

// ── Step 2: Verwerfen morpht in eine Inline-Form ─────────────────────────
await page.getByRole("button", { name: /^Verwerfen$/ }).click();
await page.waitForTimeout(500);
await rec.step(page, "Verwerfen-Klick → Inline-Form erscheint (Combobox + Textarea + Submit)", {
  actions: ['click button { name: "Verwerfen" }'],
  notes: [
    "Erster Klick auf Verwerfen morpht den Button — kein Modal, kein Page-Wechsel.",
    "Form-Felder oben → unten: „Stattdessen…“ (datalist-Combobox über valid_steps_per_anchor), „Warum?“ (Textarea, required), „Korrektur erfassen“-Submit, „Abbrechen“ / „Doch löschen“-Footer.",
    "Akzeptieren ist disabled solange die Form offen ist — vermeidet das versehentliche Doppel-Feuern „accept + override“ auf demselben Tile.",
    "Esc oder „Abbrechen“ kollabieren die Form ohne Submit; „Doch löschen“ ist der explizite Pfad „dieser Vorschlag war wirklich Rauschen“.",
  ],
  shots: [{ annotations: [
    { kind: "note", text: "Combobox-Input fokussiert (autoFocus); Submit disabled solange Reason leer." },
  ] }],
});

// ── Step 3: Bekannten Step wählen + Reason → Submit ──────────────────────
const reasonKnown = "Chunk ist eine Konstrukt-Definition, kein Faktum — Task formulieren passt besser.";
await page.getByLabel(/Stattdessen…/).fill("formulate_task");
await page.getByLabel(/Warum\?/).fill(reasonKnown);
await page.waitForTimeout(300);
await page.getByRole("button", { name: /Korrektur erfassen/ }).click();
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(1800);
// Bring the canvas focus back so the EC sibling tile is visible in the screenshot.
const sessAfter1 = await getSession(session.session_id);
const ecAfter1 = sessAfter1.nodes.filter(n => n.kind === "expert_step_override");
console.log(`After known-step submit: ${ecAfter1.length} expert_step_override node(s).`);
await clickPlanTile(page, proposalId);
await page.waitForTimeout(800);
await rec.step(page, `Submit „${decideCalls.at(-1)?.body?.expert_correction?.intended_step}“ → expert_step_override-Tile + dotted "stattdessen"-Edge`, {
  actions: [
    'fill input { name: "Stattdessen…" } → "formulate_task"',
    'fill textarea { name: "Warum?" } → reason',
    'click button { name: "Korrektur erfassen" }',
    `POST /sessions/${session.session_id}/decide`,
  ],
  notes: [
    "Submit feuert POST /decide mit dem typisierten expert_correction-Block: { proposal_node_id, expert_correction: { intended_step, intended_args: {}, reason } }.",
    "Phase-3: server schreibt einen expert_step_override-Node (kind discriminates, kein is_unimplemented-Flag mehr), einen NOTE-Skill mit correction_origin=\"plan_proposal\" ins Korpus und eine \"overrides\"-Edge zurück zum plan_proposal — der wird NICHT tombstoned, damit der Audit-Trail steht.",
    "Canvas rendert die Tile als roses Geschwister (Purpose 1 — teach the agent) mit dem dashed „stattdessen“-Edge — UI-Story: „Agent suggested X | Expert prescribed Y“.",
    `Erfasste expert_step_override-Nodes in der Session: ${ecAfter1.length}.`,
  ],
  shots: [{ annotations: [
    { kind: "note", text: "expert_step_override-Tile (rose) + dashed \"stattdessen\"-Edge zum amber plan_proposal." },
  ] }],
});

// ── Step 4: Unbekannte Methode → EC + capability_request ────────────────
await page.getByRole("button", { name: /^Verwerfen$/ }).click();
await page.waitForTimeout(400);
const unimplemented = "summarize_section";
const reasonUnknown = "Chunk braucht erst eine Zusammenfassung — diesen Step gibt es noch nicht.";
await page.getByLabel(/Stattdessen…/).fill(unimplemented);
await page.waitForTimeout(200);
await page.getByLabel(/Warum\?/).fill(reasonUnknown);
await page.waitForTimeout(300);
await page.getByRole("button", { name: /Korrektur erfassen/ }).click();
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(2000);
const sessAfter2 = await getSession(session.session_id);
const emrAfter2 = sessAfter2.nodes.filter(n => n.kind === "expert_method_request" && n.actor === "human");
const humanCRsAfter2 = sessAfter2.nodes.filter(n => n.kind === "capability_request" && n.actor === "human");
const crAggr = await fetchCapabilityRequests();
const aggrMatch = crAggr.find(r => r.name === unimplemented);
console.log(`After unknown-step submit: ${emrAfter2.length} expert_method_request node(s); ${humanCRsAfter2.length} legacy human-CR(s); aggregator name=${aggrMatch?.name}.`);
await clickPlanTile(page, proposalId);
await page.waitForTimeout(800);
await rec.step(page, `Unbekannte Methode „${unimplemented}“ → expert_method_request-Tile + Aggregator surfaces actor=human`, {
  actions: [
    `fill { name: "Stattdessen…" } → "${unimplemented}"`,
    `fill { name: "Warum?" } → reason`,
    'click "Korrektur erfassen"',
    `POST /sessions/${session.session_id}/decide`,
    "GET /capability-requests",
  ],
  notes: [
    "Der Combobox-Hint „Neuer Skill — wird auch als Capability-Wunsch erfasst“ erscheint, sobald die Eingabe nicht im valid_steps_per_anchor steckt.",
    "Phase-3: server schreibt EINEN expert_method_request-Node (Purpose 2 — mark a capability gap). Die capability_request-Payload-Felder (`name`, `description`) sind direkt in den Node gefaltet — kein separater capability_request-Spawn mehr. Der `capability_request`-Kind bleibt agent-only per Invariante.",
    "Aggregator unter /capability-requests includiert sowohl `capability_request` (agent-emitted) als auch `expert_method_request` (expert-prescribed) — actor-Field discriminates.",
    `Live im Aggregator: name=${aggrMatch?.name ?? "(missing)"} · count=${aggrMatch?.count ?? 0} · actor=${aggrMatch?.examples?.[0]?.actor ?? "—"}.`,
    "Phase-4 (Replikation): Capability-Wishlist-UI baut auf diesem typed-Mark auf — sortiert nach Häufigkeit, gruppiert nach intended_step, surfaces Build-this-Tool-Backlog für die Dev-Crew.",
  ],
  shots: [{ annotations: [
    { kind: "note", text: "Ein spawned-Node: expert_method_request (amber, AlertTriangle-Icon, „landet auf der Capability-Wunschliste“-Badge)." },
  ] }],
});

// ── Step 5: Leere Reason → Submit disabled, kein Network-Call ───────────
const decideCallsBefore = decideCalls.length;
await page.getByRole("button", { name: /^Verwerfen$/ }).click();
await page.waitForTimeout(400);
await page.getByLabel(/Stattdessen…/).fill("formulate_task");
// Warum bewusst leer lassen.
await page.waitForTimeout(300);
const submitBtn = page.getByRole("button", { name: /Korrektur erfassen/ });
const submitDisabled = await submitBtn.isDisabled();
await submitBtn.click({ trial: true }).catch(() => {}); // trial click = no real click, just hit-testing
await page.waitForTimeout(800);
const decideFiredOnEmpty = decideCalls.length - decideCallsBefore;
console.log(`Empty-reason guard: submitDisabled=${submitDisabled} · decide POSTs since=${decideFiredOnEmpty}.`);
await rec.step(page, "Leere Reason → Submit ist disabled, kein POST /decide", {
  actions: [
    'click "Verwerfen"',
    'fill { name: "Stattdessen…" } → "formulate_task"',
    "leave { name: \"Warum?\" } empty",
    "attempt click „Korrektur erfassen“",
  ],
  notes: [
    "Client-side Guard: canSubmitCorrection = trimmedStep ≠ \"\" && trimmedReason ≠ \"\" — beide müssen non-empty sein.",
    "Submit-Button rendert sich mit disabled-State (helles Grau, opacity-50, kein Hover-Highlight); der Click hat keine Wirkung.",
    `Server hört nichts: ${decideFiredOnEmpty} /decide POST(s) zwischen Verwerfen-Klick und jetzt.`,
    "Damit wird verhindert, dass jemand versehentlich eine Reason-lose Korrektur abschickt — Reason ist das einzig wirklich wichtige Datum für die Replikation des Expert-Flows.",
  ],
  shots: [{ annotations: [
    { kind: "note", text: `Submit disabled=${submitDisabled}, POSTs seit Click=${decideFiredOnEmpty}.` },
  ] }],
});

// ── Step 6: Esc kollabiert die Form ─────────────────────────────────────
await page.keyboard.press("Escape");
await page.waitForTimeout(600);
const formGone = (await page.getByLabel(/Stattdessen…/).count()) === 0;
const verwerfenBack = (await page.getByRole("button", { name: /^Verwerfen$/ }).count()) > 0;
console.log(`Esc collapse: form gone=${formGone}, Verwerfen back=${verwerfenBack}.`);
await rec.step(page, "Esc → Form kollabiert auf Verwerfen-Button zurück", {
  actions: ["press Escape"],
  notes: [
    "Document-Level keydown-Listener (gemounted nur solange die Form offen ist) räumt den lokalen State: verwerfenMode → idle, intendedStep → \"\", reason → \"\".",
    "Effekt: Form weg, Original-Buttons (Akzeptieren + Verwerfen) wieder sichtbar, Akzeptieren re-enabled, kein Network-Call.",
    "Cheaper Escape-Hatch für „eigentlich war ich nur am Stöbern, nicht am Übersteuern“ — kein Modal-Dismiss, keine doppelte Bestätigung.",
    `State nach Esc: form weg = ${formGone}; Verwerfen-Button wieder da = ${verwerfenBack}.`,
  ],
  shots: [{ annotations: [
    { kind: "note", text: "Panel zurück im Idle-Zustand — Akzeptieren + Verwerfen sichtbar." },
  ] }],
});

// Cleanup: drop the test session (also drops the recorded plan_proposal,
// expert_step_override, expert_method_request Nodes + edges).
await deleteSession(session.session_id);
console.log(`Cleanup: session ${session.session_id} gelöscht.`);
console.log(`Total /decide POSTs in this recording: ${decideCalls.length}`);

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);
