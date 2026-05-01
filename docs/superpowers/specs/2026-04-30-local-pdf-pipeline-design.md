# Local PDF Pipeline — Design Spec

**Phase:** A.0 — Local PDF Pipeline (sits *upstream* of A.1-A.7)
**Date:** 2026-04-30
**Status:** Spec — pending user review, then `superpowers:writing-plans` for the implementation plan.

## 1. Goal

Build an opinionated, local, free-tools assistive desktop-web tool that takes a raw PDF and produces canonical `SourceElement` JSON (the same shape `analyze.json` from Microsoft Document Intelligence produces today). The output drops into the existing goldens system without any consumer-side rewiring.

The tool guides the user through:
1. Auto-detecting layout (chapters, paragraphs, tables, figures) as bounding boxes
2. Manually correcting / merging / categorizing those boxes
3. Running extraction on the corrected segmentation
4. Reviewing extracted HTML side-by-side with the source PDF, fixing inline
5. Exporting the result as canonical `SourceElement` JSON

This is the alternative to relying on Microsoft Document Intelligence's analyze.json — which is a black box and not always reliable on technical PDFs. The UI puts the human in the loop where the auto-pipeline fails.

## 2. Decisions Log

| ID | Topic | Decision | Reasoning |
|----|-------|----------|-----------|
| D1 | Scope and time horizon | **Ongoing internal tool** (not throwaway, not multi-user yet) | User will process every new PDF through this; needs persistence + polish but no auth complexity beyond A-Plus.1 |
| D2 | Output format | **Canonical `SourceElement` JSON** (PR #12 schema) | Drop-in replacement for Microsoft DI's `analyze.json`; goldens system needs zero changes downstream |
| D3 | Deployment shape | **Reuse A-Plus stack:** FastAPI + React/Vite + Tailwind + TanStack Query | Same dev workflow, copy boilerplate from `goldens/api/` and `frontend/`, deployment via `query-eval segment serve` |
| D4 | Layout detection engine | **DocLayout-YOLO** (opendatalab) | Highest mAP on DocLayNet (79.7), real-time YOLOv10 backbone, what MinerU itself uses internally; AGPL-3.0 acceptable |
| D5 | Extraction engine | **MinerU 3** (with MinerU2.5-Pro VLM, 1.2B params) | Open-weights leader on OmniDocBench; cross-page table merging + sliding-window long-doc support |
| D6 | OCR | **Skip in this phase** | Out of scope; scanned docs flagged as `needs-ocr` in status |
| D7 | Workflow shape | One doc at a time; user goes raw → segmenting → extracting → done explicitly | No auto-progression; user controls when to "Run extraction" since MinerU is the slow step |
| D8 | Persistence | Per-PDF sidecar JSON files in `data/raw-pdfs/<slug>/` | Simple, crash-safe, no SQLite |
| D9 | Save model | **Auto-save** to draft sidecar after every edit (debounce 300ms) | No "did I save?" anxiety |
| D10 | Module location | `features/pipelines/local-pdf/` (sibling to `pipelines/microsoft/`) | Matches Phase A.7's pipeline-agnostic structure |
| D11 | Phase placement | **A.0** — upstream of A.1-A.7 | Conceptually pre-goldens: produces source elements that goldens consumes |
| D12 | Segmenter editor layout | **2-pane** with PDF dominant (~75%) + properties sidebar (~25%) + collapsible page-list | Maximum visual real-estate for the page; properties always visible |
| D13 | HTML editor | **WYSIWYG (Tiptap) by default** with raw-HTML escape hatch (CodeMirror) | Rich-text for typos and structure; raw-HTML for surgical fixes |
| D14 | Box-kind hotkeys | Single-letter: h=heading, p=paragraph, t=table, f=figure, c=caption, q=formula, l=list-item, x=discard (8 hotkeys for 8 kinds) | Power-user efficiency for dense docs |
| D15 | Box-color scheme | Heading=blue, paragraph=green, table=orange, figure=teal, caption=purple, formula=pink, list-item=indigo | Visual category at a glance, consistent between PDF view and HTML view |
| D16 | Click-to-link | Click HTML element → highlights + scrolls source box on PDF; hover box → flash matching HTML element | "Side-by-side" is the differentiator — synchronization is the feature |
| D17 | Re-extract scope | "Re-extract this region" right-click on element → MinerU runs only on that bbox | Local fix without re-processing whole doc |
| D18 | Concurrency | Single-user; fcntl-lock per file (matches A.3 storage pattern) | No multi-user complexity in this phase |
| D19 | Undo/redo | In-session only (no persistent history) | Simpler; auto-save is the safety net |

## 3. Architecture

```
                     +----------------------------+
                     |    React + Vite frontend   |
                     |  (Tiptap, PDF.js, TanStack)|
                     +---------+-----+------------+
                               |     |
                          REST | SSE | (NDJSON streaming for extract progress)
                               |     |
                     +---------v-----v------------+
                     |     FastAPI backend         |
                     |  (X-Auth-Token middleware)  |
                     +-+---------+----------+------+
                       |         |          |
                       v         v          v
            +----------+--+ +----+----+ +---+--------+
            | DocLayout-  | | MinerU 3| | sidecar    |
            | YOLO worker | | worker  | | files      |
            | (Python)    | | (Python)| | (JSON)     |
            +-------------+ +---------+ +------------+
                                            |
                                            v
                               data/raw-pdfs/<slug>/
                                  ├── source.pdf
                                  ├── yolo.json
                                  ├── segments.json    (user-edited)
                                  ├── mineru-out.json
                                  ├── html.html        (user-edited)
                                  └── sourceelements.json (final export)
```

### Component responsibilities

- **React frontend**: 3 main routes (`/inbox`, `/doc/<slug>/segment`, `/doc/<slug>/extract`); PDF rendering via PDF.js; box manipulation via DOM overlays; rich-text via Tiptap; raw HTML via CodeMirror.
- **FastAPI backend**: thin REST layer mirroring A-Plus.1 patterns. Endpoints in §5.
- **DocLayout-YOLO worker**: Python module wrapping the pre-trained `doclayout_yolo_docstructbench_imgsz1024.pt` weights. Sync invocation per-doc; results persisted to `yolo.json`.
- **MinerU 3 worker**: Python module wrapping MinerU 3 CLI; supports full-doc and per-bbox re-extract. Streams progress via NDJSON to the frontend.
- **Sidecar files**: each PDF lives in `data/raw-pdfs/<slug>/` with a deterministic file structure. fcntl-locked.

## 4. Data Flow

```
Raw PDF dropped into data/raw-pdfs/         status: raw
       |
       | user clicks "start →" in inbox
       v
DocLayout-YOLO runs → yolo.json             status: segmenting
       |
       | user reviews + edits boxes in /doc/<slug>/segment
       | (auto-saves to segments.json on every edit)
       v
User clicks "Run extraction →"
       |
       | MinerU 3 runs on segments.json     status: extracting
       v
MinerU 3 outputs → mineru-out.json
       |
       | user reviews + edits HTML in /doc/<slug>/extract
       | (auto-saves to html.html on every edit)
       v
User clicks "Export →"
       |
       | converter writes sourceelements.json
       v
data/raw-pdfs/<slug>/sourceelements.json    status: done
```

## 5. API Endpoints (FastAPI)

Following A-Plus.1 patterns (X-Auth-Token, 127.0.0.1 bind, no versioning prefix).

```
GET  /api/docs                                  → inbox listing (slug, filename, pages, status, last_touched)
POST /api/docs                                  → upload PDF; copies to data/raw-pdfs/<slug>/, status=raw
GET  /api/docs/{slug}                           → doc metadata + status
POST /api/docs/{slug}/segment                   → run DocLayout-YOLO; streams progress via NDJSON; persists yolo.json
GET  /api/docs/{slug}/segments                  → current segments.json (auto-edited)
PUT  /api/docs/{slug}/segments/{box_id}         → update a single box (kind, bbox)
POST /api/docs/{slug}/segments/merge            → merge box IDs in document order
POST /api/docs/{slug}/segments/split            → split a box at a given y-coordinate
DELETE /api/docs/{slug}/segments/{box_id}       → delete (effectively kind=discard)
POST /api/docs/{slug}/extract                   → run MinerU 3 on segments.json; NDJSON streaming progress
POST /api/docs/{slug}/extract/region            → re-extract single bbox region
GET  /api/docs/{slug}/html                      → current html.html (user-editable)
PUT  /api/docs/{slug}/html                      → save edited HTML (called by Tiptap on debounce)
POST /api/docs/{slug}/export                    → run sourceelements converter; writes sourceelements.json; status=done
GET  /api/docs/{slug}/source.pdf                → serve raw PDF (for PDF.js)
GET  /api/health                                → health check (no auth)
```

## 6. UI Screens

Three React routes, design validated visually in brainstorming session.

### 6.1 Inbox (`/inbox`)

Table of PDFs in `data/raw-pdfs/`. Columns: filename, pages, status (badge), boxes count, last touched, action (start / resume / view).

- **+ Add PDF** button → file picker → POST /api/docs (copies file in, creates slug dir)
- **Search input** + status filter
- **Drop-zone hint** at the bottom — also accepts file-system drops directly into the watched folder

### 6.2 Segmenter (`/doc/<slug>/segment`)

2-pane: PDF dominant (~75%), properties + actions sidebar (~25%), collapsible page-list behind a hamburger button.

**PDF pane:**
- PDF.js renders the page; box overlays in absolute-positioned divs
- Click box → select (red outline + corner handles)
- Drag corners/edges → resize
- Drag center → reposition
- Shift-click multiple boxes → multi-select
- Right-click box → context menu (split here, copy bbox, jump to box N)

**Sidebar:**
- Selected box: kind dropdown (8 values), bbox readout, confidence score
- Actions: Merge with next (m), Split at cursor (/), New box (n), Delete (⌫)
- Page status: boxes detected, edited count, avg confidence
- "Run extraction →" button (primary blue) — sends every non-discard box in `segments.json` to MinerU; only enabled when status allows it

**Hotkeys:**
- h/p/t/f/c/q/l/x → assign kind to selected box (or boxes)
- m → merge selected
- / → split at cursor
- arrow keys → navigate boxes in reading order
- ? → show shortcut overlay

**Visual signals:**
- Box outline + label color matches kind (heading=blue, paragraph=green, table=orange, figure=teal, caption=purple, formula=pink, list-item=indigo)
- Low-confidence boxes (< 0.7) flash yellow until reviewed
- Confidence shown on each box label

### 6.3 Extraction view (`/doc/<slug>/extract`)

2-pane equal split: PDF (left, read-only reference with the user's blessed boxes) + editable HTML (right).

**HTML editor:**
- WYSIWYG by default (Tiptap-based) — toolbar with B/I/H1/H2/¶ shortcuts
- "view: WYSIWYG ▾" toggle → switches to raw HTML mode (CodeMirror)
- Each element has data-source-box="<box_id>" for click-to-link
- Color-coded left-border per kind (matches segmenter color scheme)
- Auto-save 300ms-debounced to `/api/docs/<slug>/html`

**Cross-pane interactions:**
- Click element on right → source box on left highlights red + scrolls into view
- Hover box on left → matching element on right flashes briefly
- Synchronized scrolling (toggleable): scrolling PDF auto-scrolls HTML to visible region

**Quality assists:**
- Low-confidence elements get a yellow warning banner (visible until edited or explicitly accepted)
- Right-click element → "Re-extract this region" (calls `/api/docs/<slug>/extract/region`)

## 7. Persistence Model

```
data/raw-pdfs/<slug>/
  ├── source.pdf                # original (read-only after upload)
  ├── meta.json                 # filename, pages, status, last_touched
  ├── yolo.json                 # raw DocLayout-YOLO output (immutable)
  ├── segments.json             # user-edited boxes (auto-saved)
  ├── mineru-out.json           # raw MinerU 3 output (immutable per-extract-run)
  ├── html.html                 # user-edited HTML (auto-saved)
  └── sourceelements.json       # final canonical output (only after Export)
```

- All sidecar files use **fcntl LOCK_EX** for writes (matches `goldens/storage/` pattern from A.3)
- `meta.json.status` transitions: `raw → segmenting → extracting → done`. User actions trigger transitions, never auto.
- `yolo.json` and `mineru-out.json` are kept as immutable "what the engine said" — useful for re-running with different segmentation or for auditing
- `segments.json` and `html.html` are the user's authoritative edits

## 8. SourceElement Output Format

Final `sourceelements.json` conforms to the existing `SourceElement` schema (PR #12). The converter runs at Export time, walking the user-edited HTML + segments and emitting one `SourceElement` per blessed segment.

Expected shape (matches existing pipelines/microsoft/ output):

```json
{
  "doc_slug": "bam-tragkorb-2024",
  "source_pipeline": "local-pdf",
  "elements": [
    {
      "kind": "heading",
      "page": 2,
      "bbox": [140, 80, 380, 110],
      "text": "3 Prüfverfahren",
      "level": 1
    },
    {
      "kind": "paragraph",
      "page": 2,
      "bbox": [140, 220, 380, 80],
      "text": "Die Prüfung des Tragkorbs erfolgt nach DIN EN 12100 ..."
    }
  ]
}
```

The `source_pipeline: "local-pdf"` field distinguishes from `"microsoft"` outputs so downstream evaluators can filter or compare side-by-side.

## 9. Code Reuse from A-Plus

| From | What | Where it goes |
|------|------|---------------|
| `features/goldens/api/auth.py` | X-Auth-Token middleware | `features/pipelines/local-pdf/api/auth.py` (verbatim) |
| `features/goldens/api/identity.py` | Identity loader | reused as-is |
| `features/goldens/storage/log.py` | fcntl LOCK_EX wrapper | imported, not copied |
| `frontend/src/api/client.ts` | API client + 401 interceptor | copied + adapted (different base URL) |
| `frontend/src/auth/` | Auth gate + login | reused verbatim |
| `frontend/src/components/TopBar.tsx` | TopBar + slug context | adapted for doc-context |
| Plan structure / TDD pattern | superpowers:subagent-driven-development | reused for implementation |

## 10. Out of Scope (this phase)

- **Multi-user / Doktor Müller review.** Single-user only; UI assumes one keyboard.
- **OCR for scanned PDFs.** Flag as `needs-ocr`, defer to a follow-up phase.
- **Persistent undo/redo across sessions.** In-session only; auto-save is the safety net.
- **Reading-order recovery / re-ordering.** Trust DocLayout-YOLO's reading order; expose drag-reorder only as a follow-up if needed.
- **Drag-onto-drop merge gesture.** The shift-click + m hotkey is sufficient.
- **Mobile / tablet support.** Desktop-only.
- **Export back to MinerU's native Markdown.** SourceElement is the canonical output; if Markdown is needed later, it's a separate converter.

## 11. Known Follow-ups

- **OCR step** — Tesseract or PaddleOCR — fired before DocLayout-YOLO when status=`needs-ocr` is set
- **Cross-doc consistency review** — UI to compare same-kind elements across multiple processed docs (e.g., "all the headings extracted from norm documents")
- **DocLayout-YOLO retraining** — once we have N corrected segmentations, optionally fine-tune the model on our domain
- **Pipeline parity report** — for docs we've processed both with Microsoft DI and local-pdf, diff the SourceElements and surface inconsistencies (related to Phase E `span_match`)
- **Phase A.7 chunk-match doesn't currently know about `source_pipeline` field** — need a small read-side adjustment when this lands

## 12. References

- **MinerU 3 release**: https://newreleases.io/project/github/opendatalab/MinerU/release/mineru-3.0.0-released
- **MinerU2.5 paper**: https://arxiv.org/abs/2509.22186
- **DocLayout-YOLO repo**: https://github.com/opendatalab/DocLayout-YOLO
- **OmniDocBench (CVPR 2025)**: https://arxiv.org/abs/2412.07626
- **PR #12 SourceElement schema** (this repo)
- **A-Plus.1 backend spec** for auth + serve-pattern reference
- **A-Plus.2 frontend spec** for SPA pattern reference
