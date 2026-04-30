# A-Plus.2 — `frontend/` Browser SPA — Design

**Status:** Draft, brainstorming-derived (2026-04-30). Companion to A-Plus.1 backend design.

**Prerequisite:** A-Plus.1 backend (`refactor/pydantic-core-migration` + `feat/a-plus-1-backend`) merged. The frontend consumes the HTTP API contract defined in `2026-04-30-a-plus-1-backend-design.md`.

## 1. Motivation

A-Plus.1 exposes the goldens stack (curate, refine/deprecate, synthesise) over HTTP. A-Plus.2 is the browser UI that consumes that API and replaces the CLI for the typical curate-flow.

The smoke-test loop on the merged A.4-A.7 stack (PRs #15-#17) demonstrated three UX gaps that are awkward in CLI but trivial in a browser: dense table elements warrant multiple questions per element (now possible via PR #16), full-table rendering needs space (PR #17), and dry-run flows shouldn't need credentials (PR #15). All three lend themselves naturally to a browser surface.

For Day-1 scope (per AP1.1): single user, localhost-only, static-token auth. The frontend is a small SPA — no SSR, no offline mode, no multi-user collaboration features. Phase D will layer user-signals (`signal_einverstanden` / `signal_disqualifiziert`) on top later.

## 2. Goals & Non-Goals

### Goals

- TypeScript + React 18 + Vite SPA in a new top-level `frontend/` directory (separate npm package)
- Element-centric curate-flow matching the UI mockup in `phases-overview.md:200-221`
- Sidebar+Detail layout for navigation through 100s of elements
- Multi-question-per-element (D19 from A.4 spec — the loop continues on the same element until empty ENTER)
- Refine/Deprecate of existing entries via modals
- Synthesise streaming progress UI consuming the NDJSON endpoint from A-Plus.1
- Login-route with token persistence in `sessionStorage`, 401-interceptor → redirect to login
- Dev-server (Vite) with `/api/*`-proxy to FastAPI; production single-process via FastAPI static-mount of `dist/`
- Tests: Vitest + React Testing Library + msw + Playwright (e2e)
- Coverage target: 90%+ for components/hooks/api

### Non-Goals

- **No User-Signals.** `signal_einverstanden` / `signal_disqualifiziert` buttons in the phases-overview mockup are Phase D, not A-Plus.2.
- **No multi-user features.** No WebSockets, no presence indicators, no optimistic locks.
- **No mobile / touch optimization.** Desktop Chromium-only Day-1.
- **No offline / PWA.** No service worker, no offline queue.
- **No internationalization.** UI is German (mirrors CLI).
- **No theming / dark-mode toggle.** Tailwind dark-mode utilities available but no Day-1 switcher.
- **No SSR / SSG / static-export.** SPA via client-side rendering only.
- **No Storybook / visual regression tests.** RTL-component tests are sufficient.

## 3. Architecture

### 3.1 Process Model

- **Dev:** two terminals — `cd frontend && npm run dev` (Vite on 5173 with `/api/*`-proxy → 8000) + `query-eval serve` (FastAPI on 8000). Browser at 5173.
- **Production-ish (single-process):** `cd frontend && npm run build` produces `frontend/dist/`. FastAPI auto-mounts `StaticFiles` at `/` if `dist/` exists. User opens `http://127.0.0.1:8000`.

### 3.2 State Model

- **Server-state** managed by TanStack Query v5: cache + refetch-on-focus + retry-on-network. Cache keys per URL/slug/element_id.
- **Local UI-state** via React `useState`/`useReducer`. No Redux, no Zustand — YAGNI for MVP.
- **Auth-state** in `sessionStorage` (cleared on browser close, safer than localStorage).
- **Streaming-state** for synthesise via dedicated `useReducer` consuming the NDJSON line-stream.

### 3.3 Boundary

```
Browser ──HTTP/JSON+NDJSON──▶ FastAPI (A-Plus.1 backend, unchanged)
   │
   ├─ TanStack-Query (cache + refetch-on-focus + invalidation on mutations)
   ├─ react-router v6 (hash-mode for static-served compatibility)
   └─ Tailwind CSS (utility classes, no CSS-in-JS runtime)
```

The frontend has **no business logic** — all domain knowledge lives in the backend. Frontend is rendering + user-input + API calls + state-management. Tests run against mocked API, no real backend needed.

## 4. Routing

react-router v6 in **hash mode**. Hash mode works with static-served frontend without requiring FastAPI to register a SPA-catch-all route.

| Path | Page | API calls |
|---|---|---|
| `#/login` | Token-input → sessionStorage → redirect | `GET /api/health` for token validation |
| `#/docs` | Slug list, click → element-walk | `GET /api/docs` |
| `#/docs/:slug/elements` | Sidebar+Detail, default first element | `GET /api/docs/:slug/elements` |
| `#/docs/:slug/elements/:elementId` | Same Sidebar+Detail, deep-link | + `GET /api/docs/:slug/elements/:elementId` |
| `#/docs/:slug/synthesise` | Form + streaming progress | `POST /api/docs/:slug/synthesise` (streaming) |
| `#/*` | 404 with link to `/docs` | — |

### 4.1 Bootstrap Sequence

1. `main.tsx` mounts App
2. `App.tsx` reads `sessionStorage["goldens.api_token"]`
   - Missing → redirect to `#/login`
   - Present → fetch `GET /api/health` with `X-Auth-Token`
     - 200 → render outlet
     - 401 → clear token, redirect to `#/login`

### 4.2 Component Tree per Page

#### `#/docs/:slug/elements/:elementId`

```
DocElementsRoute
├─ TopBar (slug, doc-picker dropdown, logout)
├─ ElementSidebar
│   uses ["doc-elements", slug]
│   renders 1 row/element: page · type · count_active_entries · active-flag
│   click navigates to .../elements/<id>
└─ ElementDetail
    uses ["element", slug, elementId]
    ├─ ElementBody (Table | Figure | Paragraph | Heading)
    ├─ EntryList (EntryItem per active entry, with Refine/Deprecate buttons)
    ├─ NewEntryForm (textarea + Speichern button)
    │   on-success: invalidate ["element", slug, elementId] + ["doc-elements", slug]
    │   form clears, re-prompts on same element (multi-question pattern)
    └─ WeiterButton (advances :elementId in URL to next element from sidebar order)
```

Keyboard-shortcuts on this page:
- `Enter` — submit new-entry form (or "Weiter" when empty)
- `Escape` — close any open modal
- `j` / `k` / arrow-keys — sidebar nav up/down
- `t` — table-element stub ↔ full toggle
- `?` — open keyboard help modal

#### `#/docs/:slug/synthesise`

State machine:
```
Idle → fillingForm → submitting → streaming → complete | error
                                         │
                                         └─ user can cancel via AbortController
```

Component tree:
```
SynthesiseRoute
├─ SynthForm (idle, fillingForm)
│   fields per A-Plus.1 SynthesiseRequest
│   Submit triggers POST + streaming reader
├─ SynthProgress (submitting, streaming)
│   line-list, type-discriminated:
│     - SynthStartLine → header "Starting (9 elements)"
│     - SynthElementLine → row "✓ p2-8e6e4a52 · 3 kept · 234 tokens"
│     - SynthErrorLine → red row "✗ p1-aaa · LLM rate-limited"
│     - SynthCompleteLine → footer "Complete: 18 events written, 1834 tokens"
│   running totals (kept, errors, tokens)
└─ SynthSummary (complete)
    persistent recap + "Back to elements" link
```

### 4.3 NDJSON Streaming Reader

`api/ndjson.ts`:

```typescript
async function* streamNdjson(response: Response): AsyncIterable<SynthLine> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.trim()) yield JSON.parse(line);
    }
  }
}
```

`useSynthesise` hook consumes via `for await ... of` and dispatches into a `useReducer` state-machine. AbortController exposed for cancel-button.

## 5. Schema Strategy

API-shape mirrors A-Plus.1's Pydantic models. Frontend keeps a TS-only mirror in `src/types/domain.ts` — types only, no runtime validation (TanStack-Query trusts the server).

```typescript
export interface SourceElement {
  document_id: string;
  page_number: number;
  element_id: string;        // bare hash (sans p{page}- prefix)
  element_type: ElementType;
}

export interface DocumentElement {
  element_id: string;        // with p{page}- prefix
  page_number: number;
  element_type: ElementType;
  content: string;
  table_dims?: [number, number];
  table_full_content?: string;
  caption?: string;
}

export interface RetrievalEntry {
  entry_id: string;
  query: string;
  expected_chunk_ids: string[];
  chunk_hashes: Record<string, string>;
  review_chain: Review[];
  deprecated: boolean;
  refines: string | null;
  task_type: "retrieval";
  source_element: SourceElement | null;
}

// ... Actor union, Review, ElementWithCounts (matches Pydantic ElementWithCounts), etc.
```

Drift between frontend types and Pydantic shapes is caught by msw integration tests (request/response shape assertions).

## 6. Mutations + Cache Invalidation

| Action | Hook | Invalidates |
|---|---|---|
| Create Entry | `useCreateEntry` | `["element", slug, elementId]`, `["doc-elements", slug]` |
| Refine | `useRefineEntry` | `["element", slug, elementId]`, `["entry", entryId]` if cached |
| Deprecate | `useDeprecateEntry` | `["element", slug, elementId]` (entry filters out of active list) |

**Optimistic-update for Create Entry:** yes — feels like CLI-instant-save. On error: rollback + toast.
**Optimistic for Refine:** no — refine writes 2 events atomically; rollback would be complex. Show spinner instead.
**Optimistic for Deprecate:** yes — single event, rollback is removal of the deprecation marker.

## 7. Error Handling

| Class | HTTP / Source | Where caught | UX |
|---|---|---|---|
| Auth | 401 | `api/client.ts` interceptor | clear sessionStorage, redirect `#/login?reason=expired` |
| Validation | 422 | mutation `onError` | inline form-error parsing `detail[].msg` |
| Domain | 404 EntryNotFound, SlugUnknown · 409 EntryDeprecated | mutation `onError` | toast: human-readable detail; UI stable |
| Server / network | 500, network-down | global QueryClient `onError` + mutation `onError` | toast + retry-button |
| Streaming mid-error | `SynthErrorLine` in NDJSON | `useSynthesise` reducer | inline red row in progress list, tooltip with reason; stream continues |
| Stream connection-drop | `AbortError` from fetch | `useSynthesise` catch | "Connection lost. Saved events: N. [Resume]" with `start_from` pre-fill |

Toast lib: `react-hot-toast` (~1 KB, zero-config).

## 8. Auth Flow

- **Login** (`#/login`): `<input type="password">` for token → submit → fetch `GET /api/health` with header → success: `sessionStorage.setItem("goldens.api_token", token)` + redirect `/docs`. Fail: red banner "Token rejected".
- **Logout**: clear sessionStorage + redirect to `/login`.
- **401-Interceptor** in `api/client.ts`: every response → on 401, clear sessionStorage + push history `/login?reason=expired`.

## 9. Module Layout

```
DocumentAnalysisMicrosoft/
├── frontend/                            ← NEW in A-Plus.2
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── playwright.config.ts
│   ├── index.html
│   ├── src/
│   │   ├── main.tsx                     bootstrap: QueryClient, Router, Toaster
│   │   ├── App.tsx                      Layout shell: TopBar + Outlet
│   │   ├── routes/
│   │   │   ├── login.tsx
│   │   │   ├── docs-index.tsx
│   │   │   ├── doc-elements.tsx
│   │   │   └── doc-synthesise.tsx
│   │   ├── components/
│   │   │   ├── ElementSidebar.tsx
│   │   │   ├── ElementDetail.tsx
│   │   │   ├── ElementBody.tsx
│   │   │   ├── TableElementView.tsx
│   │   │   ├── FigureElementView.tsx
│   │   │   ├── EntryList.tsx
│   │   │   ├── EntryItem.tsx
│   │   │   ├── EntryRefineModal.tsx
│   │   │   ├── EntryDeprecateModal.tsx
│   │   │   ├── NewEntryForm.tsx
│   │   │   ├── SynthForm.tsx
│   │   │   ├── SynthProgress.tsx
│   │   │   ├── SynthSummary.tsx
│   │   │   ├── TopBar.tsx
│   │   │   ├── HelpModal.tsx
│   │   │   └── Spinner.tsx
│   │   ├── api/
│   │   │   ├── client.ts                fetch wrapper + 401-interceptor
│   │   │   ├── docs.ts
│   │   │   ├── entries.ts
│   │   │   └── ndjson.ts
│   │   ├── hooks/
│   │   │   ├── useAuth.ts
│   │   │   ├── useDocs.ts
│   │   │   ├── useElements.ts
│   │   │   ├── useElement.ts
│   │   │   ├── useCreateEntry.ts
│   │   │   ├── useRefineEntry.ts
│   │   │   ├── useDeprecateEntry.ts
│   │   │   ├── useSynthesise.ts
│   │   │   └── useKeyboardShortcuts.ts
│   │   ├── types/
│   │   │   └── domain.ts
│   │   └── styles/
│   │       └── globals.css              Tailwind directives
│   ├── tests/
│   │   ├── components/                  RTL-tests
│   │   ├── api/                         msw-mocked
│   │   ├── hooks/                       hook-tests
│   │   └── e2e/
│   │       └── tragkorb.spec.ts         Playwright happy-path
│   └── README.md                        dev-quickstart
└── features/goldens/src/goldens/api/app.py  ← +5 lines for static-mount
```

## 10. Testing Strategy

### 10.1 Coverage by layer

| Layer | Tool | What |
|---|---|---|
| Pure components | Vitest + RTL | Render with props, DOM asserts, user-events |
| Hooks | Vitest + RTL hook utils | Mutation logic, useSynthesise state-machine |
| API client + interceptor | Vitest + msw | URL/header/body asserts, 401-redirect path |
| NDJSON reader | Vitest | Push fixture-bytes through ReadableStream, assert yielded SynthLine objects (incl. partial-line buffer) |
| Integration (route-level) | Vitest + msw + RTL | MemoryRouter, full user-flow, assert API + DOM |
| E2E | Playwright | Full Tragkorb walk-through against real FastAPI |

### 10.2 Fixtures

- **Mock-Backend** (msw) returns Tragkorb-shaped responses for unit/integration
- **Real-Backend** (Playwright) reads `outputs/smoke-test-tragkorb/` from the repo

### 10.3 Coverage target

90%+ for `components/`, `hooks/`, `api/`. E2E covers happy-path only (login, walk through 2 elements, add 1 question, refine 1, deprecate 1, trigger synthesise dry-run, verify N progress lines).

### 10.4 Out of test scope

- Real LLM calls in synthesise E2E — `dry_run=true` only
- Cross-browser visual regressions — Chromium only
- Network throttling scenarios — defer to A-Plus.3

## 11. Build / Deploy

### 11.1 npm scripts

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "e2e": "playwright test",
    "lint": "eslint src --ext .ts,.tsx",
    "format:check": "prettier --check src"
  }
}
```

### 11.2 Vite config highlights

```typescript
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: true },
});
```

### 11.3 FastAPI hookup

In `features/goldens/src/goldens/api/app.py` (small extension to A-Plus.1's `create_app`):

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

# In create_app(), after all API routes are registered:
DIST = Path(__file__).parents[5] / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(DIST), html=True), name="frontend")
```

If `dist/` doesn't exist (dev mode or fresh install), the mount is skipped — only API routes and `/docs` (Swagger) are reachable. No crash.

### 11.4 Dev quickstart

```bash
cd frontend
npm install
npm run dev               # Terminal 1
# Terminal 2:
cd .. && source .venv/bin/activate
export GOLDENS_API_TOKEN=$(uuidgen)
query-eval serve
# Browser: http://127.0.0.1:5173 (Vite with proxy)
# Token from Terminal 2 → paste into Login form
```

### 11.5 Single-process production-ish quickstart

```bash
cd frontend && npm run build && cd ..
export GOLDENS_API_TOKEN=$(uuidgen)
query-eval serve
# Browser: http://127.0.0.1:8000
```

## 12. Accessibility Basics

Not a full WCAG-AA audit (solo MVP, no formal a11y testing), but:

- Semantic HTML (`<button>`, `<nav>`, `<main>`, `<aside>`)
- Form labels for every input
- Focus-visible states (Tailwind default + ring utilities)
- ARIA-live region for toast container (`aria-live="polite"`)
- Keyboard shortcuts documented in HelpModal (`?` key)

No specific screen-reader optimization, but semantic HTML alone yields 80% of the value.

## 13. Decision Log

| # | Topic | Decision | Why |
|---|---|---|---|
| AP2.1 | Tech stack | TS + React 18 + Vite | Microsoft-stack convention; mature ecosystem; Vite-HMR |
| AP2.2 | Framework | React-only, NOT Next.js | API routes duplicate FastAPI; SSR/SSG value near zero for authenticated localhost; static-export restrictions undermine Next.js strengths |
| AP2.3 | Build / Deploy | Single FastAPI process serves built `dist/`; dev: separate Vite with `/api/*`-proxy | Match's A-Plus.1 single-process model |
| AP2.4 | Day-1 scope | Full A-Plus.1 surface: curate, refine, deprecate, synthesise streaming | Match's AP1.2; browser must be true CLI alternative |
| AP2.5 | Routing | `react-router` v6 hash mode | Static-served compat; no FastAPI catch-all needed |
| AP2.6 | Server-state | TanStack Query v5 | Standard for API-driven SPAs; cache + refetch + retry built-in |
| AP2.7 | UI-state | React useState/useReducer | YAGNI for Redux/Zustand at MVP scale |
| AP2.8 | Styling | Tailwind CSS | Microsoft-conventional; small production bundle; fast to write |
| AP2.9 | HTTP client | native fetch | No Axios dep; sufficient for REST + ReadableStream NDJSON |
| AP2.10 | Streaming reader | native ReadableStream + TextDecoder line-splitter | ~30 LOC; native browser API; no SSE library |
| AP2.11 | Forms | Plain controlled inputs | YAGNI for react-hook-form at 3 forms total |
| AP2.12 | Tests | Vitest (unit) + RTL (component) + msw (api-mock) + Playwright (e2e) | Vite-native; standard stack |
| AP2.13 | Navigation style | B — Linear + Sidebar | Linear for flow-state; sidebar for 200-element-doc navigation |
| AP2.14 | Synthesise UI | Dedicated Route `/docs/{slug}/synthesise` with form + inline streaming + summary | Honest about long-running; events persist across navigation; no job-state machine |
| AP2.15 | Refine/Deprecate UI | Modals from EntryItem | Preserves page-context; standard CRUD pattern |
| AP2.16 | Auth flow | Login route → sessionStorage token → 401-interceptor | Standard for solo MVP; sessionStorage clears on browser-close |
| AP2.17 | Real-time updates | No polling; TanStack-Query refetch-on-focus default; Refresh button on lists | Solo-user Day-1; multi-user comes with Phase D |
| AP2.18 | URL style | Hash routing (`#/docs/<slug>/elements/<id>`) | Static-served compat without FastAPI catch-all |
| AP2.19 | Error envelope | FastAPI default `{"detail": ...}` → toast + inline form errors | Minimal custom code; matches AP1.9 |
| AP2.20 | Keyboard shortcuts | Enter/Escape/j/k/t/? | 200-element docs are mouse-hell otherwise |

## 14. Out of Scope (explicit)

- **Phase D User-Signals** — `signal_einverstanden` / `signal_disqualifiziert` buttons in the phases-overview mockup are NOT in A-Plus.2. Phase D gets its own brainstorming.
- **Multi-user / collaboration** — no WebSocket, no presence, no optimistic locks
- **Mobile / touch optimization** — desktop only
- **Offline mode / PWA** — no service worker, no offline queue
- **Internationalization** — UI is German (mirrors CLI)
- **Theming / dark-mode toggle** — Tailwind dark utilities available but no Day-1 switcher
- **Cross-browser / IE support** — Chromium only Day-1
- **Visual regression tests / Storybook** — RTL component tests sufficient

## 15. Open Questions (for refinement, not Day-1 blocking)

- **NewEntryForm UX:** Multi-line `<textarea>` with "Save" button + Ctrl+Enter shortcut, or single-line `<input>` + Enter-to-submit? (Recommendation: textarea + Save + Ctrl+Enter)
- **Sidebar width:** fixed or resizable? (Recommendation: fixed 280px; resizable when viewport > 1200px)
- **Optimistic updates for Refine:** yes or no? (Recommendation: no — refine writes 2 events atomically; rollback complexity > UX gain)
- **Keyboard shortcut preset:** vim-style (j/k/gg) or arrow keys? (Recommendation: arrow keys + j/k both supported; no gg/G)

## 16. Verification Checklist

Before merging A-Plus.2:

- [ ] A-Plus.1 backend merged and reachable at `http://127.0.0.1:8000/api/...`
- [ ] `cd frontend && npm install && npm run build` produces `dist/` without errors
- [ ] `query-eval serve` mounts `dist/` and serves at `http://127.0.0.1:8000`
- [ ] Login + walk through 2 Tragkorb elements + add 1 question succeeds end-to-end
- [ ] Refine + Deprecate modals work; entry list updates
- [ ] Synthesise dry-run streams progress lines for the 9-element fixture
- [ ] `npm test` (unit + integration) green
- [ ] `npm run e2e` (Playwright happy-path) green
- [ ] Coverage ≥90% in components/hooks/api
- [ ] ESLint + Prettier clean

## 17. Future Phases (referenced for context, not built here)

- **Phase D** — User-Signals (`signal_einverstanden`, `signal_disqualifiziert`) on elements and entries; aggregate views for triage
- **A-Plus.3** — Multi-user / per-user identity; SSO; reverse-proxy deployment
- **Phase B** — Answer-quality LLM-judge; new entry type `AnswerQualityEntry`; new route `/docs/:slug/judge`
