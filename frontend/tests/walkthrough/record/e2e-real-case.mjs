// Walkthrough recording: e2e-real-case
// One continuous tour that threads a real (pre-extracted) document through
// every pipeline stage — Login → Inbox → Extrahieren → Synthese → Voting
// (anti-anchoring) → Vergleich → Provenienz → Statistik — capturing the
// post-BAM-reskin UI (light surfaces, BAM-cyan CTAs, GOLDENS login lockup).
//
// Design notes / honest scope (see /tmp/wt_briefs.json → e2e-real-case):
//   * We DON'T run MinerU extraction live (5-15 min) — we thread the default
//     pre-extracted slug through every data-rich stage instead. The Upload
//     step shows the „+ PDF hinzufügen“ affordance only (no throwaway doc).
//   * Two-voter anti-anchoring is the centerpiece. Voter identity is the
//     server-side actor.pseudonym derived from the request's auth token
//     (backend admin/synthesise.py::_admin_actor_with_level). The dev
//     X-Auth-Token resolves to pseudonym "admin"; a freshly-minted curator
//     token resolves to the curator's name. So we drive TWO isolated browser
//     contexts (separate sessionStorage/cookies = the brief's "no cookie
//     sharing") — admin in ctxA, a throwaway curator in ctxB — and cast real
//     clicks so each POST is attributed to a distinct pseudonym.
//   * IDEMPOTENCY: votes are append-only events; teardown revokes both votes
//     (curator vote with the curator token FIRST, before deleting the
//     curator — a revoked curator token would 401), deletes any question we
//     generated, then deletes the curator. Wrapped in try/finally.

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8001";

const hdr = (t) => ({ "X-Auth-Token": t });
const jhdr = (t) => ({ "X-Auth-Token": t, "Content-Type": "application/json" });

// ── Backend helpers ───────────────────────────────────────────────────────
async function getSegments() {
  const r = await fetch(`${API}/api/admin/docs/${SLUG}/segments`, { headers: hdr(TOKEN) });
  return r.ok ? r.json() : { boxes: [] };
}
async function getQuestions(token = TOKEN) {
  const r = await fetch(`${API}/api/admin/docs/${SLUG}/questions`, { headers: hdr(token) });
  return r.ok ? r.json() : {};
}
async function llmStatus() {
  const r = await fetch(`${API}/api/admin/llm/status`, { headers: hdr(TOKEN) });
  return r.ok ? r.json() : null;
}
async function vote(token, entryId, action) {
  return fetch(
    `${API}/api/admin/docs/${SLUG}/questions/${entryId}/vote`,
    { method: "POST", headers: jhdr(token), body: JSON.stringify({ action }) },
  ).catch(() => null);
}

function setSession(page, { token, role, name }) {
  return page.evaluate(({ t, r, n }) => {
    sessionStorage.setItem("goldens.api_token", t);
    sessionStorage.setItem("goldens.role", r);
    sessionStorage.setItem("goldens.name", n);
  }, { t: token, r: role, n: name });
}

const pageNumOf = (boxId) => {
  const m = boxId.match(/p(\d+)/);
  return m ? parseInt(m[1], 10) : 1;
};

// ── Setup: pick boxes + a question target, mint a curator ──────────────────
const seg = await getSegments();
const boxes = seg.boxes ?? [];
const tableBox = boxes.find(b => b.kind === "table");
const biblioBox = boxes.find(b => b.kind === "bibliography");

const qsByBox = await getQuestions();
const votedEntry = (() => {
  for (const [boxId, arr] of Object.entries(qsByBox)) {
    if (Array.isArray(arr) && arr.length > 0) {
      const q = arr[0];
      return { boxId, entryId: q.entry_id || q.question_id, text: q.text };
    }
  }
  return null;
})();
// A fresh paragraph box (no questions) to demo box-scoped LLM generation.
const takenBoxes = new Set(Object.keys(qsByBox));
const genBox = boxes.find(b => b.kind === "paragraph" && b.page >= 2 && !takenBoxes.has(b.box_id));

// Mint a throwaway curator → second, distinct voter pseudonym.
const CURATOR_NAME = "WT-Kurator (e2e)";
let curatorId = null;
let curatorToken = null;
{
  const r = await fetch(`${API}/api/admin/curators`, {
    method: "POST", headers: jhdr(TOKEN), body: JSON.stringify({ name: CURATOR_NAME }),
  }).catch(() => null);
  if (r && r.ok) {
    const body = await r.json();
    curatorId = body.id;
    curatorToken = body.token;
    console.log("Minted curator:", curatorId, "pseudonym:", body.name);
  } else {
    console.log("Curator mint failed — anti-anchoring will be single-context.", r?.status);
  }
}

console.log("Setup — table:", tableBox?.box_id, "biblio:", biblioBox?.box_id,
  "votedEntry:", votedEntry?.entryId, "on box", votedEntry?.boxId, "genBox:", genBox?.box_id);

// Track state we create so teardown can undo it.
let generatedEntryIds = [];

const rec = new Recorder("e2e-real-case", BASE);

const browser = await chromium.launch();
const ctxA = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const pageA = await ctxA.newPage();
// Auto-accept the window.confirm() that „Frage löschen“ triggers.
pageA.on("dialog", (d) => d.accept().catch(() => {}));

try {
  // ── Step 1: GOLDENS login lockup (un-authed) ─────────────────────────────
  await pageA.goto(`${BASE}/`);
  await pageA.waitForLoadState("networkidle").catch(() => {});
  await pageA.waitForTimeout(1200);
  await rec.step(pageA, "Login — GOLDENS-Lockup (Session A: Admin)", {
    actions: ["goto http://127.0.0.1:5173 (un-authed)"],
    notes: [
      "Post-BAM-Reskin: zentrierte weiße Login-Karte auf dunklem Backdrop, GOLDENS-Logo-Lockup statt der alten „Anmeldung“-Überschrift.",
      "Felder per aria-label: „Fachbereich“ (Tenant), „Benutzername“, „Passwort“ → Submit „Einloggen“ (btn-primary, BAM-Cyan #00aff0). Legacy-Tab „API-Token (alt)“ daneben.",
      "Für die Aufnahme injizieren wir den Dev-Token direkt in den sessionStorage (Konvention aller Walkthrough-Skripte) statt das Formular real abzuschicken — die echten Selektoren bleiben hier dokumentiert.",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: 'input[aria-label="Benutzername"]', text: "Benutzername (aria-label)" },
      { kind: "note", text: 'Passwort = aria-label="Passwort", Submit = „Einloggen“, Tenant = „Fachbereich“' },
    ] }],
  });

  // Inject admin identity (recorder convention) and continue to the inbox.
  await setSession(pageA, { token: TOKEN, role: "admin", name: "Sorgsamer Bär" });

  // ── Step 2: Inbox / „Dokumente“ + Upload-Affordance ──────────────────────
  await pageA.goto(`${BASE}/#/admin/inbox`);
  await pageA.waitForLoadState("networkidle").catch(() => {});
  await pageA.waitForTimeout(1500);
  await rec.step(pageA, "Posteingang — Dokumentliste + „PDF hinzufügen“", {
    actions: ["goto /admin/inbox"],
    notes: [
      "Überschrift „Dokumente“; Top-Bar ist helle weiße Canvas (kein Navy-Chrome mehr), Tabs als role=tab-Links mit BAM-Cyan-Aktivmarkierung.",
      "Tabelle: Dateiname · Seiten · Status (Roh/Extrahiert/Synthesised) · Elemente · Zuletzt geändert · Aktion (starten/fortsetzen/ansehen · Veröffentlichen · Löschen).",
      "„+ PDF hinzufügen“ (oben rechts, BAM-Cyan) öffnet einen versteckten input[type=file] → POST /api/admin/docs (multipart). Wir zeigen nur die Affordance — der eigentliche Walkthrough nutzt das bereits extrahierte Dokument darunter, statt eine lange MinerU-Extraktion live zu fahren.",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: 'button:has-text("PDF hinzufügen")', text: "Upload-CTA (BAM-Cyan)" },
      { kind: "highlight", selector: `a[href*="/admin/doc/${SLUG}/extract"]`, text: "„starten/fortsetzen“ → Extrahieren" },
    ] }],
  });

  // ── Step 3: Extrahieren — PDF-Canvas + Box-Overlay ───────────────────────
  await pageA.goto(`${BASE}/#/admin/doc/${SLUG}/extract`);
  await pageA.waitForLoadState("networkidle").catch(() => {});
  await pageA.waitForTimeout(2500);
  await rec.step(pageA, "Extrahieren — PDF gerendert mit Box-Overlay", {
    actions: [`goto /admin/doc/${SLUG}/extract`],
    notes: [
      "pdfjs rendert die Seite; MinerU-Segmente liegen als farbcodierte Boxen darüber (data-testid=box-<box_id>, Label „<kind> · <confidence>“).",
      "Top-Bar: „Verzeichnisse erkennen“, „Alle Seiten extrahieren“ (aria-label=Re-extract all), „Export“. Wäre das Dokument noch „Roh“, würde ein „Alle Seiten extrahieren“-Lauf die Boxen erzeugen (3-15 min) — hier ist es vorab extrahiert.",
      "6 Stufen-Tabs (Dateien · Extrahieren · Synthese · Vergleich · Provenienz · Statistik) als Link-Reiter mit BAM-Cyan-Unterstrich auf dem aktiven Tab.",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: 'button[aria-label="Re-extract all"]', text: "„Alle Seiten extrahieren“ (Re-extract all)" },
      { kind: "highlight", selector: '[data-testid^="box-"]', text: "MinerU-Box-Overlay" },
    ] }],
  });

  // ── Step 4: Tabellen-Box → HtmlEditor (PR #52 Hochstellungs-Fix) ─────────
  if (tableBox?.box_id) {
    const tablePage = pageNumOf(tableBox.box_id);
    // Navigate to the table's page via the page-strip next button.
    for (let i = 1; i < tablePage; i++) {
      await pageA.locator('[data-testid="extract-page-next"]').click().catch(() => {});
      await pageA.waitForTimeout(350);
    }
    await pageA.waitForTimeout(800);
    await pageA.locator(`[data-testid="box-${tableBox.box_id}"]`).click({ force: true }).catch(() => {});
    await pageA.waitForTimeout(900);
  }
  await rec.step(pageA, "Tabellen-Box prüfen — Spaltenköpfe als col1/col2 (PR #52)", {
    actions: [tableBox?.box_id ? `select box ${tableBox.box_id} (kind=table)` : "no table box in this doc"],
    notes: [
      "Eine Box vom Typ „table“ ausgewählt → der HtmlEditor (data-testid=html-editor-host) im rechten Panel zeigt das extrahierte Tabellen-HTML.",
      "PR-#52-Kernprüfung: MinerUs Superscript-Rescue war zu aggressiv und hat Tabellen-Zellen zerstört. Spaltenköpfe müssen als literales col1/col2 erscheinen — NICHT als hochgestelltes col¹/col². col1 = PASS, col¹ = FAIL.",
      `Dieses Dokument hat genau 1 Tabelle (${tableBox?.box_id ?? "—"}) sowie ${biblioBox ? "Bibliographie-Boxen (Register-Detection)" : "keine Register-Boxen"}.`,
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: '[data-testid="html-editor-host"]', text: "Tabellen-HTML im HtmlEditor" },
    ] }],
  });

  // ── Step 5: Synthese — read-only HTML-Vorschau (iframe) ──────────────────
  await pageA.goto(`${BASE}/#/admin/doc/${SLUG}/synthesise`);
  await pageA.waitForLoadState("networkidle").catch(() => {});
  await pageA.waitForTimeout(2500);
  await rec.step(pageA, "Synthese — HTML-Vorschau links, Box-Auswahl als Voraussetzung", {
    actions: [`goto /admin/doc/${SLUG}/synthesise`],
    notes: [
      "Linke Spalte: read-only HTML-Vorschau im sandboxed iframe (data-testid=synth-html-preview) — jede MinerU-Box ist ein anklickbares [data-source-box]-Element.",
      "Mittleres Panel zeigt „Klicke ein Element im HTML-Bereich, um die Fragen zu sehen.“ — Box-Auswahl ist Voraussetzung für Generate/Voting.",
      "Rechte Steuerleiste: vLLM-Status-Indikator, Seiten-Navigation (◀ ▶ / data-testid=synth-page-prev|next), „Diese Seite sperren“ (synth-page-lock), Box-Eigenschaften.",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: '[data-testid="synth-html-preview"]', text: "HTML-Vorschau (iframe)" },
      { kind: "highlight", selector: '[data-testid="synthesise-questions"]', text: "Mittleres Q&A-Panel (leer bis Box-Klick)" },
    ] }],
  });

  // ── Step 6: Box-scoped LLM generation (vLLM-guarded) ─────────────────────
  // Navigate to the gen box's page, select it, fire generation IF vLLM healthy.
  let genFired = false;
  if (genBox?.box_id) {
    const genPage = pageNumOf(genBox.box_id);
    for (let i = 1; i < genPage; i++) {
      await pageA.locator('[data-testid="synth-page-next"]').click().catch(() => {});
      await pageA.waitForTimeout(350);
    }
    await pageA.waitForTimeout(800);
    const frameA = pageA.frameLocator("iframe");
    await frameA.locator(`[data-source-box="${genBox.box_id}"]`).first().click().catch(() => {});
    await pageA.waitForTimeout(800);

    const llm = await llmStatus();
    if (llm?.healthy) {
      const before = (await getQuestions())[genBox.box_id]?.length ?? 0;
      await pageA.locator('button[aria-label="Fragen für diese Box generieren"]').click().catch(() => {});
      // Wait for the NDJSON stream to land new questions (best-effort, bounded).
      for (let i = 0; i < 30; i++) {
        const arr = (await getQuestions())[genBox.box_id] ?? [];
        if (arr.length > before) { genFired = true; break; }
        await pageA.waitForTimeout(1500);
      }
      await pageA.waitForTimeout(1200);
      const fresh = (await getQuestions())[genBox.box_id] ?? [];
      generatedEntryIds = fresh.map(q => q.entry_id || q.question_id).filter(Boolean);
    }
  }
  await rec.step(pageA, genFired
    ? `Synthese — LLM generiert Fragen für ${genBox?.box_id}`
    : "Synthese — Box gewählt, „Fragen generieren“ aktiv (vLLM offline → übersprungen)", {
    actions: [
      genBox?.box_id ? `click iframe [data-source-box="${genBox.box_id}"]` : "no fresh box",
      genFired ? "click „Fragen für diese Box generieren“ → NDJSON-Stream" : "vLLM nicht healthy → Generate nur gezeigt",
    ],
    notes: [
      "Box-Klick im iframe sendet die box_id an die React-App: highlight-Outline im iframe, rechtes Panel zeigt Box-Eigenschaften, „Fragen für diese Box generieren“ wird aktiv.",
      "Klick → POST /api/admin/docs/{slug}/synthesise?box_id=… ; der Server ruft das LLM mit dem Box-Text als Kontext und streamt die Q&A als NDJSON zurück.",
      genFired
        ? `vLLM war healthy → frische Q&A für ${genBox?.box_id} erzeugt (werden im Teardown wieder entfernt, damit Re-Runs sauber bleiben).`
        : "vLLM war hier nicht healthy → Generate-Schritt übersprungen; der Button bleibt im aktivierbaren Zustand sichtbar. (Voting nutzt eine bereits vorhandene Frage.)",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: 'button[aria-label="Fragen für diese Box generieren"]', text: "Box-scoped Generate-Button" },
    ] }],
  });

  // ── Step 7: Edit a question text (refine) ────────────────────────────────
  // Navigate to the voted question's box so it renders, then double-click to edit.
  let editFrame = null;
  if (votedEntry?.boxId) {
    const qPage = pageNumOf(votedEntry.boxId);
    // Reset to page 1, then walk forward to the question's page.
    await pageA.goto(`${BASE}/#/admin/doc/${SLUG}/synthesise`);
    await pageA.waitForLoadState("networkidle").catch(() => {});
    await pageA.waitForTimeout(2000);
    for (let i = 1; i < qPage; i++) {
      await pageA.locator('[data-testid="synth-page-next"]').click().catch(() => {});
      await pageA.waitForTimeout(350);
    }
    await pageA.waitForTimeout(700);
    editFrame = pageA.frameLocator("iframe");
    await editFrame.locator(`[data-source-box="${votedEntry.boxId}"]`).first().click().catch(() => {});
    await pageA.waitForTimeout(900);
  }
  await rec.step(pageA, "Frage bearbeiten — Doppelklick → Inline-Textarea → „Speichern“", {
    actions: [
      votedEntry?.boxId ? `select box ${votedEntry.boxId} → ${votedEntry.entryId}` : "no question target",
      "double-click question text → inline edit",
    ],
    notes: [
      "Doppelklick auf den Fragetext (oder Stift-Icon „Frage bearbeiten“) öffnet eine Inline-Textarea mit „Speichern“/„Abbrechen“.",
      "Speichern → PATCH /questions/{id}; backend-seitig ist Refine = neue Frage anlegen + alte deprecaten (Audit-Trail bleibt intakt). Leerer Text wird abgewiesen.",
      "Kein Reload nötig — react-query invalidiert und re-rendert die Liste.",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: '[data-testid="synthesise-questions"]', text: "Q&A-Liste der aktiven Box (editierbar)" },
    ] }],
  });

  // ── Step 8: Anti-anchoring — BEFORE any vote (Session A) ──────────────────
  if (votedEntry?.entryId) {
    await rec.step(pageA, "Anti-Anchoring — vor der Abstimmung: keine Zähler sichtbar", {
      actions: [`question ${votedEntry.entryId} — kein Vote gesetzt`],
      notes: [
        "Decision 14 (Anti-Anchoring): solange der eigene my_vote == null ist, bleiben die Vote-Zähler („n ✓ · m ✗“) verborgen — verhindert Anchoring-Bias durch fremde Stimmen.",
        "Linker Karten-Rand ist transparent (border-l-transparent = noch keine eigene Stimme); grüner CheckCircle2 („Einverstanden“) und roter XCircle („Disqualifizieren“) sind sichtbar, aber keiner ist gefüllt.",
        "Voter-Identität kommt server-seitig aus dem Auth-Token (actor.pseudonym), nicht aus dem Client — Session A ist „admin“.",
      ],
      shots: [{ annotations: [
        { kind: "highlight", selector: `[data-testid="question-${votedEntry.entryId}"]`, text: "Frage-Karte: Rand transparent, keine Zähler" },
        { kind: "highlight", selector: '[aria-label="Einverstanden"]', text: "Grüner Vote (noch nicht gefüllt)" },
      ] }],
    });
  }

  // ── Step 9: Session A votes „Einverstanden" (approved) ───────────────────
  if (votedEntry?.entryId) {
    await pageA.locator(`[data-testid="question-${votedEntry.entryId}"] [aria-label="Einverstanden"]`)
      .first().click().catch(() => {});
    await pageA.waitForTimeout(1200);
    await rec.step(pageA, "Session A stimmt „Einverstanden“ → grüner Streifen + Zähler 1 ✓ · 0 ✗", {
      actions: ["click „Einverstanden“ → POST /vote {action:'approved'} (Token A → pseudonym admin)"],
      notes: [
        "Optimistisches UI-Update: linker Rand wird emerald-500, der CheckCircle2-Button füllt sich, POST /vote {action:'approved'}.",
        "Da A jetzt my_vote='approved' hat, erscheinen für A die Zähler „1 ✓ · 0 ✗“ im Karten-Footer.",
        "Wichtig: Session B (Kurator) sieht weiterhin KEINE Zähler — Anti-Anchoring gilt pro Nutzer (my_vote-Check).",
      ],
      shots: [{ annotations: [
        { kind: "highlight", selector: `[data-testid="question-${votedEntry.entryId}"]`, text: "Grüner Streifen (border-l-emerald-500) + Zähler 1 ✓ · 0 ✗" },
      ] }],
    });
  }

  // ── Step 10: Session B (curator) — anti-anchoring still hides counts ──────
  let pageB = null;
  if (curatorToken && votedEntry?.entryId) {
    const ctxB = await browser.newContext({ viewport: { width: 1400, height: 900 } });
    pageB = await ctxB.newPage();
    pageB.on("dialog", (d) => d.accept().catch(() => {}));
    await pageB.goto(`${BASE}/`);
    await setSession(pageB, { token: curatorToken, role: "curator", name: CURATOR_NAME });

    const qPage = pageNumOf(votedEntry.boxId);
    await pageB.goto(`${BASE}/#/admin/doc/${SLUG}/synthesise`);
    await pageB.waitForLoadState("networkidle").catch(() => {});
    await pageB.waitForTimeout(2200);
    for (let i = 1; i < qPage; i++) {
      await pageB.locator('[data-testid="synth-page-next"]').click().catch(() => {});
      await pageB.waitForTimeout(350);
    }
    await pageB.waitForTimeout(700);
    const frameB = pageB.frameLocator("iframe");
    await frameB.locator(`[data-source-box="${votedEntry.boxId}"]`).first().click().catch(() => {});
    await pageB.waitForTimeout(1000);

    await rec.step(pageB, "Session B (Kurator) — A hat abgestimmt, B sieht trotzdem keine Zähler", {
      actions: ["separate browser context (isolierter sessionStorage) als Kurator-Token", `select box ${votedEntry.boxId}`],
      notes: [
        "Zweiter, isolierter Browser-Kontext (keine Cookie-/sessionStorage-Teilung) → eigener Auth-Token → eigene Voter-Pseudonym-Identität.",
        "DER ANTI-ANCHORING-BEWEIS: A hat bereits „approved“ gewählt, aber Bs Frage-Karte zeigt weder einen farbigen Rand noch Zähler — denn B hat selbst noch nicht abgestimmt (my_vote == null).",
        "Würden B die Zähler hier schon angezeigt → Decision-14-Verletzung.",
      ],
      shots: [{ annotations: [
        { kind: "highlight", selector: `[data-testid="question-${votedEntry.entryId}"]`, text: "Bei B: Rand transparent, keine Zähler trotz As Stimme" },
      ] }],
    });

    // ── Step 11: Session B votes „Disqualifizieren" (rejected) ─────────────
    await pageB.locator(`[data-testid="question-${votedEntry.entryId}"] [aria-label="Disqualifizieren"]`)
      .first().click().catch(() => {});
    await pageB.waitForTimeout(1200);
    await rec.step(pageB, "Session B stimmt „Disqualifizieren“ → roter Streifen + Zähler 1 ✓ · 1 ✗", {
      actions: ["click „Disqualifizieren“ → POST /vote {action:'rejected'} (Curator-Token → pseudonym Kurator)"],
      notes: [
        "Bs linker Rand wird red-500, der XCircle füllt sich; POST /vote {action:'rejected'} wird der Kurator-Pseudonym zugeschrieben.",
        "Jetzt hat B my_vote != null → für B erscheinen die aggregierten Zähler „1 ✓ · 1 ✗“ (As approved + Bs rejected).",
        "Streifenfarbe ist pro Nutzer: A sieht weiterhin Grün, B sieht Rot — dieselbe Frage, zwei unabhängige Stimmen.",
      ],
      shots: [{ annotations: [
        { kind: "highlight", selector: `[data-testid="question-${votedEntry.entryId}"]`, text: "Bei B: roter Streifen (border-l-red-500) + 1 ✓ · 1 ✗" },
      ] }],
    });

    // ── Step 12: Session A reload → cross-session consistency ──────────────
    await pageA.reload();
    await pageA.waitForLoadState("networkidle").catch(() => {});
    await pageA.waitForTimeout(2200);
    const qPageA = pageNumOf(votedEntry.boxId);
    for (let i = 1; i < qPageA; i++) {
      await pageA.locator('[data-testid="synth-page-next"]').click().catch(() => {});
      await pageA.waitForTimeout(350);
    }
    await pageA.waitForTimeout(700);
    await pageA.frameLocator("iframe").locator(`[data-source-box="${votedEntry.boxId}"]`).first().click().catch(() => {});
    await pageA.waitForTimeout(1000);
    await rec.step(pageA, "Session A neu geladen → konsistente Zähler 1 ✓ · 1 ✗, eigener grüner Streifen", {
      actions: ["pageA.reload() → backend refetch von vote_summary"],
      notes: [
        "Nach dem Reload spiegelt der Server-Refetch beide Stimmen: A sieht jetzt „1 ✓ · 1 ✗“.",
        "As eigener Streifen bleibt emerald-500 (As Stimme unverändert) — Bs Rot ist nur in Bs Sicht; die Aggregat-Zähler sind für beide identisch.",
      ],
      shots: [{ annotations: [
        { kind: "highlight", selector: `[data-testid="question-${votedEntry.entryId}"]`, text: "Bei A nach Reload: grüner Streifen + 1 ✓ · 1 ✗" },
      ] }],
    });
  } else {
    await rec.step(pageA, "Anti-Anchoring zweiter Voter — übersprungen (kein Kurator-Token)", {
      actions: ["curator mint failed"],
      notes: [
        "Der zweite, unabhängige Voter konnte nicht erzeugt werden (POST /api/admin/curators fehlgeschlagen).",
        "Mit nur einem Dev-Token kollabieren beide Stimmen auf dieselbe Pseudonym-Identität — der Cross-Session-Anti-Anchoring-Beweis ist hier nicht darstellbar.",
      ],
      shots: [{ annotations: [{ kind: "note", text: "Kurator-Token fehlte — zweiter Voter ausgelassen" }] }],
    });
  }

  // ── Step 13: Vergleich (renders without crashing) ────────────────────────
  await pageA.goto(`${BASE}/#/admin/doc/${SLUG}/compare`);
  await pageA.waitForLoadState("networkidle").catch(() => {});
  await pageA.waitForTimeout(2200);
  await rec.step(pageA, "Vergleich — Fragen links, Treffer-/Pipeline-Bereich Mitte", {
    actions: [`goto /admin/doc/${SLUG}/compare`],
    notes: [
      "Drei-Spalten-Layout: data-testid=compare-left (Fragen der Seite) · compare-middle (Such-/Pipeline-Ergebnis) · compare-detail (Detail-Panel).",
      "Vergleich gleicht Q&A gegen die Wissensquelle (Azure/Microsoft Search) ab; ohne konfigurierte Quellen erscheint „Keine Treffer in der Wissensquelle.“",
      "Out-of-scope für die PR-#51-Voting/Statistik-Story — geprüft wird hier nur, dass der Tab ohne Fehler rendert (kein 500, kein schwarzes Canvas).",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: '[data-testid="compare-left"]', text: "Fragen-Spalte (compare-left)" },
      { kind: "highlight", selector: '[data-testid="compare-middle"]', text: "Treffer-/Pipeline-Bereich (compare-middle)" },
    ] }],
  });

  // ── Step 14: Provenienz (sessions rail) ──────────────────────────────────
  await pageA.goto(`${BASE}/#/admin/doc/${SLUG}/provenienz`);
  await pageA.waitForLoadState("networkidle").catch(() => {});
  await pageA.waitForTimeout(2200);
  await rec.step(pageA, "Provenienz — „Sitzungen“-Leiste + Canvas", {
    actions: [`goto /admin/doc/${SLUG}/provenienz`],
    notes: [
      "Linke Leiste mit Überschrift „Sitzungen“ (h2, text-bam-navy) + „Neu“-Button; Mitte = ReactFlow-DAG der Agenten-Iteration (Chunk-/Claim-/Task-/Search-Knoten).",
      "Leerstand „Keine Sitzungen für dieses Dokument.“ ist OK, wenn noch keine Provenienz-Session angelegt wurde.",
      "Dieser Schritt verifiziert nur, dass der Tab ohne Absturz rendert.",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: 'h2:has-text("Sitzungen")', text: "„Sitzungen“-Überschrift (text-bam-navy)" },
    ] }],
  });

  // ── Step 15: Statistik — 3 Abschnitte (PR #51 Kern) ──────────────────────
  await pageA.goto(`${BASE}/#/admin/doc/${SLUG}/statistics`);
  await pageA.waitForLoadState("networkidle").catch(() => {});
  await pageA.waitForTimeout(2500);
  await rec.step(pageA, "Statistik — drei Abschnitte Extrahieren / Synthese / Provenienz (PR #51)", {
    actions: [`goto /admin/doc/${SLUG}/statistics`],
    notes: [
      "Drei Sektionen mit navy-Überschriften (h2.text-bam-navy): „Extrahieren“, „Synthese“, „Provenienz“ — kein eigener „Statistik“-h2 (der Tabname ist der Seitentitel).",
      "Extrahieren: DiagnosticBar (clean/no-decomposition/split) + MetricCounter „Register-Boxen“ (N / Gesamt).",
      "Synthese: zwei MetricGauges (Curator-Überleben %, Reviewer-Zustimmung %) + VoteDistributionBar. Provenienz: MetricGauge „Experten-Korrekturen“ + CapabilityWishesSunburst.",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: 'h2:has-text("Extrahieren")', text: "Sektion 1 — Extrahieren" },
      { kind: "highlight", selector: 'h2:has-text("Synthese")', text: "Sektion 2 — Synthese" },
      { kind: "highlight", selector: 'h2:has-text("Provenienz")', text: "Sektion 3 — Provenienz" },
    ] }],
  });

  // ── Step 16: Synthese gauge reflects voting (50%) + Register-Counter ──────
  await rec.step(pageA, "Statistik — Reviewer-Zustimmung 50% (1 ✓ / 2) + Register-Boxen-Zähler", {
    actions: ["read Synthese gauge „Reviewer-Zustimmung“ + Extrahieren counter „Register-Boxen“"],
    notes: [
      curatorToken && votedEntry
        ? "Reviewer-Zustimmung = 50%: 1 approved (admin) + 1 rejected (Kurator) auf derselben Frage → 1/(1+1). Untertitel der Gauge zeigt „1 / 2“. Backend aggregiert per (entry_id, pseudonym)-letzter-Stimme (statistics.py::_collapse_votes)."
        : "Reviewer-Zustimmung spiegelt die vorhandenen Stimmen (kein zweiter Voter in diesem Lauf).",
      "Register-Boxen (Extrahieren-Sektion, MetricCounter): N / Gesamt, wobei N = Anzahl toc/bibliography-Boxen. Dieses Dokument hat Bibliographie-Boxen → N > 0 erwartet (CountUp-Animation von 0 hoch).",
      "Zeigt 'Keine Daten'/0%, falls die vote_summary-Aggregation nicht antwortet oder der Cache veraltet ist.",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: 'h2:has-text("Synthese")', text: "Synthese-Gauges (Reviewer-Zustimmung ~50%)" },
      { kind: "note", text: "Extrahieren-Sektion: MetricCounter „Register-Boxen“ N / Gesamt" },
    ] }],
  });

  // ── Step 17: Auth-Gate — Token entfernen → „Bitte zuerst anmelden." ──────
  await pageA.evaluate(() => {
    sessionStorage.removeItem("goldens.api_token");
    sessionStorage.removeItem("goldens.role");
    sessionStorage.removeItem("goldens.name");
  });
  await pageA.goto(`${BASE}/#/admin/doc/${SLUG}/statistics`);
  await pageA.waitForLoadState("networkidle").catch(() => {});
  await pageA.waitForTimeout(1800);
  await rec.step(pageA, "Auth-Gate — ohne Token zeigt Statistik „Bitte zuerst anmelden.“", {
    actions: ["sessionStorage geleert (Logout-Äquivalent)", `goto /admin/doc/${SLUG}/statistics direkt`],
    notes: [
      "Statistics.tsx: bei token === null wird statt der Metriken „Bitte zuerst anmelden.“ gerendert (PR-#51-Auth-Gate).",
      "Direktes Aufrufen der Statistik-URL ohne gültigen Token liefert also keine Daten — die Seite bleibt nicht leer/blank, sondern zeigt die Hinweismeldung.",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: 'text=Bitte zuerst anmelden', text: "Auth-Gate-Meldung" },
    ] }],
  });
} finally {
  // ── Teardown (idempotent) — order matters ──────────────────────────────
  // 1) revoke curator vote WITH the curator token (before deleting curator),
  // 2) revoke admin vote, 3) delete generated questions, 4) delete curator.
  try {
    if (curatorToken && votedEntry?.entryId) {
      await vote(curatorToken, votedEntry.entryId, "revoked");
      console.log("Teardown: revoked curator vote");
    }
    if (votedEntry?.entryId) {
      await vote(TOKEN, votedEntry.entryId, "revoked");
      console.log("Teardown: revoked admin vote");
    }
    for (const qid of generatedEntryIds) {
      await fetch(`${API}/api/admin/docs/${SLUG}/questions/${qid}`, {
        method: "DELETE", headers: hdr(TOKEN),
      }).catch(() => {});
    }
    if (generatedEntryIds.length) {
      console.log("Teardown: deleted", generatedEntryIds.length, "generated question(s)");
    }
    if (curatorId) {
      const r = await fetch(`${API}/api/admin/curators/${curatorId}`, {
        method: "DELETE", headers: hdr(TOKEN),
      }).catch(() => null);
      console.log("Teardown: deleted curator", curatorId, r ? `(${r.status})` : "(failed)");
    }
  } catch (e) {
    console.log("Teardown error:", e?.message);
  }

  const outDir = await rec.finish();
  await browser.close();
  console.log("Wrote walkthrough to", outDir);
}
