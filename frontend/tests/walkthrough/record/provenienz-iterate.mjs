// Walkthrough recording: provenienz-iterate
// End-to-end story for the Provenienz iteration loop:
//   ① Wurzel-Chunk in einer neuen Sitzung verankern
//   ② AI „rate den nächsten Schritt“ (POST /next-step) — LLM schlägt eine
//      ausführbare Aktion vor (extract_claims / formulate_task / search / …)
//   ③ User liest die Begründung im Plan-Proposal-Panel und entscheidet
//      (recommended / alt / override → /decide)
//
// Setup über die API, UI nur für visuelle Storyboard-Captures. Cleanup
// löscht die Wegwerf-Sitzung am Ende.

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8001";

// Pick a paragraph box on page 2 as the Wurzel-Chunk (rich enough that
// the LLM has something to propose against).
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
// Apply a plan_proposal: routes to the step-specific endpoint based on
// payload.name (extract_claims → /extract-claims, formulate_task →
// /formulate-task, …). Mirrors PlanProposalPanel.handleAccept.
async function applyPlanProposal(sid, proposal) {
  const p = proposal.payload;
  const trail = p.triggered_from_node_id || undefined;
  const body = { triggered_from_node_id: trail };
  let route;
  switch (p.name) {
    case "extract_claims":
      route = "extract-claims";
      body.chunk_node_id = p.anchor_node_id;
      break;
    case "formulate_task":
      route = "formulate-task";
      body.claim_node_id = p.anchor_node_id;
      break;
    case "search":
      route = "search";
      body.task_node_id = p.anchor_node_id;
      body.top_k = 5;
      break;
    default:
      throw new Error(`unsupported proposal name: ${p.name}`);
  }
  const r = await fetch(`${API}/api/admin/provenienz/sessions/${sid}/${route}`, {
    method: "POST",
    headers: { "X-Auth-Token": TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`apply ${p.name}: ${r.status} ${await r.text()}`);
  return r.json();
}
async function deleteSession(sid) {
  await fetch(`${API}/api/admin/provenienz/sessions/${sid}`, {
    method: "DELETE", headers: { "X-Auth-Token": TOKEN },
  }).catch(() => {});
}

const rootChunk = await findRootChunk();
if (!rootChunk) throw new Error("no paragraph box on page 2");
const session = await createSession(rootChunk);
console.log("Created session", session.session_id, "anchored at", rootChunk);
const chunkNodeId = (await getSession(session.session_id)).nodes[0].node_id;

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 } });
const page = await ctx.newPage();
await page.goto(`${BASE}/`);
await page.evaluate(({ t }) => {
  sessionStorage.setItem("goldens.api_token", t);
  sessionStorage.setItem("goldens.role", "admin");
  sessionStorage.setItem("goldens.name", "probe");
}, { t: TOKEN });

const rec = new Recorder("provenienz-iterate", BASE);

// ── Step 1: Provenienz mit der frischen Sitzung ───────────────────────────
await page.goto(`${BASE}/#/admin/doc/${SLUG}/provenienz`);
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(2500);
await rec.step(page, `Sitzung mit Wurzel-Chunk „${rootChunk}“ — Canvas zeigt nur den Anker`, {
  actions: [
    `POST /sessions {slug, root_chunk_id:"${rootChunk}"}`,
    `goto /admin/doc/${SLUG}/provenienz`,
  ],
  notes: [
    "Neue Sitzung wird mit genau einem Knoten initialisiert — dem Wurzel-Chunk (kind=chunk).",
    "Linkes Rail: Sitzungs-Liste; Canvas mittig: Graph mit dem Chunk-Anker; rechtes Panel: Detail der ausgewählten Node.",
    "Sitzung wird über /sessions angelegt; root_chunk_id verweist auf eine MinerU-Box-ID (z.B. p2-b0).",
  ],
  shots: [{ annotations: [
    { kind: "note", text: `Session-ID: ${session.session_id.slice(0,12)}…` },
  ] }],
});

// ── Step 2: AI rät den nächsten Schritt → plan_proposal node ──────────────
const proposal = await triggerNextStep(session.session_id, chunkNodeId);
const proposalId = proposal.node_id;
console.log("AI proposed:", proposal.payload?.name, "(node_id:", proposalId, ")");
await page.reload();
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(2500);
await rec.step(page, `AI-Vorschlag: ${proposal.payload?.name || "—"} (plan_proposal Node)`, {
  actions: [`POST /sessions/${session.session_id}/next-step {anchor_node_id}`],
  notes: [
    "/next-step lässt den Planer den Kontext um den Anker zusammensuchen (Chunk-Text, vorhandene Claims, gesteckte Approaches), wählt eine ausführbare Aktion + begründet sie.",
    "Antwort = neuer plan_proposal Node mit payload.name (z.B. „extract_claims“, „formulate_task“, „search“) + reasoning + alt-Vorschlägen.",
    "Im Canvas erscheint die Vorschlags-Tile als Kind des Anker-Chunks; UI zeigt sie hellblau mit dem Sparkles-Icon.",
    `Konkrete AI-Wahl: ${proposal.payload?.name || "n/a"}`,
    `Begründung (gekürzt): „${(proposal.payload?.reasoning || "").slice(0,140)}…“`,
  ],
  shots: [{ annotations: [
    { kind: "note", text: `Proposal-Node: ${proposalId.slice(0,12)}…` },
  ] }],
});

// ── Step 3: User liest Vorschlag → Plan-Proposal-Panel im Detail ──────────
// (UI: Klick auf den Proposal-Node würde das PlanProposalPanel öffnen)
await page.waitForTimeout(1200);
await rec.step(page, "User liest Begründung + Alternativen im rechten Panel", {
  actions: ["click proposal node in canvas (UI flow)"],
  notes: [
    "PlanProposalPanel rendert: Schritt-Name, Begründung, Goal-Alignment, mögliche Alternativen, „Anwenden“-Button.",
    "Der User entscheidet, ob er die AI-Empfehlung übernimmt, eine Alternative wählt oder komplett überschreibt.",
    "Drei Entscheidungs-Pfade: recommended (AI-Wahl) · alt (Alternative aus dem Vorschlag) · override (eigene Aktion).",
  ],
  shots: [{ annotations: [
    { kind: "note", text: "Plan-Proposal-Panel zeigt Begründung + Alternativen + Apply-Button" },
  ] }],
});

// ── Step 4: User akzeptiert → ruft step-spezifischen Endpoint (kein /decide) ─
const result = await applyPlanProposal(session.session_id, proposal);
const sessAfter = await getSession(session.session_id);
const newNodes = sessAfter.nodes.filter(n => n.kind !== "chunk" && n.node_id !== proposalId);
await page.reload();
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(2500);
await rec.step(page, `„Anwenden“ klicken → ${proposal.payload.name} läuft → ${newNodes.length} neue Nodes`, {
  actions: [`POST /sessions/${session.session_id}/${proposal.payload.name.replace(/_/g,'-')}`],
  notes: [
    "PlanProposalPanel.handleAccept routet anhand payload.name auf den passenden Step-Endpoint (extract_claims → /extract-claims, formulate_task → /formulate-task, search → /search).",
    "Wichtig: /decide ist ein anderer Pfad — er gilt nur für action_proposal-Nodes (z.B. Promote/Decompose/Investigate, wo der User aus mehreren Hits auswählt).",
    `Konkret hier: ${proposal.payload.name} produziert ${newNodes.length} neue Sub-Node(s) unter dem Chunk-Anker.`,
    "Damit ist eine Iteration der Provenance-Kette komplett. Vom neuen Node kann erneut /next-step ausgelöst werden — die Kette wächst iterativ zum DAG.",
    "Audit-Trail bleibt: der plan_proposal-Tile wird NICHT gelöscht („Reviewers sehen agent suggested X → step Y produced Z“).",
  ],
  shots: [{ annotations: [
    { kind: "note", text: `${newNodes.length} neue Node(s) hängen unter dem Anker` },
  ] }],
});

// Cleanup
await deleteSession(session.session_id);
console.log("Cleanup: session deleted.");

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);
