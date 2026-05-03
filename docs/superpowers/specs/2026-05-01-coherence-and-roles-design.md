# Coherence + Roles + UI Polish — Design Spec

**Phase:** A.1.0 — Coherence pass on top of A.0 + A-Plus.2
**Date:** 2026-05-01
**Status:** Spec — proceed directly to writing-plans (user approved as "ship it").

## 1. Goal

Stop pretending the SPA is two unrelated apps stitched together (A-Plus.2 goldens-frontend + A.0 local-pdf). Re-architect as **one coherent product with two role-based shells**:

- **Admin** — uploads PDFs, segments + corrects, extracts + corrects, runs synthesis, reviews synth output, manages curators, monitors curators (later: runs pipelines + dashboards).
- **Curator** — sees assigned documents, reads paragraphs, adds their own questions, reviews and weights synthesised questions.

Same product, same auth surface, same backend. Different chrome, different routes, different capabilities — gated by role.

The current testing session surfaced this defect concretely: clicking the "Goldens" TopBar link landed on `/docs/<slug>/elements`, which 404'd because the local-pdf backend doesn't have that route. Two route trees in one SPA, both pretending to use `/api/docs`, no clear ownership. This spec ends that.

## 2. Decisions Log

| ID | Topic | Decision | Reasoning |
|----|-------|----------|-----------|
| C1 | Product framing | One product, two role-based shells | Admin and curator do meaningfully different things on the same data; not two products, two faces |
| C2 | Auth model | Simple tokens — admin token from env, curator tokens stored in `data/curators.json`, admin issues + revokes via UI | Internal team tool; ships in ~1 day; clean upgrade path to user-accounts later |
| C3 | URL structure | Role-prefixed: `/admin/*` and `/curate/*`; `/login` is shared | Codebase mirrors URLs, no accidental cross-role leakage, easy to add a 3rd role later |
| C4 | Backend route prefixing | `/api/admin/*` (admin-only) and `/api/curate/*` (curator-only); `/api/auth/*` and `/api/_features` shared | Resolves the `/api/docs/<slug>/elements` 404 ambiguity at the URL level |
| C5 | Doc state machine | `raw → segmenting → extracting → extracted → synthesising → synthesised → open-for-curation → archived` | Linear admin-driven; `open-for-curation` is the explicit publish gate |
| C6 | Curator-doc visibility | Curator only sees docs in `open-for-curation` AND assigned to their token | Per-doc admin control over who curates what |
| C7 | Admin chrome | Navy blue (#1e3a8a) header + ADMIN role badge in top-right | Instantly visible role context; no chance of confusing admin/curator |
| C8 | Curator chrome | Forest green (#065f46) header + name pill in top-right | Same approach, different color signals different role |
| C9 | UI library stack | Add `lucide-react` (icons), `framer-motion` (animations), `@radix-ui/react-*` (headless primitives: Dialog, Dropdown, Toast); keep existing Tailwind, TanStack Query, Tiptap, CodeMirror | Modern, maintained, accessible, well-typed, low bundle cost |
| C10 | Component migration | Move `frontend/src/local-pdf/*` to `frontend/src/admin/*`; move existing `frontend/src/components/Element*` etc to `frontend/src/curator/components/*` | Module structure mirrors role/shell |
| C11 | Login redirect | After token validation: admin → `/admin/inbox`; curator → `/curate/`; ambiguous → `/login` with error | Explicit role-driven navigation |
| C12 | Existing routes deletion | Remove `/docs`, `/docs/<slug>/elements`, `/docs/<slug>/synthesise` from the SPA — all functionality lives under `/admin/*` or `/curate/*` | No more dead-end URLs |
| C13 | Backend feature endpoint | New `GET /api/_features` returns `{features: [...]}` so the frontend can show right nav even before login | Single source of truth for what the deployment supports |
| C14 | Migration strategy | Single PR off main; old `/api/docs/*` routes return 410 Gone for 2 weeks then are removed | One coherent state, no half-migrated mess |
| C15 | Admin token bootstrap | Admin token = `GOLDENS_API_TOKEN` env var (unchanged from today); first admin login auto-creates `data/curators.json` if absent | Backward compatible with existing dev script |
| C16 | Curator token format | 32-char hex (`secrets.token_hex(16)`); admin sees full token once at creation, then only the prefix (last 8 chars) | Tokens are credentials; show-once is the standard hygiene |

## 3. Architecture

### Frontend module layout

```
frontend/src/
├── App.tsx                      # role-router: /login, /admin/*, /curate/*
├── auth/
│   ├── useAuth.ts               # role-aware (returns {token, role, name})
│   ├── routes/Login.tsx         # token input + role detection on submit
│   └── api.ts                   # POST /api/auth/check
├── shell/
│   ├── AdminShell.tsx           # navy chrome, admin nav, Outlet for routes
│   ├── CuratorShell.tsx         # green chrome, curator nav, Outlet for routes
│   └── shared/
│       ├── ColorThemes.ts       # role color tokens
│       └── RoleBadge.tsx        # the pill in top-right
├── admin/
│   ├── routes/
│   │   ├── Inbox.tsx            # was: local-pdf/routes/inbox + docs-index merged
│   │   ├── Segment.tsx          # was: local-pdf/routes/segment
│   │   ├── Extract.tsx          # was: local-pdf/routes/extract
│   │   ├── Synthesise.tsx       # was: routes/doc-synthesise
│   │   ├── DocCurators.tsx      # NEW — assign curators to a doc
│   │   ├── Curators.tsx         # NEW — list/create/revoke curator tokens
│   │   └── CuratorActivity.tsx  # NEW — per-curator monitor
│   ├── components/
│   │   ├── BoxOverlay.tsx       # was: local-pdf/components/BoxOverlay
│   │   ├── HtmlEditor.tsx       # was: local-pdf/components/HtmlEditor
│   │   ├── PdfPage.tsx          # was: local-pdf/components/PdfPage
│   │   ├── PropertiesSidebar.tsx
│   │   ├── StageIndicator.tsx
│   │   ├── StageTimeline.tsx
│   │   └── StatusBadge.tsx
│   ├── hooks/                   # was: local-pdf/hooks/* + existing useElements/useSynthesise
│   ├── streamReducer.ts         # was: local-pdf/streamReducer
│   └── api/
│       └── adminClient.ts       # was: local-pdf/api/client + endpoints to /api/admin/*
├── curator/
│   ├── routes/
│   │   ├── Docs.tsx             # NEW — list of assigned docs
│   │   └── DocPage.tsx          # NEW — element-by-element question entry
│   ├── components/
│   │   ├── ElementBody.tsx      # was: components/ElementBody
│   │   ├── ElementSidebar.tsx   # was: components/ElementSidebar
│   │   ├── NewEntryForm.tsx     # was: components/NewEntryForm
│   │   ├── EntryItem.tsx
│   │   ├── EntryList.tsx
│   │   ├── EntryRefineModal.tsx
│   │   ├── EntryDeprecateModal.tsx
│   │   └── HelpModal.tsx
│   ├── hooks/                   # was: hooks/* (useElements, useElement, useCreateEntry, etc.)
│   └── api/
│       └── curatorClient.ts     # NEW — endpoints to /api/curate/*
├── shared/
│   ├── types/                   # domain types used by both shells
│   ├── components/              # SourceElement renderer, modal primitives, toasts
│   └── icons/                   # re-exports from lucide-react with per-app conventions
├── styles/
│   ├── tailwind.css
│   └── shell-themes.css         # color variables for admin / curator
└── tests/                       # mirrors src/ structure
```

### Backend module layout

```
features/pipelines/local-pdf/src/local_pdf/
├── api/
│   ├── auth.py                  # extended: token → {role, name} lookup
│   ├── config.py                # unchanged
│   ├── app.py                   # mounts /api/admin/* + /api/curate/* + /api/auth/*
│   ├── schemas.py               # extended: Curator, CuratorAssignment
│   └── routers/
│       ├── auth.py              # NEW: /api/auth/check, /api/_features
│       ├── admin/
│       │   ├── docs.py          # was: routers/docs (list/upload/source.pdf)
│       │   ├── segments.py      # was: routers/segments
│       │   ├── extract.py       # was: routers/extract
│       │   ├── synthesise.py    # NEW: orchestrates synth via goldens.creation
│       │   └── curators.py      # NEW: list/create/revoke + assignment management
│       └── curate/
│           ├── docs.py          # NEW: GET /api/curate/docs (assigned-only)
│           ├── elements.py      # NEW: GET /api/curate/docs/<slug> (read-only)
│           └── questions.py     # NEW: POST /api/curate/docs/<slug>/questions
├── storage/
│   ├── sidecar.py               # unchanged
│   └── curators.py              # NEW: read/write data/curators.json with fcntl
└── workers/                     # unchanged from A.0
```

### Data on disk

```
data/
├── raw-pdfs/<slug>/             # unchanged from A.0
│   ├── source.pdf
│   ├── meta.json
│   ├── yolo.json
│   ├── segments.json
│   ├── mineru-out.json
│   ├── html.html
│   ├── synthetic.json           # NEW — synth output
│   └── sourceelements.json      # final
└── curators.json                # NEW — admin-managed
```

`curators.json` schema:

```json
{
  "curators": [
    {
      "id": "c-a3f9",
      "name": "Doktor Müller",
      "token_prefix": "c0d3...",
      "token_sha256": "<hex hash of full token>",
      "assigned_slugs": ["bam-tragkorb-2024", "din-en-12100"],
      "created_at": "2026-05-01T12:00:00Z",
      "last_seen_at": "2026-05-01T14:23:11Z",
      "active": true
    }
  ]
}
```

Token comparison: backend hashes presented token via SHA-256 and compares to stored hash. Admin sees full token only at creation moment; from then on, only `token_prefix` (last 8 chars) is shown.

## 4. URL Catalog

### Frontend SPA

```
/login                                      shared
/admin/inbox                                admin only
/admin/doc/<slug>/segment                   admin only
/admin/doc/<slug>/extract                   admin only
/admin/doc/<slug>/synthesise                admin only
/admin/doc/<slug>/curators                  admin only — assign curators
/admin/curators                             admin only — list/create/revoke
/admin/curators/<id>/activity               admin only — monitor
/admin/pipelines                            admin only — placeholder ("coming soon")
/admin/dashboard                            admin only — placeholder
/curate/                                    curator only — assigned docs list
/curate/doc/<slug>                          curator only — element-by-element view
/curate/doc/<slug>/element/<id>             curator only — deep link
/*                                          → 404 page with "Go home" button
```

### Backend API

```
POST /api/auth/check                        body: {token} → 200 {role, name} or 401
GET  /api/_features                         200 {features: [...], roles: ["admin", "curator"]}
GET  /api/health                            200 {status, data_root}

# Admin
GET    /api/admin/docs                      list inbox
POST   /api/admin/docs                      upload PDF (multipart)
GET    /api/admin/docs/<slug>               metadata
GET    /api/admin/docs/<slug>/source.pdf    PDF binary
POST   /api/admin/docs/<slug>/segment       NDJSON streaming run
GET    /api/admin/docs/<slug>/segments      current boxes
PUT    /api/admin/docs/<slug>/segments/<id> update box
POST   /api/admin/docs/<slug>/segments/merge
POST   /api/admin/docs/<slug>/segments/split
DELETE /api/admin/docs/<slug>/segments/<id>
POST   /api/admin/docs/<slug>/extract       NDJSON streaming run
POST   /api/admin/docs/<slug>/extract/region
GET    /api/admin/docs/<slug>/html
PUT    /api/admin/docs/<slug>/html
POST   /api/admin/docs/<slug>/synthesise    NDJSON streaming
GET    /api/admin/docs/<slug>/synthesise    list synth output
POST   /api/admin/docs/<slug>/export        produces sourceelements.json
POST   /api/admin/docs/<slug>/publish       sets status to open-for-curation
POST   /api/admin/docs/<slug>/archive       sets status to archived
GET    /api/admin/docs/<slug>/curators      list curators assigned to this doc
POST   /api/admin/docs/<slug>/curators      assign curator to this doc
DELETE /api/admin/docs/<slug>/curators/<id>
GET    /api/admin/curators                  list all curators
POST   /api/admin/curators                  create curator + token
DELETE /api/admin/curators/<id>             revoke
GET    /api/admin/curators/<id>/activity    audit trail (questions added, etc.)

# Curator
GET    /api/curate/docs                     assigned-only listing
GET    /api/curate/docs/<slug>              read-only doc view (elements, html, etc.)
GET    /api/curate/docs/<slug>/elements     element list (paragraphs)
GET    /api/curate/docs/<slug>/elements/<id>
POST   /api/curate/docs/<slug>/questions    add a question
GET    /api/curate/docs/<slug>/synthesised-questions   review queue
POST   /api/curate/docs/<slug>/synthesised-questions/<id>/vote   weight (good/bad/skip)

# Removed (410 Gone for 2 weeks, then deleted)
ALL /api/docs/*                             — moved to /api/admin/* or /api/curate/*
```

## 5. Visual Design System

### Color tokens

```css
:root {
  /* Admin */
  --admin-chrome:        #1e3a8a;  /* navy */
  --admin-chrome-fg:     #ffffff;
  --admin-accent:        #fbbf24;  /* amber for ADMIN badge */

  /* Curator */
  --curator-chrome:      #065f46;  /* forest green */
  --curator-chrome-fg:   #ffffff;
  --curator-accent:      #6ee7b7;  /* mint for name badge */

  /* Shared */
  --surface:             #ffffff;
  --surface-muted:       #f9fafb;
  --border:              #e5e7eb;
  --text:                #111827;
  --text-muted:          #6b7280;
  --link:                #3b82f6;
  --danger:              #ef4444;
  --warn:                #f59e0b;
  --ok:                  #10b981;
}
```

### Typography

- System font stack with `-apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`
- Monospace for technical content: `ui-monospace, "SF Mono", Menlo, Consolas, monospace`
- Sizes: 11px (label), 13px (body), 16px (h3), 20px (h2), 24px (h1)

### Iconography

`lucide-react` — modern, comprehensive, tree-shakeable. Conventions:
- Navigation: `Inbox`, `Users`, `BarChart3`, `Cpu` (pipelines), `LogOut`
- Actions: `Plus`, `Trash2`, `Edit3`, `Save`, `Play`, `RefreshCcw`
- Status: `Circle`, `CheckCircle2`, `XCircle`, `Clock`, `AlertTriangle`
- Semantic: re-export under `frontend/src/shared/icons/index.ts` so component code can `import { Inbox } from "@/shared/icons"`.

### Animations

`framer-motion` — declarative React API, well-typed. Patterns:
- Page transitions: `<AnimatePresence>` wrap on the AdminShell / CuratorShell `<Outlet />` for fade-in (200ms) on route change
- Modal entry: scale 0.97 → 1.0 with opacity 0 → 1 (150ms)
- Toast slide: `from: y=-20, opacity=0` → `to: y=0, opacity=1` (200ms)
- Box drag/resize: keep CSS transforms (no framer-motion needed; would slow it)
- Status-badge color change: smooth color transition (150ms)

### Headless primitives

`@radix-ui/react-*`:
- `@radix-ui/react-dialog` — replaces hand-rolled modals (HelpModal, RefineModal, DeprecateModal)
- `@radix-ui/react-dropdown-menu` — for kind-picker on box-right-click
- `@radix-ui/react-toast` — replaces `react-hot-toast` (more accessible, keeps consistency with Radix surface)
- `@radix-ui/react-tabs` — admin route layouts that have multiple sub-views (e.g. doc detail with segment / extract / synth tabs)

### Accessibility (free wins from Radix)

- Keyboard nav on all menus + dialogs
- Focus traps in modals
- ARIA labels auto-applied
- High-contrast role badges (WCAG AA)

## 6. Doc State Machine (extended)

```
                ┌───────────┐
upload PDF ──→  │   raw     │
                └─────┬─────┘
                      │ admin clicks "Start"
                ┌─────▼─────┐
                │segmenting │  ← admin edits boxes
                └─────┬─────┘
                      │ admin clicks "Run extraction"
                ┌─────▼─────┐
                │extracting │  ← MinerU 3 runs
                └─────┬─────┘
                      │ extraction complete
                ┌─────▼─────┐
                │ extracted │  ← admin edits HTML
                └─────┬─────┘
                      │ admin clicks "Run synthesis"
                ┌─────▼─────┐
                │synthesising│  ← LLM generates Q candidates
                └─────┬─────┘
                      │ synthesis complete
                ┌─────▼─────┐
                │synthesised│  ← admin reviews + accepts/rejects synth Qs
                └─────┬─────┘
                      │ admin clicks "Publish for curation"
                ┌─────▼─────────────┐
                │ open-for-curation │  ← curators see assigned slice
                └─────┬─────────────┘
                      │ admin clicks "Archive"
                ┌─────▼─────┐
                │ archived  │  ← read-only forever; used for evaluation
                └───────────┘
```

Curator can be in `open-for-curation` indefinitely — no auto-transition. Admin manually archives when satisfied with curation coverage.

Synthesis is OPTIONAL — admin can publish without synthesising (state goes `extracted → published`, skipping the synth step). Future Phase D will revisit this.

## 7. Migration Strategy

This is a single PR off main, not incremental. The current state is unstable enough that a half-migration would be worse than the disease.

### Stage 1 — Backend route prefix split (no behavior change)

- Move all existing routes under `/api/admin/*`. Add 410 Gone shim at `/api/docs/*` that says "moved to /api/admin/docs/*; this shim removes 2026-05-15."
- Update tests to match.

### Stage 2 — Auth refactor

- Extend `auth.py` to look up token in `data/curators.json` first, fall back to env-var (admin) match.
- New endpoint `POST /api/auth/check` returns `{role, name}`.
- Curator endpoints under `/api/curate/*` enforce role.

### Stage 3 — Curator backend

- Implement `/api/curate/*` reading from existing sidecar files but filtered to `open-for-curation` AND assigned.
- New `/api/admin/curators` for token CRUD and per-doc assignment.

### Stage 4 — Frontend module restructure

- Move `frontend/src/local-pdf/*` to `frontend/src/admin/*`.
- Move `Element*` components to `frontend/src/curator/components/*`.
- Delete the old `routes/docs-index.tsx`, `routes/doc-elements.tsx`, `routes/doc-synthesise.tsx`.

### Stage 5 — Shells + role-router

- Add `AdminShell` (navy chrome) + `CuratorShell` (green chrome).
- Update `App.tsx` for `/admin/*` + `/curate/*` + role-aware login redirect.

### Stage 6 — UI library integration

- Add deps: `lucide-react`, `framer-motion`, `@radix-ui/react-dialog`, `@radix-ui/react-dropdown-menu`, `@radix-ui/react-toast`, `@radix-ui/react-tabs`.
- Replace existing modals/menus/toasts with Radix primitives.
- Replace inline emoji icons with Lucide icons.
- Wrap `<Outlet />` in `<AnimatePresence>` for route transitions.

### Stage 7 — Curator UI

- Build `/curate/` (assigned-doc list) and `/curate/doc/<slug>` (element-by-element question entry) using moved + polished components.

### Stage 8 — Smoke + ship

- Manual end-to-end smoke for both roles.
- Push branch, open PR.

## 8. Code Reuse + Library Choices

| Library | Version | Purpose | Why |
|---|---|---|---|
| `lucide-react` | ^0.477 | Icons | Tree-shakeable, modern, comprehensive (~1000 icons), MIT |
| `framer-motion` | ^11 | Animations | De-facto standard for React; declarative; great types |
| `@radix-ui/react-dialog` | ^1.1 | Modals | Headless, accessible, MIT |
| `@radix-ui/react-dropdown-menu` | ^2.1 | Dropdowns | Same |
| `@radix-ui/react-toast` | ^1.2 | Toasts | Replaces react-hot-toast; better Radix integration |
| `@radix-ui/react-tabs` | ^1.1 | Sub-navigation | For doc-detail tabbed UI |
| `clsx` | ^2.1 | Conditional classNames | Tiny utility, common in Tailwind projects |

Bundle size impact: Lucide tree-shakes to ~5 KB per icon used; framer-motion is ~20 KB gzipped; Radix is ~3-5 KB per primitive. Total budget impact: ~50 KB gzipped — acceptable for the UX improvement.

## 9. Out of Scope

- **Proper user accounts (passwords + sessions)** — defer to a Phase A.1.1 if needed
- **External OAuth (GitHub/Google)** — out of scope for internal tool
- **Audit log persistence beyond the in-flight session** — `last_seen_at` is the only persistent audit field
- **Rate-limiting curator actions** — small N, defer until needed
- **Email notifications to curators** — they get tokens out-of-band today
- **Mobile-responsive layout** — desktop-only (matches A.0 decision)
- **Real-time collaboration** (multiple curators on same doc simultaneously) — fcntl-locked storage means sequential safe; concurrency UI deferred

## 10. Known Follow-ups

- `Phase A.1.1` — proper user accounts with passwords + sessions, when team grows or external curators join
- `Phase A.1.2` — admin dashboard with cross-doc curator activity heatmap
- `Phase A.1.3` — pipeline runs + performance dashboards (the "later" track from the user's vision)
- Move from `react-hot-toast` to Radix `Toast` cleanly (probably as part of Stage 6)
- Audit `data/curators.json` write concurrency (fcntl-locked already; double-check after first multi-admin scenario, if any)

## 11. Success Criteria

After this lands:
- [ ] No URL in the SPA produces a 404 from a misrouted backend call
- [ ] Login as admin → land on `/admin/inbox`; nav has only admin items; chrome is navy
- [ ] Login as curator → land on `/curate/`; nav has only curator items; chrome is green
- [ ] `/api/docs/*` returns 410 Gone (not silently broken)
- [ ] All existing test suites pass (76 backend, ~104 frontend, plus new tests for role-gating)
- [ ] One smoke run end-to-end: admin uploads PDF → segments → extracts → synthesises → publishes; curator logs in → sees doc → adds question
- [ ] No remaining "Goldens" / "Local PDF" labels in TopBar — both replaced by role chrome
- [ ] No env-var hacks needed for frontend dev (`npm run dev` Just Works)

## 12. References

- `docs/superpowers/specs/2026-04-30-local-pdf-pipeline-design.md` — A.0 base
- `docs/superpowers/specs/2026-04-30-a-plus-1-backend-design.md` — A-Plus.1 backend
- `docs/superpowers/specs/2026-04-30-a-plus-2-frontend-design.md` — A-Plus.2 frontend
- `docs/superpowers/specs/2026-05-01-a-0-model-lifecycle-and-progress-design.md` — model lifecycle
- Lucide icons: https://lucide.dev
- Framer Motion: https://www.framer.com/motion/
- Radix Primitives: https://www.radix-ui.com/primitives
