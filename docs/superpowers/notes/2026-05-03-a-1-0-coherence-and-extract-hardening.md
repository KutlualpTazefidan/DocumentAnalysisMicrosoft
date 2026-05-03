# A.1.0 — Coherence + Roles + Extract-Pipeline-Hardening

> **Status:** PR open against `main`. Branch `test/coherence-with-fixes`.
> **Date:** 2026-05-03
> **Scope:** ~40 commits combining the architectural A.1.0 spec with extensive
> hardening of the MinerU-driven extract pipeline.

This branch grew out of the A.1.0 design ([spec](../specs/2026-05-01-coherence-and-roles-design.md)) but expanded as testing surfaced concrete defects in the extract pipeline. Both bodies of work ship together.

## Part 1 — A.1.0 baseline (architectural cleanup)

Decisions C1–C16 from the spec, implemented:

- **Role-prefixed routes**: `/admin/*` and `/curate/*` on the SPA; `/api/admin/*` and `/api/curate/*` on the backend. Resolves the `/api/docs/<slug>/elements` 404 from earlier testing.
- **Two role-based shells**: navy admin shell, green curator shell, shared `/login`.
- **Simple-token auth**: admin token from `GOLDENS_API_TOKEN`, curator tokens stored in `data/curators.json` with admin issue/revoke UI.
- **Component migration**: `frontend/src/local-pdf/*` → `frontend/src/admin/*`; legacy URL redirects retained.
- **UI library bump**: lucide-react + framer-motion + Radix primitives (Dialog, Dropdown, Toast).
- **Backend refactor**: `local-pdf` API split into admin and curate routers with role-aware middleware.

## Part 2 — Extract pipeline hardening (the "with-fixes" part)

The unified VLM-driven extract pipeline (segment + extract in one MinerU pass) replaced the legacy YOLO+per-bbox approach. Real-world testing on a German technical PDF surfaced a long list of edge cases that this branch addresses commit-by-commit:

### Box-level decomposition
- **List blocks** (`type=list`) split into one `<li>` per bullet (1d9c2c5 → 26c2cfd) so consecutive items wrap in `<ul>`.
- **Visual blocks** (`table`/`image`/`chart`/`code`) split into separate `body` / `caption` / `footnote` SegmentBoxes (bb10f69) — caption is independently editable.
- **Multi-line auxiliaries** (page headers/footers spanning multiple visual lines) split into per-line boxes (a7a5efa).

### Layout
- **Aux row layout**: top/bottom 3-column grid keyed off `data-aux-align` (a29cdaa). Multiple iterations to find the right same-row detection rule:
  - Initially y0-band → bbox-overlap → final: y0-distance with half-height tolerance (3a3b8cc) — touching-but-stacked bboxes no longer chain into one row.
- **Body-row layout**: same grouping for body items (e.g. two-column paragraphs sit side-by-side via `.body-row` flex container) (3239b78).
- **Discard-kind boxes** filtered from rendered HTML; reactivate restores them via cached `mineru.json` snippet (3a6b6be, 31f9004).

### Figures
- `vlm_segment_doc` now passes `image_writer_dir` so MinerU saves figure cropouts to disk (defb251).
- Auth middleware whitelists `GET /mineru-images/<file>` so iframe `<img>` requests work without `X-Auth-Token` (190c3b5).
- Frontend rewrites `<img src="mineru-images/…">` to absolute API URL (60288cf) — `about:srcdoc` base can't resolve relative paths.
- Figure styling: `max-width:90%`, `figure-desc` paragraph carrying MinerU's VLM-generated description (ce4cc8e, ad08e0e).

### LaTeX → MathML
- Added `latex2mathml` dependency.
- `$$…$$` display math → `<math display="block">` (30e202f).
- Bare LaTeX commands in table cells (`\dot{q}_{max,X}`) auto-converted to inline MathML (d9c7a02, fb3a313).
- Multi-letter sub/sup bodies wrapped in `\mathrm{}` so "max, Brennstab" reads as upright text instead of italic letter-multiplication (66faf2e).
- Trailing primes attach to the variable via `<msubsup>` (handles `&#x27;` HTML-entity form too) (7d5a01a).

### Footnote-marker heuristics
Three conservative regexes lift trailing `digit)` to `<sup>` where MinerU lost the typographic distinction:
- `(GGG)2)` → `<sup>2)</sup>` (after closing paren) — 73a3a53
- `0.44)` and `0,44)` → split off last digit (after `\d{1,2}[.,]\d{1,2}`) — 73a3a53, 455004d
- `Moderatorzone8)` → after a 4+ letter word — d673a78

Each uses lookbehind/lookahead to avoid false-tripping on legitimate values like `(0.44)`, `(2018)`, `1.5)`, or short units like `m2)` (left to the unit-exponent path).

### Unit exponents
`W/m2` → `W/m²`, `mm-1` → `mm⁻¹`. Conservative regex requires `/` or whitespace boundary so `H2O` and `Foo3.0` aren't touched (c91da9c).

### UI polish
- New box / Delete box buttons on the extract sidebar (32e7616).
- Pending state on Activate/Deactivate buttons (31f9004).
- Prev / next page arrow buttons flanking the page-grid toggle (9ebb031).
- Sticky page-nav so the toggle stays visible after a figure click expands the properties panel (698b0d2).
- "Quelltext (mineru.json)" panel shows the raw pre-conversion snippet for debugging (66faf2e).

### Re-extract robustness
- Re-extract injects `data-x/y/y1` so the new snippet lands in its correct y-position (afbdfa3).
- Empty VLM output falls back to keeping the previous snippet — boxes don't vanish on a no-op re-extract.
- Visual-hint badge no longer prints the kind label (`PARAGRAPH`/`HEADING`) into the cropped image — the VLM was OCR'ing it back into the output text (eba702f).

### Segment route removal
Final cleanup (8cc0edf): `frontend/src/admin/routes/segment.tsx` and `PropertiesSidebar.tsx` deleted. The extract route subsumes their function — it calls `/api/admin/docs/<slug>/segment` for full-doc and per-page passes, and exposes all editing controls (kind change, new/delete box, merge/unmerge, activate/deactivate, reset). `Segment` tab gone from `DocStepTabs`. Legacy `/segment` URLs redirect to `/extract`.

## What survives backend-side

The `/api/admin/docs/<slug>/segment` endpoint is intact — the extract route depends on it. `_re_extract_box` and the kind-change diagnostic flow are unchanged.

## Test coverage

- 59/59 backend tests pass (`features/pipelines/local-pdf/tests/test_routers_admin_segments.py`).
- 213/213 frontend tests pass (was 273 — 60 segment-specific tests removed alongside the route).
- All commits pass `ruff check`, `ruff format`, `mypy`, and the import-boundary hook.

## Migration notes for reviewer

- No database/schema migrations; all changes are file-format compatible (`mineru.json` gains an optional `html_snippet_raw` field with fallback).
- New dep: `latex2mathml >=3.77, <4` in `features/pipelines/local-pdf/pyproject.toml`.
- Existing extracted documents will need a re-segment to populate `html_snippet_raw` and benefit from the new conversion passes — no data loss.
- The `/api/admin/docs/<slug>/mineru-images/<file>` route now serves without `X-Auth-Token`. Acceptable for the single-user MVP bound to 127.0.0.1; revisit if the deployment widens.
