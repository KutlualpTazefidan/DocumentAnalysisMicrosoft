// Walkthrough recording: vergleich-microsoft-search
// Tour the full Vergleich (Comparison) pipeline against a Microsoft
// (Azure) knowledge source: pick a curated question on the left, choose a
// pre-indexed Microsoft source on the right, run Suchen to retrieve chunks,
// review + toggle chunk selection, generate an answer from the kept chunks,
// then Vergleichen the answer against the local reference answer (BM25 /
// Cosine ScoreBars) and read the per-chunk eval metrics + the
// "Ähnliche Fragen im Dokument" block.
//
// IMPORTANT: every pipeline result in Comparison.tsx lives in React useState
// (selectedEntry, searchChunks, chunkSelection, answerText, compareResult,
// showChunkAnalytics). A page.reload() would wipe all of it — so after the
// question is selected this is ONE continuous click sequence, no reloads.
// API + reload is only used in setup (before selecting) and cleanup.

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8001";

// ── Setup helpers (backend reads, mirror synthese-edit-answer's shape) ──────

// /questions returns a map box_id → Question[]; flatten + keep box_id.
async function getQuestions() {
  const r = await fetch(`${API}/api/admin/docs/${SLUG}/questions`, {
    headers: { "X-Auth-Token": TOKEN },
  }).catch(() => null);
  const j = r && r.ok ? await r.json() : {};
  const all = [];
  if (Array.isArray(j)) all.push(...j);
  else for (const [boxId, qs] of Object.entries(j)) {
    if (Array.isArray(qs)) qs.forEach(q => all.push({ ...q, box_id: q.box_id ?? boxId }));
  }
  return all;
}

// Pick a fully-curated question (has a reference answer). The Vergleichen
// button stays disabled without one, so this is the question we must drive.
function pickAnsweredQuestion(qs) {
  return qs.find(q => q.answer && String(q.answer).trim().length > 0) ?? qs[0] ?? null;
}

// box_id like "p3-..." → page 3; questionsOnPage filters by `p{page}-`.
function pageOfBox(boxId) {
  const m = String(boxId ?? "").match(/^p(\d+)-/);
  return m ? parseInt(m[1], 10) : 1;
}

// Prefer a pre-indexed Microsoft source — the only branch that can complete
// in a single recording (uploading + Azure indexing takes 5–15 min).
async function getIndexedSource() {
  const r = await fetch(`${API}/api/admin/pipelines/microsoft/sources`, {
    headers: { "X-Auth-Token": TOKEN },
  }).catch(() => null);
  const list = r && r.ok ? await r.json() : [];
  const arr = Array.isArray(list) ? list : [];
  return arr.find(s => s.state === "indexed") ?? arr[0] ?? null;
}

const target = await getQuestions().then(pickAnsweredQuestion);
const ENTRY = target?.entry_id ?? null;
const TARGET_PAGE = pageOfBox(target?.box_id);
const indexedSource = await getIndexedSource();
const SOURCE_SLUG = indexedSource?.slug ?? null;
console.log("Target question:", ENTRY, "box:", target?.box_id, "page:", TARGET_PAGE);
console.log("Microsoft source:", SOURCE_SLUG, "state:", indexedSource?.state);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();

// Accept the window.confirm dialogs the upload/delete handlers raise (we do
// not delete here, but register defensively before any source mutation).
page.on("dialog", d => d.accept().catch(() => {}));

await page.goto(`${BASE}/`);
await page.evaluate(({ t, slug, pg }) => {
  sessionStorage.setItem("goldens.api_token", t);
  sessionStorage.setItem("goldens.role", "admin");
  sessionStorage.setItem("goldens.name", "probe");
  sessionStorage.setItem("goldens.tenant_name", "Fachbereich 3.3");
  // Mount the Comparison route already on the target question's page so it
  // appears in the visible questionsOnPage list (useState(() => loadCurrentPage)).
  localStorage.setItem(`doc.currentPage.${slug}`, String(pg));
}, { t: TOKEN, slug: SLUG, pg: TARGET_PAGE });

const rec = new Recorder("vergleich-microsoft-search", BASE);

await page.goto(`${BASE}/#/admin/doc/${SLUG}/compare`);
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(2000);

// Step 1: Four-pane Vergleich layout.
await rec.step(page, "Vergleich-Tab: Vier-Pane-Layout (Fragen · Detail · Pipeline · Steuerung)", {
  actions: [`goto /admin/doc/${SLUG}/compare`],
  notes: [
    "Vier Spalten: links die Fragen dieser Seite (300px), daneben Detail + „Ähnliche Fragen“ (flexibel), dann der Pipeline-Runner (440px), rechts die Steuerleiste (280px) mit Seiten-Navigation, Pipeline-Auswahl und Microsoft-Wissensquellen.",
    "Helle BAM-Oberflächen nach dem Re-Skin; aktive Akzente in BAM-Cyan (#00aff0), die Referenz-Antwort-Karte in Emerald, die Vergleichen-CTA in Emerald.",
    "Rechts ist „microsoft“ als Pipeline vorgewählt — deshalb zeigt die Steuerleiste das Wissensquellen-Panel.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: '[data-testid="compare-left"]', text: "Fragen-Liste (Seite)" },
    { kind: "highlight", selector: '[data-testid="compare-middle"]', text: "Pipeline-Runner" },
    { kind: "highlight", selector: '[data-testid="compare-sidebar"]', text: "Steuerleiste (Pipeline + Quellen)" },
  ] }],
});

// Step 2: Select the curated question (has reference answer) on the left.
const questionSel = ENTRY ? `[data-testid="compare-question-${ENTRY}"]` : '[data-testid^="compare-question-"]';
await page.locator(questionSel).first().click().catch(() => {});
await page.waitForTimeout(800);
await rec.step(page, "Frage links wählen → Detail + Referenz-Antwort + ähnliche Fragen laden", {
  actions: [`click ${questionSel}`],
  notes: [
    "Die gewählte Frage bekommt links den BAM-Cyan-Akzentstreifen (border-l-4 border-l-bam-cyan).",
    "Im Detail-Pane erscheinen: „Ausgewählte Frage“-Karte, die lokale Referenz-Antwort (Emerald-Karte) und darunter „Ähnliche Fragen im Dokument“.",
    "Ähnliche Fragen laden via GET /api/admin/docs/{slug}/questions/{entry_id}/similar?k=5 — BM25 (+ Cosine, falls Embedder konfiguriert).",
    "Nur eine Frage MIT Referenz-Antwort kann am Ende verglichen werden — die Vergleichen-CTA bleibt sonst deaktiviert.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: questionSel, text: "Gewählte (kuratierte) Frage" },
    { kind: "highlight", selector: '[data-testid="compare-detail"]', text: "Detail + Referenz + ähnliche Fragen" },
  ] }],
});

// Step 3: Pick the pre-indexed Microsoft source in the right panel.
const sourceSel = SOURCE_SLUG ? `[data-testid="ms-source-${SOURCE_SLUG}"]` : '[data-testid^="ms-source-"]';
await page.locator(sourceSel).first().click().catch(() => {});
await page.waitForTimeout(600);
await rec.step(page, "Microsoft-Wissensquelle wählen (rechts) — bevorzugt „indexed“", {
  actions: [`click ${sourceSel}`],
  notes: [
    "Jeder Quellen-Eintrag zeigt Dateinamen, Seitenzahl und einen State-Chip: neu / 1·4 / 2·4 / 3·4 / ✓ (indexed) / ✗.",
    "Nur eine „✓ indexed“-Quelle ist sofort durchsuchbar — frisch hochgeladene PDFs durchlaufen erst Azure-Analyse + Embeddings + Indexierung (5–15 min), deshalb nehmen wir hier eine vorindexierte Quelle.",
    "Gewählte Quelle bekommt den BAM-Cyan-Rahmen + rowsel-Hintergrund; der „🔍 Suchen“-Button ist erst jetzt (Frage + Quelle gewählt) aktiv.",
    "▲ PDF hochladen würde eine neue Quelle anlegen — kostenpflichtige Azure-Schritte, daher mit Bestätigungsdialog. Hier nicht ausgelöst, um den Doku-Stand sauber zu halten.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: sourceSel, text: "Gewählte Microsoft-Quelle" },
    { kind: "highlight", selector: '[data-testid="ms-upload"]', text: "Upload (hier nicht ausgelöst)" },
  ] }],
});

// Step 4: Pipeline selector + middle-pane state before searching.
await rec.step(page, "Pipeline = microsoft, Frage + Quelle gesetzt → „🔍 Suchen“ aktiv", {
  actions: ["inspect [data-testid=\"compare-pipeline-select\"]", "inspect [data-testid=\"compare-search\"]"],
  notes: [
    "Der Pipeline-Selektor (rechts) steht auf „microsoft“. Ein Wechsel würde searchChunks / answerText / compareResult zurücksetzen — sauberer Neustart pro Pipeline.",
    "Der Pipeline-Runner zeigt die Frage und die Referenz-Antwort als Read-only-Karte zur Orientierung während des Laufs.",
    "„🔍 Suchen“ ist deaktiviert (bg-slate-300), solange keine Frage gewählt ist, die Suche läuft, oder bei microsoft keine Quelle gewählt ist — jetzt ist es aktiv.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: '[data-testid="compare-pipeline-select"]', text: "Pipeline = microsoft" },
    { kind: "highlight", selector: '[data-testid="compare-search"]', text: "🔍 Suchen (aktiv)" },
  ] }],
});

// Step 5: Run search — LIVE click (state is React-only; no reload allowed).
await page.locator('[data-testid="compare-search"]').click().catch(() => {});
// Wait for the first chunk card to render rather than a fixed sleep, so the
// screenshot captures whatever came back even if Azure is slow/unconfigured.
await page.waitForSelector('[data-testid^="chunk-toggle-"]', { timeout: 12000 }).catch(() => {});
await page.waitForTimeout(800);
await rec.step(page, "„🔍 Suchen“ klicken → Chunks aus der Microsoft-Quelle", {
  actions: ['click [data-testid="compare-search"]'],
  notes: [
    "POST /api/admin/pipelines/microsoft/search mit {question, source, top_k: 5} — Azure AI Search liefert die Chunks.",
    "Jeder Chunk wird zur auswählbaren, aufklappbaren Karte: Checkbox + Titel/chunk_id + „Treffer {score}“ (Retrieval-Score von Azure) + Aufklapp-Pfeil. Beim Suchen sind alle Chunks angehakt.",
    "Toast: „{N} Chunks von microsoft“. Parallel scored compare-bulk jeden Chunk gegen den lokalen Quell-Box-Text (boxRelevance) — best-effort, ohne UI-Block.",
    "Die Analyse-Bars bleiben zunächst verborgen (showChunkAnalytics=false) und erscheinen erst nach „Vergleichen“.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: '[data-testid^="chunk-checkbox-"]', text: "Chunk-Auswahl (alle vorab an)" },
    { kind: "note", text: "Section-Kopf zählt: „{N} Chunk(s) · {N} ausgewählt“" },
  ] }],
});

// Step 6: Expand a couple of chunks and deselect one.
await page.locator('[data-testid^="chunk-toggle-"]').first().click().catch(() => {});
await page.locator('[data-testid^="chunk-toggle-"]').nth(1).click().catch(() => {});
await page.waitForTimeout(400);
// Uncheck the last chunk so the "ausgewählt" counter visibly drops.
const checkboxes = page.locator('[data-testid^="chunk-checkbox-"]');
const cbCount = await checkboxes.count().catch(() => 0);
if (cbCount > 1) {
  await checkboxes.last().click().catch(() => {});
}
await page.waitForTimeout(400);
await rec.step(page, "Chunks aufklappen + einen abwählen → Zähler aktualisiert live", {
  actions: [
    'click [data-testid^="chunk-toggle-"] (erste zwei)',
    cbCount > 1 ? 'click [data-testid^="chunk-checkbox-"] (letzte → abwählen)' : "—",
  ],
  notes: [
    "Aufklappen ist lokaler State (setOpen) — der volle Chunk-Text wird sichtbar; in zu der Antwort beitragenden Karten kommen später Analyse-Bars hinzu.",
    "Abhaken eines Chunks aktualisiert sofort den „{count} ausgewählt“-Zähler im Section-Kopf; nur angehakte Chunks gehen in die Antwort.",
    "Bei mehr als einem Chunk erscheinen „Alle“ / „Keine“ (chunks-select-all / chunks-select-none) für Batch-Auswahl.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: '[data-testid="chunks-select-none"]', text: "„Keine“ — Batch-Abwahl" },
    { kind: "note", text: "„{N} ausgewählt“ sinkt nach dem Abwählen" },
  ] }],
});

// Step 7: Generate the answer from the kept chunks — LIVE click.
await page.locator('[data-testid="compare-answer"]').click().catch(() => {});
await page.waitForTimeout(2500);
await rec.step(page, "„💬 Antwort generieren“ → LLM-Antwort aus gewählten Chunks", {
  actions: ['click [data-testid="compare-answer"]'],
  notes: [
    "Button-Text: „💬 Antwort generieren ({N} Chunks)“ — deaktiviert, wenn kein Chunk angehakt ist; nach erfolgreichem Lauf „↻ Nochmal antworten“.",
    "POST /api/admin/pipelines/microsoft/answer mit {question, chunks} — die Antwort erscheint als weiße Karte unter den Chunks. Toast: „Antwort generiert ({N} Chunks verwendet)“.",
    "Anschließend scored compare-bulk jeden gewählten Chunk gegen die neue Antwort (chunkRelevance) → speist die „Beitrag zur Antwort“-Bars.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: '[data-testid="compare-answer"]', text: "Antwort generieren / Nochmal antworten" },
    { kind: "note", text: "microsoft — Antwort (weiße Karte) unter den Chunks" },
  ] }],
});

// Step 8: Compare generated answer vs. reference — LIVE click.
await page.locator('[data-testid="compare-compare"]').click().catch(() => {});
await page.waitForTimeout(2000);
await rec.step(page, "„▶ Vergleichen“ → Ähnlichkeit Referenz ↔ microsoft (BM25 / Cosine)", {
  actions: ['click [data-testid="compare-compare"]'],
  notes: [
    "Nur aktiv, wenn Antwort UND Referenz-Antwort existieren (sonst grau).",
    "POST /api/admin/compare mit {reference, candidate} → {bm25, cosine, embedder}.",
    "Die Ergebnis-Karte „Ähnlichkeit Referenz ↔ microsoft“ zeigt zwei ScoreBars: „Sinngleichheit (Cosine)“ und „Wortlaut (BM25)“. Bar-Farbe: ≥ 0.8 Emerald, ≥ 0.5 Amber, < 0.5 Rot.",
    "Ohne Azure-Embeddings steht Cosine = 0 mit Hinweis „Cosine = 0 weil Azure-Embeddings nicht konfiguriert sind“.",
    "Der Klick setzt showChunkAnalytics=true → die Per-Chunk-Analyse-Bars werden eingeblendet (siehe nächster Schritt).",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: '[data-testid="compare-compare"]', text: "▶ Vergleichen" },
    { kind: "note", text: "ScoreBars: Sinngleichheit (Cosine) + Wortlaut (BM25)" },
  ] }],
});

// Step 9: Per-chunk eval metrics now visible after Vergleichen.
// Chunk 0 is already expanded (from step 6) and its analytics are live —
// setShowChunkAnalytics(true) fired on the Vergleichen click in step 8.
// No toggle here: clicking chunk-toggle now would COLLAPSE the open card.
await rec.step(page, "Per-Chunk-Metriken nach „Vergleichen“: Vs lokaler Chunk + Beitrag zur Antwort", {
  actions: ['inspect [data-testid^="chunk-toggle-"] (erste, weiterhin aufgeklappte Karte)'],
  notes: [
    "Analyse-Bars rendern nur, wenn showChunkAnalytics=true UND der Chunk angehakt ist UND boxRelevance vorliegt.",
    "„Vs lokaler Chunk“: BM25 (+ Cosine, falls Embedder) des MS-Chunks gegen den lokalen Quell-Box-Text.",
    "„Beitrag zur Antwort“: BM25 (+ Cosine) des Chunks gegen die generierte Antwort.",
    "Längen-Bars vergleichen MS-Chunk-Länge (blau) mit lokaler Box-Länge (emerald): „2.5× MS“ / „1.3× lokal“ / „≈ gleich“. Einen Chunk abwählen blendet seine Analyse aus (Cache, kein Re-Fetch).",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: '[data-testid^="chunk-toggle-"]', text: "Aufgeklappter Chunk mit Analyse-Bars" },
    { kind: "note", text: "Vs lokaler Chunk · Beitrag zur Antwort · Längen-Verhältnis" },
  ] }],
});

// Step 10: Similar-questions block in the detail pane.
await rec.step(page, "„Ähnliche Fragen im Dokument“ — gerankte Treffer im Detail-Pane", {
  actions: ['inspect [data-testid^="similar-card-"]'],
  notes: [
    "Geladen aus GET /api/admin/docs/{slug}/questions/{entry_id}/similar?k=5.",
    "Jede Karte: Rang-Ribbon (#1, #2 …), links Frage-Text + box_id + BM25/Cosine-ScoreBars, rechts ein Chunk-Auszug aus der Quell-Box jener Frage.",
    "Ribbon-Farbe nach kombiniertem Score (0.4·BM25 + 0.6·Cosine bei Embedder, sonst BM25): ≥ 0.7 Emerald, ≥ 0.4 Amber, < 0.4 Slate.",
    "Hilft, verwandte Q&A anderswo im Dokument zu finden, die den aktuellen Vergleich informieren können.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: '[data-testid^="similar-card-"]', text: "Ähnliche-Fragen-Karte (Rang + Scores + Chunk)" },
  ] }],
});

// Step 11: Page navigation + lock/unlock in the sidebar.
await page.locator('[data-testid="compare-page-grid-toggle"]').click().catch(() => {});
await page.waitForTimeout(500);
await rec.step(page, "Seiten-Navigation + Sperren in der Steuerleiste", {
  actions: [
    'click [data-testid="compare-page-grid-toggle"]',
    "(verfügbar: compare-page-prev / compare-page-next / compare-page-btn-{p} / compare-page-lock)",
  ],
  notes: [
    "◀ / ▶ (compare-page-prev / -next) blättern; der mittlere Button öffnet das Seiten-Raster (compare-page-grid-toggle).",
    "Im Raster: rote Buttons = keine Fragen, grüne = mit Fragen; die aktive Seite trägt einen BAM-Cyan-Ring. compare-page-btn-{p} springt direkt zu Seite p.",
    "Seitenwechsel setzt selectedEntry, searchChunks, answerText, compareResult und die Analyse zurück — sauberer Start je Seite (kein Reload nötig, alles client-seitig).",
    "compare-page-lock schaltet die Freigabe der aktuellen Seite um: „🔒 Diese Seite sperren“ ↔ „🔓 Diese Seite entsperren“ (gesperrt = BAM-Cyan-Rahmen + rowsel). Gleicher localStorage-Key wie Extract/Synthese.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: '[data-testid="compare-page-grid-toggle"]', text: "Seiten-Raster (offen)" },
    { kind: "highlight", selector: '[data-testid="compare-page-lock"]', text: "🔒 Diese Seite sperren" },
  ] }],
});

// Cleanup: close the page grid. No backend state was created (no upload,
// no source delete; search/answer/compare are ephemeral React state), so
// there is nothing to revoke — re-runs stay pristine.
await page.locator('[data-testid="compare-page-grid-toggle"]').click().catch(() => {});

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);
