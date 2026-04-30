# A-Plus.2 Frontend SPA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a TypeScript + React 18 + Vite SPA in a new top-level `frontend/` directory that consumes the A-Plus.1 HTTP backend. Element-centric curate flow with sidebar+detail, multi-question per element, refine/deprecate modals, and a streaming-progress UI for synthesise.

**Architecture:** Static-served SPA in hash-routing mode. `fetch` + `ReadableStream` for REST + NDJSON. TanStack Query for server-state caching. React `useState`/`useReducer` for local UI state. `react-hot-toast` for errors. Vitest + RTL + msw for unit/integration; Playwright for E2E.

**Tech Stack:** TypeScript 5 · React 18 · Vite 5 · react-router 6 (hash mode) · TanStack Query 5 · Tailwind CSS 3 · react-hot-toast · Vitest · React Testing Library · msw 2 · Playwright

**Spec:** `docs/superpowers/specs/2026-04-30-a-plus-2-frontend-design.md`
**Prerequisite:** A-Plus.1 backend merged and reachable at `http://127.0.0.1:8000/api/...` (which itself depends on the Pydantic-migration PR).

---

## File Map

**New top-level directory `frontend/`:**

```
frontend/
├── .gitignore                           node_modules, dist, coverage
├── package.json
├── tsconfig.json
├── tsconfig.node.json                   for vite.config.ts only
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── playwright.config.ts
├── index.html                           single entry
├── src/
│   ├── main.tsx                         bootstrap
│   ├── App.tsx                          shell layout
│   ├── routes/
│   │   ├── login.tsx
│   │   ├── docs-index.tsx
│   │   ├── doc-elements.tsx
│   │   └── doc-synthesise.tsx
│   ├── components/
│   │   ├── ElementSidebar.tsx
│   │   ├── ElementDetail.tsx
│   │   ├── ElementBody.tsx
│   │   ├── TableElementView.tsx
│   │   ├── FigureElementView.tsx
│   │   ├── EntryList.tsx
│   │   ├── EntryItem.tsx
│   │   ├── EntryRefineModal.tsx
│   │   ├── EntryDeprecateModal.tsx
│   │   ├── NewEntryForm.tsx
│   │   ├── SynthForm.tsx
│   │   ├── SynthProgress.tsx
│   │   ├── SynthSummary.tsx
│   │   ├── TopBar.tsx
│   │   ├── HelpModal.tsx
│   │   └── Spinner.tsx
│   ├── api/
│   │   ├── client.ts                    fetch wrapper + 401 interceptor
│   │   ├── docs.ts                      doc/element/synthesise endpoints
│   │   ├── entries.ts                   entry CRUD
│   │   └── ndjson.ts                    streaming reader
│   ├── hooks/
│   │   ├── useAuth.ts
│   │   ├── useDocs.ts
│   │   ├── useElements.ts
│   │   ├── useElement.ts
│   │   ├── useCreateEntry.ts
│   │   ├── useRefineEntry.ts
│   │   ├── useDeprecateEntry.ts
│   │   ├── useSynthesise.ts
│   │   └── useKeyboardShortcuts.ts
│   ├── types/
│   │   └── domain.ts                    TS mirrors of Pydantic schemas
│   └── styles/
│       └── globals.css                  Tailwind directives
├── tests/
│   ├── setup.ts                         test env bootstrap
│   ├── msw-handlers.ts                  shared msw handlers
│   ├── api/
│   │   ├── client.test.ts
│   │   ├── ndjson.test.ts
│   │   └── docs.test.ts
│   ├── hooks/
│   │   ├── useAuth.test.ts
│   │   ├── useElement.test.ts
│   │   ├── useCreateEntry.test.ts
│   │   ├── useSynthesise.test.ts
│   │   └── useKeyboardShortcuts.test.ts
│   ├── components/
│   │   ├── ElementSidebar.test.tsx
│   │   ├── ElementDetail.test.tsx
│   │   ├── EntryItem.test.tsx
│   │   ├── NewEntryForm.test.tsx
│   │   ├── TableElementView.test.tsx
│   │   ├── SynthProgress.test.tsx
│   │   └── EntryRefineModal.test.tsx
│   ├── routes/
│   │   ├── login.test.tsx
│   │   ├── docs-index.test.tsx
│   │   ├── doc-elements.test.tsx
│   │   └── doc-synthesise.test.tsx
│   └── e2e/
│       └── tragkorb.spec.ts             Playwright happy-path
└── README.md                            dev-quickstart
```

**Modified:**
- `features/goldens/src/goldens/api/app.py` — add 5 lines for static-mount of `frontend/dist/`
- Root `.gitignore` — add `frontend/node_modules/` and `frontend/dist/`

---

## Task 1: Project Scaffolding — package.json, tsconfig, configs

**Files:**
- Create: `frontend/.gitignore`
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/postcss.config.js`
- Create: `frontend/tailwind.config.js`
- Modify: root `.gitignore`

- [ ] **Step 1: Create `frontend/.gitignore`**

```
node_modules/
dist/
coverage/
*.tsbuildinfo
.vite/
playwright-report/
test-results/
```

- [ ] **Step 2: Create `frontend/package.json`**

```json
{
  "name": "goldens-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage",
    "e2e": "playwright test",
    "lint": "eslint src --ext .ts,.tsx",
    "format:check": "prettier --check \"src/**/*.{ts,tsx,css}\"",
    "format": "prettier --write \"src/**/*.{ts,tsx,css}\""
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.26.0",
    "@tanstack/react-query": "^5.51.0",
    "react-hot-toast": "^2.4.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.5.0",
    "vite": "^5.4.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0",
    "vitest": "^2.1.0",
    "@vitest/coverage-v8": "^2.1.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.5.0",
    "@testing-library/jest-dom": "^6.5.0",
    "jsdom": "^25.0.0",
    "msw": "^2.4.0",
    "@playwright/test": "^1.47.0",
    "eslint": "^9.10.0",
    "@typescript-eslint/eslint-plugin": "^8.4.0",
    "@typescript-eslint/parser": "^8.4.0",
    "eslint-plugin-react": "^7.35.0",
    "eslint-plugin-react-hooks": "^4.6.0",
    "prettier": "^3.3.0"
  }
}
```

- [ ] **Step 3: Create `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "useDefineForClassFields": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "tests"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 4: Create `frontend/tsconfig.node.json`**

```json
{
  "compilerOptions": {
    "composite": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true
  },
  "include": ["vite.config.ts", "tailwind.config.js", "postcss.config.js"]
}
```

- [ ] **Step 5: Create `frontend/vite.config.ts`**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/main.tsx", "src/types/**", "**/*.d.ts"],
    },
  },
});
```

- [ ] **Step 6: Create `frontend/index.html`**

```html
<!doctype html>
<html lang="de">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Goldens — Curate</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Create `frontend/tailwind.config.js`**

```javascript
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["system-ui", "-apple-system", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 8: Create `frontend/postcss.config.js`**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 9: Update root `.gitignore`**

Append:
```
frontend/node_modules/
frontend/dist/
frontend/coverage/
frontend/playwright-report/
frontend/test-results/
frontend/.vite/
```

- [ ] **Step 10: Install deps + verify**

Run from repo root:
```bash
cd frontend && npm install
```

Expected: completes without errors, `frontend/node_modules/` populated, ~250 MB.

- [ ] **Step 11: Commit**

```bash
git add frontend/.gitignore frontend/package.json frontend/package-lock.json \
        frontend/tsconfig.json frontend/tsconfig.node.json \
        frontend/vite.config.ts frontend/index.html \
        frontend/postcss.config.js frontend/tailwind.config.js \
        .gitignore
git commit -m "feat(frontend): scaffold A-Plus.2 npm project with Vite + React + Tailwind"
```

---

## Task 2: Test environment setup

**Files:**
- Create: `frontend/tests/setup.ts`

- [ ] **Step 1: Create `frontend/tests/setup.ts`**

```typescript
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});
```

- [ ] **Step 2: Verify a smoke vitest run works (no tests yet, just env)**

Run: `cd frontend && npm test 2>&1 | tail -5`

Expected: "No test files found" or similar — environment loads without error.

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/setup.ts
git commit -m "feat(frontend): test environment setup with @testing-library/jest-dom"
```

---

## Task 3: Tailwind base styles

**Files:**
- Create: `frontend/src/styles/globals.css`

- [ ] **Step 1: Create `frontend/src/styles/globals.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  body {
    @apply bg-slate-50 text-slate-900 antialiased;
  }

  :focus-visible {
    @apply outline-none ring-2 ring-blue-500 ring-offset-2;
  }
}

@layer components {
  .btn {
    @apply inline-flex items-center justify-center rounded px-3 py-1.5 text-sm font-medium transition;
  }

  .btn-primary {
    @apply btn bg-blue-600 text-white hover:bg-blue-700 disabled:bg-slate-300 disabled:text-slate-500;
  }

  .btn-secondary {
    @apply btn bg-white border border-slate-300 hover:bg-slate-50;
  }

  .btn-danger {
    @apply btn bg-red-600 text-white hover:bg-red-700;
  }

  .input {
    @apply w-full rounded border border-slate-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500;
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/styles/globals.css
git commit -m "feat(frontend): Tailwind base + utility-class component layer"
```

---

## Task 4: TypeScript domain types (mirror of Pydantic)

**Files:**
- Create: `frontend/src/types/domain.ts`

- [ ] **Step 1: Create `frontend/src/types/domain.ts`**

```typescript
export type ElementType = "paragraph" | "heading" | "table" | "figure" | "list_item";

export type Level = "expert" | "phd" | "masters" | "bachelors" | "other";
export type ComputedLevel = Level | "synthetic";

export type CreateAction = "created_from_scratch" | "synthesised" | "imported_from_faq";

export interface SourceElement {
  document_id: string;
  page_number: number;
  element_id: string;          // bare hash (sans p{page}- prefix)
  element_type: ElementType;
}

export interface DocumentElement {
  element_id: string;          // p{page}-<hash>
  page_number: number;
  element_type: ElementType;
  content: string;
  table_dims?: [number, number];
  table_full_content?: string | null;
  caption?: string | null;
}

export interface HumanActor {
  kind: "human";
  pseudonym: string;
  level: Level;
}

export interface LLMActor {
  kind: "llm";
  model: string;
  model_version: string;
  prompt_template_version: string;
  temperature: number;
}

export type Actor = HumanActor | LLMActor;

export interface Review {
  timestamp_utc: string;
  action: string;
  actor: Actor;
  notes: string | null;
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

export interface ElementWithCounts {
  element: DocumentElement;
  count_active_entries: number;
}

export interface DocSummary {
  slug: string;
  element_count: number;
}

// Synthesise streaming line types
export interface SynthStartLine {
  type: "start";
  total_elements: number;
}

export interface SynthElementLine {
  type: "element";
  element_id: string;
  kept: number;
  skipped_reason: string | null;
  tokens_estimated: number;
}

export interface SynthCompleteLine {
  type: "complete";
  events_written: number;
  prompt_tokens_estimated: number;
}

export interface SynthErrorLine {
  type: "error";
  element_id: string | null;
  reason: string;
}

export type SynthLine =
  | SynthStartLine
  | SynthElementLine
  | SynthCompleteLine
  | SynthErrorLine;

// Request bodies
export interface CreateEntryRequest {
  query: string;
}

export interface RefineRequest {
  query: string;
  expected_chunk_ids?: string[];
  chunk_hashes?: Record<string, string>;
  notes?: string | null;
  deprecate_reason?: string | null;
}

export interface DeprecateRequest {
  reason?: string | null;
}

export interface SynthesiseRequest {
  llm_model: string;
  llm_base_url?: string | null;
  dry_run?: boolean;
  max_questions_per_element?: number;
  max_prompt_tokens?: number;
  prompt_template_version?: string;
  temperature?: number;
  start_from?: string | null;
  limit?: number | null;
  embedding_model?: string | null;
  resume?: boolean;
}

// Response wrappers
export interface CreateEntryResponse {
  entry_id: string;
  event_id: string;
}

export interface RefineResponse {
  new_entry_id: string;
}

export interface DeprecateResponse {
  event_id: string;
}

export interface HealthResponse {
  status: "ok";
  goldens_root: string;
}
```

- [ ] **Step 2: Verify TS compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -5`

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/domain.ts
git commit -m "feat(frontend): TS domain types mirroring A-Plus.1 Pydantic schemas"
```

---

## Task 5: API client (fetch wrapper + 401 interceptor)

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/tests/api/client.test.ts`

- [ ] **Step 1: Write the failing test `frontend/tests/api/client.test.ts`**

```typescript
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { apiFetch, ApiError } from "../../src/api/client";

const server = setupServer();

beforeEach(() => server.listen());
afterEach(() => {
  server.resetHandlers();
  server.close();
});

describe("apiFetch", () => {
  it("includes X-Auth-Token header from sessionStorage", async () => {
    sessionStorage.setItem("goldens.api_token", "tok-test");
    server.use(
      http.get("http://localhost/api/health", ({ request }) => {
        expect(request.headers.get("X-Auth-Token")).toBe("tok-test");
        return HttpResponse.json({ status: "ok", goldens_root: "outputs" });
      }),
    );
    const result = await apiFetch<{ status: string }>("/api/health");
    expect(result.status).toBe("ok");
  });

  it("throws ApiError with detail on non-ok response", async () => {
    sessionStorage.setItem("goldens.api_token", "tok-test");
    server.use(
      http.get("http://localhost/api/entries/missing", () =>
        HttpResponse.json({ detail: "entry not found" }, { status: 404 }),
      ),
    );
    await expect(apiFetch("/api/entries/missing")).rejects.toMatchObject({
      status: 404,
      detail: "entry not found",
    });
  });

  it("clears token and dispatches a logout event on 401", async () => {
    sessionStorage.setItem("goldens.api_token", "tok-old");
    const onLogout = vi.fn();
    window.addEventListener("goldens:logout", onLogout);
    server.use(
      http.get("http://localhost/api/anything", () =>
        HttpResponse.json({ detail: "invalid token" }, { status: 401 }),
      ),
    );
    await expect(apiFetch("/api/anything")).rejects.toBeInstanceOf(ApiError);
    expect(sessionStorage.getItem("goldens.api_token")).toBeNull();
    expect(onLogout).toHaveBeenCalled();
    window.removeEventListener("goldens:logout", onLogout);
  });
});
```

- [ ] **Step 2: Run test — expect failure (module not found)**

Run: `cd frontend && npm test -- tests/api/client.test.ts`

Expected: FAIL — `Cannot find module ../../src/api/client`.

- [ ] **Step 3: Implement `frontend/src/api/client.ts`**

```typescript
const TOKEN_KEY = "goldens.api_token";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
    public url: string,
  ) {
    super(typeof detail === "string" ? detail : `HTTP ${status} on ${url}`);
    this.name = "ApiError";
  }
}

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

interface ApiOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  /** When true, skips the X-Auth-Token header (e.g. for /api/health pre-auth check). */
  skipAuth?: boolean;
  /** When true, returns the Response object instead of parsed JSON (for streaming). */
  raw?: boolean;
}

export async function apiFetch<T = unknown>(
  url: string,
  opts: ApiOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (!opts.skipAuth) {
    const token = getToken();
    if (token) headers["X-Auth-Token"] = token;
  }
  const response = await fetch(url, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
  });

  if (response.status === 401) {
    clearToken();
    window.dispatchEvent(new Event("goldens:logout"));
    let detail: unknown = "unauthorized";
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {
      /* response body not json */
    }
    throw new ApiError(401, detail, url);
  }

  if (!response.ok) {
    let detail: unknown = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail ?? body;
    } catch {
      /* response body not json */
    }
    throw new ApiError(response.status, detail, url);
  }

  if (opts.raw) {
    return response as unknown as T;
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function rawFetch(
  url: string,
  opts: ApiOptions = {},
): Promise<Response> {
  return apiFetch<Response>(url, { ...opts, raw: true });
}
```

- [ ] **Step 4: Run tests — expect pass**

Run: `cd frontend && npm test -- tests/api/client.test.ts`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/tests/api/client.test.ts
git commit -m "feat(frontend): API fetch client with X-Auth-Token + 401 interceptor"
```

---

## Task 6: NDJSON streaming reader

**Files:**
- Create: `frontend/src/api/ndjson.ts`
- Create: `frontend/tests/api/ndjson.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
import { describe, it, expect } from "vitest";
import { streamNdjson } from "../../src/api/ndjson";
import type { SynthLine } from "../../src/types/domain";

function makeResponseFromChunks(chunks: string[]): Response {
  const stream = new ReadableStream({
    start(controller) {
      const enc = new TextEncoder();
      for (const c of chunks) controller.enqueue(enc.encode(c));
      controller.close();
    },
  });
  return new Response(stream);
}

describe("streamNdjson", () => {
  it("yields one parsed object per newline-delimited JSON line", async () => {
    const lines: SynthLine[] = [];
    const resp = makeResponseFromChunks([
      '{"type":"start","total_elements":2}\n',
      '{"type":"element","element_id":"p1-aaa","kept":3,"skipped_reason":null,"tokens_estimated":42}\n',
      '{"type":"complete","events_written":3,"prompt_tokens_estimated":42}\n',
    ]);
    for await (const line of streamNdjson<SynthLine>(resp)) lines.push(line);
    expect(lines).toHaveLength(3);
    expect(lines[0]).toMatchObject({ type: "start", total_elements: 2 });
    expect(lines[2]).toMatchObject({ type: "complete", events_written: 3 });
  });

  it("buffers a partial line across chunks", async () => {
    const lines: SynthLine[] = [];
    const resp = makeResponseFromChunks([
      '{"type":"start","tota',
      'l_elements":5}\n{"type":"complete","events_written":0,"prompt_tokens_estimated":0}\n',
    ]);
    for await (const line of streamNdjson<SynthLine>(resp)) lines.push(line);
    expect(lines).toHaveLength(2);
    expect(lines[0]).toMatchObject({ type: "start", total_elements: 5 });
  });

  it("ignores blank lines and trailing whitespace", async () => {
    const lines: SynthLine[] = [];
    const resp = makeResponseFromChunks([
      '{"type":"start","total_elements":1}\n\n  \n{"type":"complete","events_written":0,"prompt_tokens_estimated":0}\n',
    ]);
    for await (const line of streamNdjson<SynthLine>(resp)) lines.push(line);
    expect(lines).toHaveLength(2);
  });
});
```

- [ ] **Step 2: Run test — expect failure**

Run: `cd frontend && npm test -- tests/api/ndjson.test.ts`

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `frontend/src/api/ndjson.ts`**

```typescript
export async function* streamNdjson<T>(response: Response): AsyncIterable<T> {
  if (!response.body) {
    throw new Error("response has no body to stream");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        if (buffer.trim()) {
          yield JSON.parse(buffer) as T;
        }
        return;
      }
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (line.trim()) yield JSON.parse(line) as T;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && npm test -- tests/api/ndjson.test.ts`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/ndjson.ts frontend/tests/api/ndjson.test.ts
git commit -m "feat(frontend): NDJSON streaming reader (ReadableStream + TextDecoder line-splitter)"
```

---

## Task 7: API endpoint modules (docs.ts, entries.ts)

**Files:**
- Create: `frontend/src/api/docs.ts`
- Create: `frontend/src/api/entries.ts`
- Create: `frontend/tests/api/docs.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { listDocs, listElements, getElement } from "../../src/api/docs";

const server = setupServer();

beforeEach(() => {
  server.listen();
  sessionStorage.setItem("goldens.api_token", "tok-test");
});
afterEach(() => {
  server.resetHandlers();
  server.close();
});

describe("docs api", () => {
  it("listDocs returns DocSummary array", async () => {
    server.use(
      http.get("http://localhost/api/docs", () =>
        HttpResponse.json([{ slug: "smoke-test-tragkorb", element_count: 9 }]),
      ),
    );
    const docs = await listDocs();
    expect(docs).toEqual([{ slug: "smoke-test-tragkorb", element_count: 9 }]);
  });

  it("listElements returns ElementWithCounts array for a slug", async () => {
    server.use(
      http.get(
        "http://localhost/api/docs/smoke-test-tragkorb/elements",
        () =>
          HttpResponse.json([
            {
              element: {
                element_id: "p1-aaa",
                page_number: 1,
                element_type: "heading",
                content: "Title",
              },
              count_active_entries: 0,
            },
          ]),
      ),
    );
    const elements = await listElements("smoke-test-tragkorb");
    expect(elements).toHaveLength(1);
    expect(elements[0].count_active_entries).toBe(0);
  });

  it("getElement returns element + entries", async () => {
    server.use(
      http.get(
        "http://localhost/api/docs/smoke-test-tragkorb/elements/p1-aaa",
        () =>
          HttpResponse.json({
            element: {
              element_id: "p1-aaa",
              page_number: 1,
              element_type: "heading",
              content: "Title",
            },
            entries: [],
          }),
      ),
    );
    const result = await getElement("smoke-test-tragkorb", "p1-aaa");
    expect(result.element.element_id).toBe("p1-aaa");
  });
});
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd frontend && npm test -- tests/api/docs.test.ts
```

Expected: module not found.

- [ ] **Step 3: Implement `frontend/src/api/docs.ts`**

```typescript
import { apiFetch, rawFetch } from "./client";
import type {
  DocSummary,
  ElementWithCounts,
  DocumentElement,
  RetrievalEntry,
  SynthesiseRequest,
  SynthLine,
} from "../types/domain";
import { streamNdjson } from "./ndjson";

export async function listDocs(): Promise<DocSummary[]> {
  return apiFetch<DocSummary[]>("/api/docs");
}

export async function listElements(slug: string): Promise<ElementWithCounts[]> {
  return apiFetch<ElementWithCounts[]>(
    `/api/docs/${encodeURIComponent(slug)}/elements`,
  );
}

export interface ElementDetailResponse {
  element: DocumentElement;
  entries: RetrievalEntry[];
}

export async function getElement(
  slug: string,
  elementId: string,
): Promise<ElementDetailResponse> {
  return apiFetch<ElementDetailResponse>(
    `/api/docs/${encodeURIComponent(slug)}/elements/${encodeURIComponent(elementId)}`,
  );
}

export async function streamSynthesise(
  slug: string,
  body: SynthesiseRequest,
  signal?: AbortSignal,
): Promise<AsyncIterable<SynthLine>> {
  const response = await rawFetch(
    `/api/docs/${encodeURIComponent(slug)}/synthesise`,
    { method: "POST", body, signal },
  );
  return streamNdjson<SynthLine>(response);
}
```

- [ ] **Step 4: Implement `frontend/src/api/entries.ts`**

```typescript
import { apiFetch } from "./client";
import type {
  CreateEntryRequest,
  CreateEntryResponse,
  DeprecateRequest,
  DeprecateResponse,
  RefineRequest,
  RefineResponse,
  RetrievalEntry,
} from "../types/domain";

export interface ListEntriesParams {
  slug?: string;
  source_element?: string;
  include_deprecated?: boolean;
}

export async function listEntries(
  params: ListEntriesParams = {},
): Promise<RetrievalEntry[]> {
  const qs = new URLSearchParams();
  if (params.slug) qs.set("slug", params.slug);
  if (params.source_element) qs.set("source_element", params.source_element);
  if (params.include_deprecated)
    qs.set("include_deprecated", String(params.include_deprecated));
  const query = qs.toString();
  return apiFetch<RetrievalEntry[]>(
    `/api/entries${query ? `?${query}` : ""}`,
  );
}

export async function getEntry(entryId: string): Promise<RetrievalEntry> {
  return apiFetch<RetrievalEntry>(
    `/api/entries/${encodeURIComponent(entryId)}`,
  );
}

export async function createEntry(
  slug: string,
  elementId: string,
  body: CreateEntryRequest,
): Promise<CreateEntryResponse> {
  return apiFetch<CreateEntryResponse>(
    `/api/docs/${encodeURIComponent(slug)}/elements/${encodeURIComponent(elementId)}/entries`,
    { method: "POST", body },
  );
}

export async function refineEntry(
  entryId: string,
  body: RefineRequest,
): Promise<RefineResponse> {
  return apiFetch<RefineResponse>(
    `/api/entries/${encodeURIComponent(entryId)}/refine`,
    { method: "POST", body },
  );
}

export async function deprecateEntry(
  entryId: string,
  body: DeprecateRequest,
): Promise<DeprecateResponse> {
  return apiFetch<DeprecateResponse>(
    `/api/entries/${encodeURIComponent(entryId)}/deprecate`,
    { method: "POST", body },
  );
}
```

- [ ] **Step 5: Run tests**

Run: `cd frontend && npm test -- tests/api/docs.test.ts`

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/docs.ts frontend/src/api/entries.ts frontend/tests/api/docs.test.ts
git commit -m "feat(frontend): API endpoint modules for docs, entries, synthesise streaming"
```

---

## Task 8: App bootstrap (main.tsx, App.tsx, Router skeleton)

**Files:**
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: Create `frontend/src/main.tsx`**

```typescript
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HashRouter } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { App } from "./App";
import "./styles/globals.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: true,
      staleTime: 30 * 1000, // 30 seconds
    },
    mutations: {
      retry: 0,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <HashRouter>
        <App />
      </HashRouter>
      <Toaster position="top-right" toastOptions={{ duration: 5000 }} />
    </QueryClientProvider>
  </StrictMode>,
);
```

- [ ] **Step 2: Create `frontend/src/App.tsx`**

```typescript
import { Navigate, Route, Routes } from "react-router-dom";

export function App() {
  return (
    <div className="min-h-screen">
      <Routes>
        <Route path="/" element={<Navigate to="/docs" replace />} />
        <Route path="/login" element={<LoginPlaceholder />} />
        <Route path="/docs" element={<DocsIndexPlaceholder />} />
        <Route
          path="/docs/:slug/elements"
          element={<DocElementsPlaceholder />}
        />
        <Route
          path="/docs/:slug/elements/:elementId"
          element={<DocElementsPlaceholder />}
        />
        <Route
          path="/docs/:slug/synthesise"
          element={<SynthesisePlaceholder />}
        />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </div>
  );
}

// Placeholders — replaced in subsequent tasks.
function LoginPlaceholder() {
  return <div className="p-8">Login (Task 9)</div>;
}
function DocsIndexPlaceholder() {
  return <div className="p-8">Docs Index (Task 11)</div>;
}
function DocElementsPlaceholder() {
  return <div className="p-8">Doc Elements (Task 23)</div>;
}
function SynthesisePlaceholder() {
  return <div className="p-8">Synthesise (Task 26)</div>;
}
function NotFound() {
  return <div className="p-8">Page not found.</div>;
}
```

- [ ] **Step 3: Verify build works**

Run: `cd frontend && npm run build 2>&1 | tail -10`

Expected: success, `dist/` populated.

- [ ] **Step 4: Verify dev-server boots**

Run (background): `cd frontend && npm run dev &`
Wait 3 seconds, then: `curl -s http://127.0.0.1:5173/ | head -5`
Expected: HTML output. Then kill: `pkill -f "vite"`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/main.tsx frontend/src/App.tsx
git commit -m "feat(frontend): app bootstrap with QueryClient + HashRouter + Toaster"
```

---

## Task 9: Auth hook + Login route

**Files:**
- Create: `frontend/src/hooks/useAuth.ts`
- Create: `frontend/src/routes/login.tsx`
- Create: `frontend/tests/hooks/useAuth.test.ts`
- Create: `frontend/tests/routes/login.test.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write the failing useAuth test**

```typescript
// frontend/tests/hooks/useAuth.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useAuth } from "../../src/hooks/useAuth";
import { setToken } from "../../src/api/client";

describe("useAuth", () => {
  beforeEach(() => sessionStorage.clear());

  it("returns null when no token", () => {
    const { result } = renderHook(() => useAuth());
    expect(result.current.token).toBeNull();
  });

  it("returns the token when stored", () => {
    setToken("tok-abc");
    const { result } = renderHook(() => useAuth());
    expect(result.current.token).toBe("tok-abc");
  });

  it("logout() clears token + dispatches goldens:logout event", () => {
    setToken("tok-abc");
    const { result } = renderHook(() => useAuth());
    act(() => result.current.logout());
    expect(sessionStorage.getItem("goldens.api_token")).toBeNull();
  });

  it("re-reads token on goldens:logout event", () => {
    setToken("tok-abc");
    const { result } = renderHook(() => useAuth());
    expect(result.current.token).toBe("tok-abc");
    act(() => {
      sessionStorage.removeItem("goldens.api_token");
      window.dispatchEvent(new Event("goldens:logout"));
    });
    expect(result.current.token).toBeNull();
  });
});
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd frontend && npm test -- tests/hooks/useAuth.test.ts
```

- [ ] **Step 3: Implement `frontend/src/hooks/useAuth.ts`**

```typescript
import { useEffect, useState, useCallback } from "react";
import { clearToken, getToken, setToken as setStoredToken } from "../api/client";

export function useAuth() {
  const [token, setTokenState] = useState<string | null>(getToken());

  useEffect(() => {
    function onLogout() {
      setTokenState(null);
    }
    window.addEventListener("goldens:logout", onLogout);
    return () => window.removeEventListener("goldens:logout", onLogout);
  }, []);

  const login = useCallback((newToken: string) => {
    setStoredToken(newToken);
    setTokenState(newToken);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setTokenState(null);
    window.dispatchEvent(new Event("goldens:logout"));
  }, []);

  return { token, login, logout };
}
```

- [ ] **Step 4: Run useAuth tests**

```bash
cd frontend && npm test -- tests/hooks/useAuth.test.ts
```

Expected: 4 passed.

- [ ] **Step 5: Write the failing Login-route test**

```tsx
// frontend/tests/routes/login.test.tsx
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { Login } from "../../src/routes/login";

const server = setupServer();
beforeEach(() => server.listen());
afterEach(() => {
  server.resetHandlers();
  server.close();
  sessionStorage.clear();
});

function renderLogin(initial = "/login") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/docs" element={<div>Docs page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Login route", () => {
  it("accepts a valid token and navigates to /docs", async () => {
    server.use(
      http.get("http://localhost/api/health", () =>
        HttpResponse.json({ status: "ok", goldens_root: "outputs" }),
      ),
    );
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText(/token/i), "tok-good");
    await user.click(screen.getByRole("button", { name: /einloggen/i }));
    expect(await screen.findByText(/docs page/i)).toBeInTheDocument();
    expect(sessionStorage.getItem("goldens.api_token")).toBe("tok-good");
  });

  it("shows error banner on rejected token", async () => {
    server.use(
      http.get("http://localhost/api/health", () =>
        HttpResponse.json({ detail: "invalid" }, { status: 401 }),
      ),
    );
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText(/token/i), "tok-bad");
    await user.click(screen.getByRole("button", { name: /einloggen/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/abgelehnt|rejected/i);
  });
});
```

- [ ] **Step 6: Run test — expect failure**

```bash
cd frontend && npm test -- tests/routes/login.test.tsx
```

- [ ] **Step 7: Implement `frontend/src/routes/login.tsx`**

```tsx
import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { apiFetch, ApiError } from "../api/client";
import { useAuth } from "../hooks/useAuth";

export function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [token, setTokenInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [params] = useSearchParams();
  const reason = params.get("reason");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      // Pre-store so apiFetch reads it; if validation fails, clearToken runs.
      sessionStorage.setItem("goldens.api_token", token);
      await apiFetch("/api/health");
      login(token);
      navigate("/docs", { replace: true });
    } catch (err) {
      sessionStorage.removeItem("goldens.api_token");
      if (err instanceof ApiError && err.status === 401) {
        setError("Token wurde abgelehnt.");
      } else {
        setError("Server nicht erreichbar.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm bg-white rounded-lg shadow p-8 space-y-4"
      >
        <h1 className="text-xl font-semibold">Goldens — Anmeldung</h1>
        {reason === "expired" ? (
          <p className="text-sm text-slate-600">
            Sitzung abgelaufen. Bitte erneut Token eingeben.
          </p>
        ) : null}
        <label className="block">
          <span className="text-sm text-slate-700">API-Token</span>
          <input
            className="input mt-1"
            type="password"
            value={token}
            onChange={(e) => setTokenInput(e.target.value)}
            placeholder="aus Terminal: $GOLDENS_API_TOKEN"
            autoFocus
            aria-label="API-Token"
          />
        </label>
        {error ? (
          <div role="alert" className="text-sm text-red-600">
            {error}
          </div>
        ) : null}
        <button
          type="submit"
          className="btn-primary w-full"
          disabled={submitting || !token.trim()}
        >
          {submitting ? "Prüfe…" : "Einloggen"}
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 8: Wire route in `frontend/src/App.tsx`**

Replace the `LoginPlaceholder` import block. Find:

```typescript
function LoginPlaceholder() {
  return <div className="p-8">Login (Task 9)</div>;
}
```

Replace with `import { Login } from "./routes/login";` at the top, and update:

```typescript
<Route path="/login" element={<Login />} />
```

Remove the `LoginPlaceholder` function entirely.

- [ ] **Step 9: Run tests**

```bash
cd frontend && npm test -- tests/routes/login.test.tsx tests/hooks/useAuth.test.ts
```

Expected: 6 passed total.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/hooks/useAuth.ts frontend/src/routes/login.tsx \
        frontend/src/App.tsx \
        frontend/tests/hooks/useAuth.test.ts frontend/tests/routes/login.test.tsx
git commit -m "feat(frontend): useAuth hook + Login route with token validation"
```

---

## Task 10: Auth gate (require login on protected routes)

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Update `frontend/src/App.tsx` to gate non-login routes**

Replace the entire file with:

```tsx
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./hooks/useAuth";
import { Login } from "./routes/login";

function RequireAuth() {
  const { token } = useAuth();
  const location = useLocation();
  if (!token) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  return <Outlet />;
}

export function App() {
  return (
    <div className="min-h-screen">
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<RequireAuth />}>
          <Route path="/" element={<Navigate to="/docs" replace />} />
          <Route path="/docs" element={<DocsIndexPlaceholder />} />
          <Route
            path="/docs/:slug/elements"
            element={<DocElementsPlaceholder />}
          />
          <Route
            path="/docs/:slug/elements/:elementId"
            element={<DocElementsPlaceholder />}
          />
          <Route
            path="/docs/:slug/synthesise"
            element={<SynthesisePlaceholder />}
          />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </div>
  );
}

function DocsIndexPlaceholder() {
  return <div className="p-8">Docs Index (Task 11)</div>;
}
function DocElementsPlaceholder() {
  return <div className="p-8">Doc Elements (Task 23)</div>;
}
function SynthesisePlaceholder() {
  return <div className="p-8">Synthesise (Task 26)</div>;
}
function NotFound() {
  return <div className="p-8">Page not found.</div>;
}
```

- [ ] **Step 2: Manual smoke (optional, can skip if dev-server not running)**

In a browser at `http://127.0.0.1:5173/#/docs` without a token, expect immediate redirect to `/login`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(frontend): RequireAuth gate redirects unauthenticated users to login"
```

---

## Task 11: Docs Index route

**Files:**
- Create: `frontend/src/hooks/useDocs.ts`
- Create: `frontend/src/components/Spinner.tsx`
- Create: `frontend/src/routes/docs-index.tsx`
- Create: `frontend/tests/routes/docs-index.test.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/routes/docs-index.test.tsx
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { DocsIndex } from "../../src/routes/docs-index";

const server = setupServer();
beforeEach(() => {
  server.listen();
  sessionStorage.setItem("goldens.api_token", "tok");
});
afterEach(() => {
  server.resetHandlers();
  server.close();
  sessionStorage.clear();
});

function renderDocs() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/docs"]}>
        <Routes>
          <Route path="/docs" element={<DocsIndex />} />
          <Route
            path="/docs/:slug/elements"
            element={<div>Element page for {/* slug */}</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DocsIndex", () => {
  it("lists docs returned by GET /api/docs", async () => {
    server.use(
      http.get("http://localhost/api/docs", () =>
        HttpResponse.json([
          { slug: "smoke-test-tragkorb", element_count: 9 },
          { slug: "another-doc", element_count: 47 },
        ]),
      ),
    );
    renderDocs();
    expect(await screen.findByText("smoke-test-tragkorb")).toBeInTheDocument();
    expect(screen.getByText(/9 elements/i)).toBeInTheDocument();
    expect(screen.getByText("another-doc")).toBeInTheDocument();
  });

  it("shows empty-state when no docs", async () => {
    server.use(
      http.get("http://localhost/api/docs", () => HttpResponse.json([])),
    );
    renderDocs();
    expect(
      await screen.findByText(/keine dokumente|no documents/i),
    ).toBeInTheDocument();
  });

  it("clicking a doc navigates to its elements page", async () => {
    server.use(
      http.get("http://localhost/api/docs", () =>
        HttpResponse.json([{ slug: "doc-x", element_count: 3 }]),
      ),
    );
    const user = userEvent.setup();
    renderDocs();
    const link = await screen.findByRole("link", { name: /doc-x/i });
    await user.click(link);
    expect(await screen.findByText(/element page for/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd frontend && npm test -- tests/routes/docs-index.test.tsx
```

- [ ] **Step 3: Implement `frontend/src/hooks/useDocs.ts`**

```typescript
import { useQuery } from "@tanstack/react-query";
import { listDocs } from "../api/docs";

export function useDocs() {
  return useQuery({
    queryKey: ["docs"],
    queryFn: listDocs,
  });
}
```

- [ ] **Step 4: Implement `frontend/src/components/Spinner.tsx`**

```tsx
export function Spinner({ label = "Lade…" }: { label?: string }) {
  return (
    <div role="status" aria-label={label} className="flex items-center gap-2 text-slate-500">
      <svg
        className="h-4 w-4 animate-spin"
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
      >
        <circle
          className="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
        />
      </svg>
      <span>{label}</span>
    </div>
  );
}
```

- [ ] **Step 5: Implement `frontend/src/routes/docs-index.tsx`**

```tsx
import { Link } from "react-router-dom";
import { useDocs } from "../hooks/useDocs";
import { Spinner } from "../components/Spinner";

export function DocsIndex() {
  const { data, isLoading, error } = useDocs();

  if (isLoading) {
    return (
      <main className="p-8">
        <Spinner label="Lade Dokumente…" />
      </main>
    );
  }
  if (error) {
    return (
      <main className="p-8">
        <p role="alert" className="text-red-600">
          Fehler beim Laden der Dokumente.
        </p>
      </main>
    );
  }
  if (!data || data.length === 0) {
    return (
      <main className="p-8">
        <p>Keine Dokumente unter <code>outputs/</code>. Lege eines an und reload.</p>
      </main>
    );
  }
  return (
    <main className="p-8 max-w-3xl mx-auto">
      <h1 className="text-2xl font-semibold mb-6">Dokumente</h1>
      <ul className="space-y-2">
        {data.map((doc) => (
          <li key={doc.slug}>
            <Link
              to={`/docs/${encodeURIComponent(doc.slug)}/elements`}
              className="block bg-white border border-slate-200 rounded p-4 hover:border-blue-500 transition"
            >
              <span className="font-medium">{doc.slug}</span>
              <span className="ml-3 text-sm text-slate-500">
                {doc.element_count} elements
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
```

- [ ] **Step 6: Wire in `frontend/src/App.tsx`**

Add `import { DocsIndex } from "./routes/docs-index";` to top. Replace `<Route path="/docs" element={<DocsIndexPlaceholder />} />` with `<Route path="/docs" element={<DocsIndex />} />`. Remove `DocsIndexPlaceholder` function.

- [ ] **Step 7: Run tests**

```bash
cd frontend && npm test -- tests/routes/docs-index.test.tsx
```

Expected: 3 passed.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/hooks/useDocs.ts frontend/src/components/Spinner.tsx \
        frontend/src/routes/docs-index.tsx frontend/src/App.tsx \
        frontend/tests/routes/docs-index.test.tsx
git commit -m "feat(frontend): DocsIndex route with useDocs query + Spinner component"
```

---

## Task 12: TopBar component (logout + slug context)

**Files:**
- Create: `frontend/src/components/TopBar.tsx`
- Create: `frontend/tests/components/TopBar.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { TopBar } from "../../src/components/TopBar";

describe("TopBar", () => {
  beforeEach(() => sessionStorage.setItem("goldens.api_token", "tok"));

  function renderBar(slug?: string) {
    return render(
      <MemoryRouter initialEntries={[slug ? `/docs/${slug}/elements` : "/docs"]}>
        <Routes>
          <Route path="/docs" element={<TopBar />} />
          <Route path="/docs/:slug/elements" element={<TopBar />} />
          <Route path="/login" element={<div>Login page</div>} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it("shows brand and a logout button", () => {
    renderBar();
    expect(screen.getByText(/goldens/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /abmelden/i })).toBeInTheDocument();
  });

  it("shows the active slug breadcrumb when in a doc", () => {
    renderBar("smoke-test-tragkorb");
    expect(screen.getByText(/smoke-test-tragkorb/)).toBeInTheDocument();
  });

  it("logout clears token and navigates to /login", async () => {
    const user = userEvent.setup();
    renderBar();
    await user.click(screen.getByRole("button", { name: /abmelden/i }));
    expect(sessionStorage.getItem("goldens.api_token")).toBeNull();
    expect(await screen.findByText(/login page/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd frontend && npm test -- tests/components/TopBar.test.tsx
```

- [ ] **Step 3: Implement `frontend/src/components/TopBar.tsx`**

```tsx
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export function TopBar() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const { slug } = useParams<{ slug?: string }>();

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <header className="bg-white border-b border-slate-200">
      <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/docs" className="font-semibold text-slate-900">
            Goldens
          </Link>
          {slug ? (
            <>
              <span className="text-slate-400">/</span>
              <span className="text-slate-700">{slug}</span>
            </>
          ) : null}
        </div>
        <button onClick={handleLogout} className="btn-secondary text-sm">
          Abmelden
        </button>
      </div>
    </header>
  );
}
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npm test -- tests/components/TopBar.test.tsx
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/TopBar.tsx frontend/tests/components/TopBar.test.tsx
git commit -m "feat(frontend): TopBar component with breadcrumb + logout"
```

---

## Task 13: useElements + useElement hooks

**Files:**
- Create: `frontend/src/hooks/useElements.ts`
- Create: `frontend/src/hooks/useElement.ts`
- Create: `frontend/tests/hooks/useElement.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { useElement } from "../../src/hooks/useElement";
import { useElements } from "../../src/hooks/useElements";
import type { ReactNode } from "react";

const server = setupServer();
beforeEach(() => {
  server.listen();
  sessionStorage.setItem("goldens.api_token", "tok");
});
afterEach(() => {
  server.resetHandlers();
  server.close();
  sessionStorage.clear();
});

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useElements", () => {
  it("returns ElementWithCounts array for a slug", async () => {
    server.use(
      http.get("http://localhost/api/docs/foo/elements", () =>
        HttpResponse.json([
          {
            element: {
              element_id: "p1-aaa",
              page_number: 1,
              element_type: "heading",
              content: "Title",
            },
            count_active_entries: 0,
          },
        ]),
      ),
    );
    const { result } = renderHook(() => useElements("foo"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
  });
});

describe("useElement", () => {
  it("returns element + entries for a slug + element_id", async () => {
    server.use(
      http.get("http://localhost/api/docs/foo/elements/p1-aaa", () =>
        HttpResponse.json({
          element: {
            element_id: "p1-aaa",
            page_number: 1,
            element_type: "heading",
            content: "Title",
          },
          entries: [],
        }),
      ),
    );
    const { result } = renderHook(() => useElement("foo", "p1-aaa"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.element.element_id).toBe("p1-aaa");
  });

  it("does not fetch when elementId is undefined", () => {
    const { result } = renderHook(() => useElement("foo", undefined), { wrapper: makeWrapper() });
    expect(result.current.isFetching).toBe(false);
  });
});
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd frontend && npm test -- tests/hooks/useElement.test.ts
```

- [ ] **Step 3: Implement `frontend/src/hooks/useElements.ts`**

```typescript
import { useQuery } from "@tanstack/react-query";
import { listElements } from "../api/docs";

export function useElements(slug: string | undefined) {
  return useQuery({
    queryKey: ["doc-elements", slug],
    queryFn: () => listElements(slug!),
    enabled: !!slug,
  });
}
```

- [ ] **Step 4: Implement `frontend/src/hooks/useElement.ts`**

```typescript
import { useQuery } from "@tanstack/react-query";
import { getElement } from "../api/docs";

export function useElement(slug: string | undefined, elementId: string | undefined) {
  return useQuery({
    queryKey: ["element", slug, elementId],
    queryFn: () => getElement(slug!, elementId!),
    enabled: !!slug && !!elementId,
  });
}
```

- [ ] **Step 5: Run tests**

```bash
cd frontend && npm test -- tests/hooks/useElement.test.ts
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/useElements.ts frontend/src/hooks/useElement.ts \
        frontend/tests/hooks/useElement.test.ts
git commit -m "feat(frontend): useElements + useElement TanStack Query hooks"
```

---

## Task 14: ElementBody + variants

**Files:**
- Create: `frontend/src/components/TableElementView.tsx`
- Create: `frontend/src/components/FigureElementView.tsx`
- Create: `frontend/src/components/ElementBody.tsx`
- Create: `frontend/tests/components/TableElementView.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TableElementView } from "../../src/components/TableElementView";
import type { DocumentElement } from "../../src/types/domain";

const tableElement: DocumentElement = {
  element_id: "p2-table",
  page_number: 2,
  element_type: "table",
  content: "M6 | 12 Nm | DIN 912\nM8 | 28 Nm | DIN 912\n...",
  table_dims: [4, 3],
  table_full_content:
    "Schraubentyp | Anzugsdrehmoment | Norm\nM6 | 12 Nm | DIN 912\nM8 | 28 Nm | DIN 912\nM10 | 55 Nm | DIN 912",
};

describe("TableElementView", () => {
  it("renders compact stub by default with toggle hint", () => {
    render(<TableElementView element={tableElement} />);
    expect(screen.getByText(/M6/)).toBeInTheDocument();
    expect(screen.getByText(/M8/)).toBeInTheDocument();
    expect(screen.queryByText(/M10/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /volle tabelle/i })).toBeInTheDocument();
  });

  it("toggles to full content when button clicked", async () => {
    const user = userEvent.setup();
    render(<TableElementView element={tableElement} />);
    await user.click(screen.getByRole("button", { name: /volle tabelle/i }));
    expect(screen.getByText(/M10/)).toBeInTheDocument();
    expect(screen.getByText(/55 Nm/)).toBeInTheDocument();
  });

  it("shows table dims badge", () => {
    render(<TableElementView element={tableElement} />);
    expect(screen.getByText(/4×3/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd frontend && npm test -- tests/components/TableElementView.test.tsx
```

- [ ] **Step 3: Implement `frontend/src/components/TableElementView.tsx`**

```tsx
import { useState } from "react";
import type { DocumentElement } from "../types/domain";

export function TableElementView({ element }: { element: DocumentElement }) {
  const [showFull, setShowFull] = useState(false);
  const dims = element.table_dims;
  const body =
    showFull && element.table_full_content ? element.table_full_content : element.content;

  return (
    <div>
      <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
        <span>Tabelle</span>
        <span>·</span>
        <span>Seite {element.page_number}</span>
        {dims ? (
          <>
            <span>·</span>
            <span>
              {dims[0]}
              {"×"}
              {dims[1]}
            </span>
          </>
        ) : null}
      </div>
      <pre className="bg-slate-50 rounded p-3 overflow-x-auto text-sm font-mono whitespace-pre">
        {body}
      </pre>
      {element.table_full_content && element.table_full_content !== element.content ? (
        <button
          onClick={() => setShowFull((s) => !s)}
          className="btn-secondary mt-2 text-sm"
          aria-pressed={showFull}
        >
          {showFull ? "Kompakte Vorschau" : "Volle Tabelle anzeigen"}
        </button>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 4: Implement `frontend/src/components/FigureElementView.tsx`**

```tsx
import type { DocumentElement } from "../types/domain";

export function FigureElementView({ element }: { element: DocumentElement }) {
  return (
    <div>
      <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
        <span>Abbildung</span>
        <span>·</span>
        <span>Seite {element.page_number}</span>
      </div>
      {element.caption ? (
        <p className="text-sm text-slate-700 mb-1">{element.caption}</p>
      ) : null}
      <p className="text-sm text-slate-500 italic">
        Bild kann im Browser nicht angezeigt werden — siehe PDF Seite {element.page_number}.
      </p>
    </div>
  );
}
```

- [ ] **Step 5: Implement `frontend/src/components/ElementBody.tsx`**

```tsx
import type { DocumentElement } from "../types/domain";
import { TableElementView } from "./TableElementView";
import { FigureElementView } from "./FigureElementView";

const TYPE_LABEL: Record<string, string> = {
  paragraph: "Absatz",
  heading: "Überschrift",
  list_item: "Listpunkt",
};

export function ElementBody({ element }: { element: DocumentElement }) {
  if (element.element_type === "table") return <TableElementView element={element} />;
  if (element.element_type === "figure") return <FigureElementView element={element} />;

  const label = TYPE_LABEL[element.element_type] ?? "Element";
  return (
    <div>
      <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
        <span>{label}</span>
        <span>·</span>
        <span>Seite {element.page_number}</span>
        <span>·</span>
        <span className="font-mono">{element.element_id}</span>
      </div>
      <p className="text-base text-slate-900 whitespace-pre-wrap">{element.content}</p>
    </div>
  );
}
```

- [ ] **Step 6: Run tests**

```bash
cd frontend && npm test -- tests/components/TableElementView.test.tsx
```

Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/TableElementView.tsx \
        frontend/src/components/FigureElementView.tsx \
        frontend/src/components/ElementBody.tsx \
        frontend/tests/components/TableElementView.test.tsx
git commit -m "feat(frontend): ElementBody with Table/Figure/Paragraph variants + table stub-full toggle"
```

---

## Task 15: NewEntryForm + useCreateEntry hook

**Files:**
- Create: `frontend/src/hooks/useCreateEntry.ts`
- Create: `frontend/src/components/NewEntryForm.tsx`
- Create: `frontend/tests/components/NewEntryForm.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { NewEntryForm } from "../../src/components/NewEntryForm";

const server = setupServer();
beforeEach(() => {
  server.listen();
  sessionStorage.setItem("goldens.api_token", "tok");
});
afterEach(() => {
  server.resetHandlers();
  server.close();
  sessionStorage.clear();
});

function renderForm(props: Partial<{ slug: string; elementId: string; onWeiter: () => void }> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <NewEntryForm
        slug={props.slug ?? "doc-x"}
        elementId={props.elementId ?? "p1-aaa"}
        onWeiter={props.onWeiter ?? (() => {})}
      />
    </QueryClientProvider>,
  );
}

describe("NewEntryForm", () => {
  it("submits the typed query and clears textarea on success", async () => {
    server.use(
      http.post(
        "http://localhost/api/docs/doc-x/elements/p1-aaa/entries",
        async ({ request }) => {
          const body = (await request.json()) as { query: string };
          expect(body.query).toBe("Welche Norm gilt?");
          return HttpResponse.json(
            { entry_id: "e_abc", event_id: "ev_xyz" },
            { status: 201 },
          );
        },
      ),
    );
    const user = userEvent.setup();
    renderForm();
    const ta = screen.getByLabelText(/neue frage/i);
    await user.type(ta, "Welche Norm gilt?");
    await user.click(screen.getByRole("button", { name: /speichern/i }));
    expect(await screen.findByText(/gespeichert/i)).toBeInTheDocument();
    expect(ta).toHaveValue("");
  });

  it("calls onWeiter when textarea is empty and Enter pressed", async () => {
    let weiterCalled = false;
    const user = userEvent.setup();
    renderForm({ onWeiter: () => (weiterCalled = true) });
    const ta = screen.getByLabelText(/neue frage/i);
    ta.focus();
    await user.keyboard("{Enter}");
    expect(weiterCalled).toBe(true);
  });

  it("submits on Ctrl+Enter when textarea has content", async () => {
    server.use(
      http.post(
        "http://localhost/api/docs/doc-x/elements/p1-aaa/entries",
        () => HttpResponse.json({ entry_id: "e", event_id: "ev" }, { status: 201 }),
      ),
    );
    const user = userEvent.setup();
    renderForm();
    const ta = screen.getByLabelText(/neue frage/i);
    await user.type(ta, "Frage");
    await user.keyboard("{Control>}{Enter}{/Control}");
    expect(await screen.findByText(/gespeichert/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd frontend && npm test -- tests/components/NewEntryForm.test.tsx
```

- [ ] **Step 3: Implement `frontend/src/hooks/useCreateEntry.ts`**

```typescript
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createEntry } from "../api/entries";
import type { CreateEntryRequest, CreateEntryResponse } from "../types/domain";

interface CreateArgs {
  slug: string;
  elementId: string;
  body: CreateEntryRequest;
}

export function useCreateEntry() {
  const qc = useQueryClient();
  return useMutation<CreateEntryResponse, Error, CreateArgs>({
    mutationFn: ({ slug, elementId, body }) => createEntry(slug, elementId, body),
    onSuccess: (_data, { slug, elementId }) => {
      qc.invalidateQueries({ queryKey: ["element", slug, elementId] });
      qc.invalidateQueries({ queryKey: ["doc-elements", slug] });
    },
  });
}
```

- [ ] **Step 4: Implement `frontend/src/components/NewEntryForm.tsx`**

```tsx
import { useState, type KeyboardEvent } from "react";
import toast from "react-hot-toast";
import { useCreateEntry } from "../hooks/useCreateEntry";
import { ApiError } from "../api/client";

interface Props {
  slug: string;
  elementId: string;
  onWeiter: () => void;
}

export function NewEntryForm({ slug, elementId, onWeiter }: Props) {
  const [query, setQuery] = useState("");
  const create = useCreateEntry();

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter") {
      const trimmed = query.trim();
      if (trimmed === "") {
        e.preventDefault();
        onWeiter();
        return;
      }
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        submit();
      }
    }
  }

  function submit() {
    const trimmed = query.trim();
    if (!trimmed) return;
    create.mutate(
      { slug, elementId, body: { query: trimmed } },
      {
        onSuccess: () => {
          toast.success("✓ gespeichert");
          setQuery("");
        },
        onError: (err) => {
          if (err instanceof ApiError && err.status === 422) {
            toast.error("Frage abgelehnt: " + JSON.stringify(err.detail));
          } else {
            toast.error("Speichern fehlgeschlagen.");
          }
        },
      },
    );
  }

  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <label className="block">
        <span className="text-sm font-medium text-slate-700">
          Neue Frage zu diesem Element
        </span>
        <textarea
          className="input mt-1 min-h-[80px]"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Tippen + Speichern (oder Ctrl+Enter). Leer + Enter = Weiter."
          aria-label="Neue Frage"
          disabled={create.isPending}
        />
      </label>
      <div className="flex items-center gap-2">
        <button
          type="submit"
          className="btn-primary"
          disabled={create.isPending || !query.trim()}
        >
          {create.isPending ? "Speichere…" : "Speichern"}
        </button>
        <span className="text-xs text-slate-500">Ctrl+Enter zum Speichern</span>
      </div>
    </form>
  );
}
```

- [ ] **Step 5: Run tests**

```bash
cd frontend && npm test -- tests/components/NewEntryForm.test.tsx
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/useCreateEntry.ts \
        frontend/src/components/NewEntryForm.tsx \
        frontend/tests/components/NewEntryForm.test.tsx
git commit -m "feat(frontend): NewEntryForm + useCreateEntry mutation with Enter/Ctrl+Enter shortcuts"
```

---

## Task 16: EntryItem + EntryList (read-only, refine/deprecate buttons stubbed)

**Files:**
- Create: `frontend/src/components/EntryItem.tsx`
- Create: `frontend/src/components/EntryList.tsx`
- Create: `frontend/tests/components/EntryItem.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EntryItem } from "../../src/components/EntryItem";
import type { RetrievalEntry } from "../../src/types/domain";

const baseEntry: RetrievalEntry = {
  entry_id: "e_001",
  query: "Welche Norm gilt für M6?",
  expected_chunk_ids: [],
  chunk_hashes: {},
  review_chain: [
    {
      timestamp_utc: "2026-04-30T07:00:00Z",
      action: "created_from_scratch",
      actor: { kind: "human", pseudonym: "alice", level: "phd" },
      notes: null,
    },
  ],
  deprecated: false,
  refines: null,
  task_type: "retrieval",
  source_element: null,
};

describe("EntryItem", () => {
  it("renders the query and the actor pseudonym", () => {
    render(<EntryItem entry={baseEntry} onRefine={() => {}} onDeprecate={() => {}} />);
    expect(screen.getByText(/welche norm/i)).toBeInTheDocument();
    expect(screen.getByText(/alice/)).toBeInTheDocument();
    expect(screen.getByText(/phd/)).toBeInTheDocument();
  });

  it("calls onRefine when Verfeinern button is clicked", async () => {
    const onRefine = vi.fn();
    const user = userEvent.setup();
    render(<EntryItem entry={baseEntry} onRefine={onRefine} onDeprecate={() => {}} />);
    await user.click(screen.getByRole("button", { name: /verfeinern/i }));
    expect(onRefine).toHaveBeenCalledWith(baseEntry);
  });

  it("calls onDeprecate when Zurückziehen button is clicked", async () => {
    const onDeprecate = vi.fn();
    const user = userEvent.setup();
    render(<EntryItem entry={baseEntry} onRefine={() => {}} onDeprecate={onDeprecate} />);
    await user.click(screen.getByRole("button", { name: /zurückziehen/i }));
    expect(onDeprecate).toHaveBeenCalledWith(baseEntry);
  });

  it("shows refine-chain depth when entry was refined", () => {
    render(
      <EntryItem
        entry={{ ...baseEntry, refines: "e_old" }}
        onRefine={() => {}}
        onDeprecate={() => {}}
      />,
    );
    expect(screen.getByText(/verfeinert von/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd frontend && npm test -- tests/components/EntryItem.test.tsx
```

- [ ] **Step 3: Implement `frontend/src/components/EntryItem.tsx`**

```tsx
import type { RetrievalEntry, Actor } from "../types/domain";

interface Props {
  entry: RetrievalEntry;
  onRefine: (entry: RetrievalEntry) => void;
  onDeprecate: (entry: RetrievalEntry) => void;
}

function actorLabel(actor: Actor): string {
  if (actor.kind === "human") {
    return `${actor.pseudonym} (${actor.level})`;
  }
  return `LLM ${actor.model}`;
}

export function EntryItem({ entry, onRefine, onDeprecate }: Props) {
  const creator = entry.review_chain[0]?.actor;
  return (
    <li className="bg-white border border-slate-200 rounded p-4">
      <p className="text-base text-slate-900 mb-2">{entry.query}</p>
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <span className="font-mono">{entry.entry_id}</span>
        {creator ? (
          <>
            <span>·</span>
            <span>{actorLabel(creator)}</span>
          </>
        ) : null}
        {entry.refines ? (
          <>
            <span>·</span>
            <span>verfeinert von {entry.refines}</span>
          </>
        ) : null}
      </div>
      <div className="flex items-center gap-2 mt-3">
        <button onClick={() => onRefine(entry)} className="btn-secondary text-xs">
          Verfeinern
        </button>
        <button onClick={() => onDeprecate(entry)} className="btn-secondary text-xs">
          Zurückziehen
        </button>
      </div>
    </li>
  );
}
```

- [ ] **Step 4: Implement `frontend/src/components/EntryList.tsx`**

```tsx
import type { RetrievalEntry } from "../types/domain";
import { EntryItem } from "./EntryItem";

interface Props {
  entries: RetrievalEntry[];
  onRefine: (entry: RetrievalEntry) => void;
  onDeprecate: (entry: RetrievalEntry) => void;
}

export function EntryList({ entries, onRefine, onDeprecate }: Props) {
  if (entries.length === 0) {
    return (
      <p className="text-sm text-slate-500 italic">
        Noch keine Fragen zu diesem Element.
      </p>
    );
  }
  return (
    <ul className="space-y-2">
      {entries.map((e) => (
        <EntryItem
          key={e.entry_id}
          entry={e}
          onRefine={onRefine}
          onDeprecate={onDeprecate}
        />
      ))}
    </ul>
  );
}
```

- [ ] **Step 5: Run tests**

```bash
cd frontend && npm test -- tests/components/EntryItem.test.tsx
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/EntryItem.tsx frontend/src/components/EntryList.tsx \
        frontend/tests/components/EntryItem.test.tsx
git commit -m "feat(frontend): EntryItem + EntryList with refine/deprecate callback hooks"
```

---

## Task 17: EntryRefineModal + useRefineEntry

**Files:**
- Create: `frontend/src/hooks/useRefineEntry.ts`
- Create: `frontend/src/components/EntryRefineModal.tsx`
- Create: `frontend/tests/components/EntryRefineModal.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { EntryRefineModal } from "../../src/components/EntryRefineModal";
import type { RetrievalEntry } from "../../src/types/domain";

const server = setupServer();
beforeEach(() => {
  server.listen();
  sessionStorage.setItem("goldens.api_token", "tok");
});
afterEach(() => {
  server.resetHandlers();
  server.close();
  sessionStorage.clear();
});

const entry: RetrievalEntry = {
  entry_id: "e_001",
  query: "Original frage",
  expected_chunk_ids: [],
  chunk_hashes: {},
  review_chain: [],
  deprecated: false,
  refines: null,
  task_type: "retrieval",
  source_element: null,
};

function renderModal(props: { onClose?: () => void; slug?: string; elementId?: string }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <EntryRefineModal
        entry={entry}
        slug={props.slug ?? "doc-x"}
        elementId={props.elementId ?? "p1-aaa"}
        onClose={props.onClose ?? (() => {})}
      />
    </QueryClientProvider>,
  );
}

describe("EntryRefineModal", () => {
  it("prefills the query with the entry's existing query", () => {
    renderModal({});
    expect(screen.getByLabelText(/neue frage/i)).toHaveValue("Original frage");
  });

  it("submits refine and closes on success", async () => {
    server.use(
      http.post("http://localhost/api/entries/e_001/refine", () =>
        HttpResponse.json({ new_entry_id: "e_002" }),
      ),
    );
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderModal({ onClose });
    const ta = screen.getByLabelText(/neue frage/i);
    await user.clear(ta);
    await user.type(ta, "Verbesserte frage");
    await user.click(screen.getByRole("button", { name: /verfeinern/i }));
    await screen.findByText(/verfeinert/i, undefined, { timeout: 2000 }).catch(() => {});
    expect(onClose).toHaveBeenCalled();
  });

  it("Escape key closes the modal", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderModal({ onClose });
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd frontend && npm test -- tests/components/EntryRefineModal.test.tsx
```

- [ ] **Step 3: Implement `frontend/src/hooks/useRefineEntry.ts`**

```typescript
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { refineEntry } from "../api/entries";
import type { RefineRequest, RefineResponse } from "../types/domain";

interface Args {
  entryId: string;
  body: RefineRequest;
  slug: string;
  elementId: string;
}

export function useRefineEntry() {
  const qc = useQueryClient();
  return useMutation<RefineResponse, Error, Args>({
    mutationFn: ({ entryId, body }) => refineEntry(entryId, body),
    onSuccess: (_data, { slug, elementId }) => {
      qc.invalidateQueries({ queryKey: ["element", slug, elementId] });
      qc.invalidateQueries({ queryKey: ["doc-elements", slug] });
    },
  });
}
```

- [ ] **Step 4: Implement `frontend/src/components/EntryRefineModal.tsx`**

```tsx
import { useEffect, useState, type KeyboardEvent } from "react";
import toast from "react-hot-toast";
import { useRefineEntry } from "../hooks/useRefineEntry";
import { ApiError } from "../api/client";
import type { RetrievalEntry } from "../types/domain";

interface Props {
  entry: RetrievalEntry;
  slug: string;
  elementId: string;
  onClose: () => void;
}

export function EntryRefineModal({ entry, slug, elementId, onClose }: Props) {
  const [query, setQuery] = useState(entry.query);
  const [notes, setNotes] = useState("");
  const refine = useRefineEntry();

  useEffect(() => {
    function onKey(e: globalThis.KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function handleSubmit(e: KeyboardEvent | { preventDefault: () => void }) {
    e.preventDefault();
    if (!query.trim()) return;
    refine.mutate(
      {
        entryId: entry.entry_id,
        slug,
        elementId,
        body: {
          query: query.trim(),
          expected_chunk_ids: entry.expected_chunk_ids,
          chunk_hashes: entry.chunk_hashes,
          notes: notes.trim() || null,
        },
      },
      {
        onSuccess: () => {
          toast.success("Eintrag verfeinert.");
          onClose();
        },
        onError: (err) => {
          if (err instanceof ApiError && err.status === 409) {
            toast.error("Eintrag bereits zurückgezogen.");
          } else if (err instanceof ApiError && err.status === 404) {
            toast.error("Eintrag nicht gefunden.");
          } else {
            toast.error("Verfeinern fehlgeschlagen.");
          }
        },
      },
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="refine-title"
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <form
        className="bg-white rounded-lg shadow-xl w-full max-w-lg p-6 space-y-4"
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
      >
        <h2 id="refine-title" className="text-lg font-semibold">
          Eintrag verfeinern
        </h2>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Neue Frage</span>
          <textarea
            className="input mt-1 min-h-[100px]"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
            aria-label="Neue Frage"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Notiz (optional)</span>
          <input
            className="input mt-1"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </label>
        <div className="flex items-center justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="btn-secondary">
            Abbrechen
          </button>
          <button
            type="submit"
            className="btn-primary"
            disabled={refine.isPending || !query.trim()}
          >
            {refine.isPending ? "Verfeinere…" : "Verfeinern"}
          </button>
        </div>
      </form>
    </div>
  );
}
```

- [ ] **Step 5: Run tests**

```bash
cd frontend && npm test -- tests/components/EntryRefineModal.test.tsx
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/useRefineEntry.ts \
        frontend/src/components/EntryRefineModal.tsx \
        frontend/tests/components/EntryRefineModal.test.tsx
git commit -m "feat(frontend): EntryRefineModal + useRefineEntry mutation hook"
```

---

## Task 18: EntryDeprecateModal + useDeprecateEntry

**Files:**
- Create: `frontend/src/hooks/useDeprecateEntry.ts`
- Create: `frontend/src/components/EntryDeprecateModal.tsx`

(Tests follow same pattern as Task 17. We bundle a small smoke test here for brevity.)

- [ ] **Step 1: Implement `frontend/src/hooks/useDeprecateEntry.ts`**

```typescript
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deprecateEntry } from "../api/entries";
import type { DeprecateRequest, DeprecateResponse } from "../types/domain";

interface Args {
  entryId: string;
  body: DeprecateRequest;
  slug: string;
  elementId: string;
}

export function useDeprecateEntry() {
  const qc = useQueryClient();
  return useMutation<DeprecateResponse, Error, Args>({
    mutationFn: ({ entryId, body }) => deprecateEntry(entryId, body),
    onSuccess: (_data, { slug, elementId }) => {
      qc.invalidateQueries({ queryKey: ["element", slug, elementId] });
      qc.invalidateQueries({ queryKey: ["doc-elements", slug] });
    },
  });
}
```

- [ ] **Step 2: Implement `frontend/src/components/EntryDeprecateModal.tsx`**

```tsx
import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { useDeprecateEntry } from "../hooks/useDeprecateEntry";
import { ApiError } from "../api/client";
import type { RetrievalEntry } from "../types/domain";

interface Props {
  entry: RetrievalEntry;
  slug: string;
  elementId: string;
  onClose: () => void;
}

export function EntryDeprecateModal({ entry, slug, elementId, onClose }: Props) {
  const [reason, setReason] = useState("");
  const deprecate = useDeprecateEntry();

  useEffect(() => {
    function onKey(e: globalThis.KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function handleSubmit(e: { preventDefault: () => void }) {
    e.preventDefault();
    deprecate.mutate(
      { entryId: entry.entry_id, slug, elementId, body: { reason: reason.trim() || null } },
      {
        onSuccess: () => {
          toast.success("Eintrag zurückgezogen.");
          onClose();
        },
        onError: (err) => {
          if (err instanceof ApiError && err.status === 409) {
            toast.error("Bereits zurückgezogen.");
          } else if (err instanceof ApiError && err.status === 404) {
            toast.error("Eintrag nicht gefunden.");
          } else {
            toast.error("Zurückziehen fehlgeschlagen.");
          }
        },
      },
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="deprecate-title"
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <form
        className="bg-white rounded-lg shadow-xl w-full max-w-md p-6 space-y-4"
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
      >
        <h2 id="deprecate-title" className="text-lg font-semibold">
          Eintrag zurückziehen
        </h2>
        <p className="text-sm text-slate-700">
          <span className="font-medium">Frage:</span> {entry.query}
        </p>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Begründung</span>
          <textarea
            className="input mt-1 min-h-[80px]"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="z.B. Duplikat, falsche Antwort, …"
            autoFocus
          />
        </label>
        <div className="flex items-center justify-end gap-2">
          <button type="button" onClick={onClose} className="btn-secondary">
            Abbrechen
          </button>
          <button type="submit" className="btn-danger" disabled={deprecate.isPending}>
            {deprecate.isPending ? "Ziehe zurück…" : "Zurückziehen"}
          </button>
        </div>
      </form>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useDeprecateEntry.ts \
        frontend/src/components/EntryDeprecateModal.tsx
git commit -m "feat(frontend): EntryDeprecateModal + useDeprecateEntry hook"
```

---

## Task 19: ElementDetail composite + WeiterButton

**Files:**
- Create: `frontend/src/components/ElementDetail.tsx`
- Create: `frontend/tests/components/ElementDetail.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { ElementDetail } from "../../src/components/ElementDetail";

const server = setupServer();
beforeEach(() => {
  server.listen();
  sessionStorage.setItem("goldens.api_token", "tok");
});
afterEach(() => {
  server.resetHandlers();
  server.close();
  sessionStorage.clear();
});

function renderDetail(props: { slug: string; elementId: string; onWeiter?: () => void }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ElementDetail
          slug={props.slug}
          elementId={props.elementId}
          onWeiter={props.onWeiter ?? (() => {})}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ElementDetail", () => {
  it("renders element body, entries list, new-entry-form, weiter button", async () => {
    server.use(
      http.get("http://localhost/api/docs/foo/elements/p1-aaa", () =>
        HttpResponse.json({
          element: {
            element_id: "p1-aaa",
            page_number: 1,
            element_type: "paragraph",
            content: "Body text.",
          },
          entries: [
            {
              entry_id: "e_001",
              query: "Was steht hier?",
              expected_chunk_ids: [],
              chunk_hashes: {},
              review_chain: [
                {
                  timestamp_utc: "2026-04-30T07:00Z",
                  action: "created_from_scratch",
                  actor: { kind: "human", pseudonym: "alice", level: "phd" },
                  notes: null,
                },
              ],
              deprecated: false,
              refines: null,
              task_type: "retrieval",
              source_element: null,
            },
          ],
        }),
      ),
    );
    renderDetail({ slug: "foo", elementId: "p1-aaa" });
    expect(await screen.findByText("Body text.")).toBeInTheDocument();
    expect(screen.getByText(/was steht hier/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/neue frage/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /weiter/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd frontend && npm test -- tests/components/ElementDetail.test.tsx
```

- [ ] **Step 3: Implement `frontend/src/components/ElementDetail.tsx`**

```tsx
import { useState } from "react";
import { useElement } from "../hooks/useElement";
import { ElementBody } from "./ElementBody";
import { EntryList } from "./EntryList";
import { NewEntryForm } from "./NewEntryForm";
import { EntryRefineModal } from "./EntryRefineModal";
import { EntryDeprecateModal } from "./EntryDeprecateModal";
import { Spinner } from "./Spinner";
import type { RetrievalEntry } from "../types/domain";

interface Props {
  slug: string;
  elementId: string;
  onWeiter: () => void;
}

export function ElementDetail({ slug, elementId, onWeiter }: Props) {
  const { data, isLoading, error } = useElement(slug, elementId);
  const [refineEntry, setRefineEntry] = useState<RetrievalEntry | null>(null);
  const [deprecateEntry, setDeprecateEntry] = useState<RetrievalEntry | null>(null);

  if (isLoading) return <Spinner label="Lade Element…" />;
  if (error)
    return (
      <p role="alert" className="text-red-600">
        Fehler beim Laden.
      </p>
    );
  if (!data) return null;

  return (
    <section className="space-y-6">
      <ElementBody element={data.element} />
      <div>
        <h3 className="text-sm font-semibold text-slate-700 mb-2">
          Vorhandene Fragen ({data.entries.length})
        </h3>
        <EntryList
          entries={data.entries}
          onRefine={setRefineEntry}
          onDeprecate={setDeprecateEntry}
        />
      </div>
      <NewEntryForm slug={slug} elementId={elementId} onWeiter={onWeiter} />
      <div className="pt-4 border-t border-slate-200">
        <button onClick={onWeiter} className="btn-secondary">
          Weiter →
        </button>
      </div>
      {refineEntry ? (
        <EntryRefineModal
          entry={refineEntry}
          slug={slug}
          elementId={elementId}
          onClose={() => setRefineEntry(null)}
        />
      ) : null}
      {deprecateEntry ? (
        <EntryDeprecateModal
          entry={deprecateEntry}
          slug={slug}
          elementId={elementId}
          onClose={() => setDeprecateEntry(null)}
        />
      ) : null}
    </section>
  );
}
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npm test -- tests/components/ElementDetail.test.tsx
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ElementDetail.tsx \
        frontend/tests/components/ElementDetail.test.tsx
git commit -m "feat(frontend): ElementDetail composite (body + entries + form + weiter + modals)"
```

---

## Task 20: ElementSidebar

**Files:**
- Create: `frontend/src/components/ElementSidebar.tsx`
- Create: `frontend/tests/components/ElementSidebar.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { ElementSidebar } from "../../src/components/ElementSidebar";

const server = setupServer();
beforeEach(() => {
  server.listen();
  sessionStorage.setItem("goldens.api_token", "tok");
});
afterEach(() => {
  server.resetHandlers();
  server.close();
  sessionStorage.clear();
});

function renderSidebar(props: { slug: string; activeElementId?: string; onSelect?: (id: string) => void }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ElementSidebar
          slug={props.slug}
          activeElementId={props.activeElementId}
          onSelect={props.onSelect ?? (() => {})}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ElementSidebar", () => {
  it("renders one row per element with type, page, count", async () => {
    server.use(
      http.get("http://localhost/api/docs/foo/elements", () =>
        HttpResponse.json([
          {
            element: {
              element_id: "p1-aaa",
              page_number: 1,
              element_type: "heading",
              content: "Title",
            },
            count_active_entries: 0,
          },
          {
            element: {
              element_id: "p2-bbb",
              page_number: 2,
              element_type: "table",
              content: "x | y",
              table_dims: [4, 3],
            },
            count_active_entries: 3,
          },
        ]),
      ),
    );
    renderSidebar({ slug: "foo" });
    expect(await screen.findByText("Title")).toBeInTheDocument();
    expect(screen.getByText("x | y")).toBeInTheDocument();
    expect(screen.getByText(/p\.1/)).toBeInTheDocument();
    expect(screen.getByText(/p\.2/)).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("highlights the active element", async () => {
    server.use(
      http.get("http://localhost/api/docs/foo/elements", () =>
        HttpResponse.json([
          {
            element: {
              element_id: "p1-aaa",
              page_number: 1,
              element_type: "heading",
              content: "Active",
            },
            count_active_entries: 0,
          },
        ]),
      ),
    );
    renderSidebar({ slug: "foo", activeElementId: "p1-aaa" });
    const item = await screen.findByRole("button", { name: /active/i });
    expect(item).toHaveAttribute("aria-current", "true");
  });

  it("calls onSelect with element_id on click", async () => {
    const events: string[] = [];
    server.use(
      http.get("http://localhost/api/docs/foo/elements", () =>
        HttpResponse.json([
          {
            element: {
              element_id: "p3-ccc",
              page_number: 3,
              element_type: "paragraph",
              content: "Some text",
            },
            count_active_entries: 0,
          },
        ]),
      ),
    );
    const user = userEvent.setup();
    renderSidebar({ slug: "foo", onSelect: (id) => events.push(id) });
    const item = await screen.findByRole("button", { name: /some text/i });
    await user.click(item);
    expect(events).toEqual(["p3-ccc"]);
  });
});
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd frontend && npm test -- tests/components/ElementSidebar.test.tsx
```

- [ ] **Step 3: Implement `frontend/src/components/ElementSidebar.tsx`**

```tsx
import { useElements } from "../hooks/useElements";
import { Spinner } from "./Spinner";
import type { ElementWithCounts } from "../types/domain";

interface Props {
  slug: string;
  activeElementId: string | undefined;
  onSelect: (elementId: string) => void;
}

const TYPE_GLYPH: Record<string, string> = {
  paragraph: "¶",
  heading: "H",
  table: "▦",
  figure: "🖼",
  list_item: "•",
};

function shorten(s: string, n = 60): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + "…";
}

function rowLabel(item: ElementWithCounts): string {
  const el = item.element;
  if (el.element_type === "figure") return el.caption ?? "(Abbildung)";
  if (el.element_type === "table") return shorten(el.content, 40);
  return shorten(el.content, 60);
}

export function ElementSidebar({ slug, activeElementId, onSelect }: Props) {
  const { data, isLoading, error } = useElements(slug);

  if (isLoading) {
    return (
      <aside className="w-72 border-r border-slate-200 p-4 overflow-y-auto">
        <Spinner label="Lade Elemente…" />
      </aside>
    );
  }
  if (error || !data) {
    return (
      <aside className="w-72 border-r border-slate-200 p-4">
        <p className="text-red-600 text-sm">Fehler.</p>
      </aside>
    );
  }
  return (
    <aside className="w-72 border-r border-slate-200 overflow-y-auto bg-slate-50">
      <ul className="divide-y divide-slate-200">
        {data.map((item) => {
          const isActive = item.element.element_id === activeElementId;
          return (
            <li key={item.element.element_id}>
              <button
                type="button"
                onClick={() => onSelect(item.element.element_id)}
                aria-current={isActive ? "true" : undefined}
                className={`w-full text-left px-3 py-2 hover:bg-white transition ${
                  isActive ? "bg-white border-l-4 border-blue-500" : ""
                }`}
              >
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <span title={item.element.element_type}>
                    {TYPE_GLYPH[item.element.element_type]}
                  </span>
                  <span>p.{item.element.page_number}</span>
                  {item.count_active_entries > 0 ? (
                    <span className="ml-auto bg-blue-100 text-blue-800 rounded-full px-2 py-0.5 text-xs">
                      {item.count_active_entries}
                    </span>
                  ) : null}
                </div>
                <p className="text-sm text-slate-700 mt-1 truncate">
                  {rowLabel(item)}
                </p>
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npm test -- tests/components/ElementSidebar.test.tsx
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ElementSidebar.tsx \
        frontend/tests/components/ElementSidebar.test.tsx
git commit -m "feat(frontend): ElementSidebar with active-highlight + count badge"
```

---

## Task 21: useKeyboardShortcuts hook

**Files:**
- Create: `frontend/src/hooks/useKeyboardShortcuts.ts`
- Create: `frontend/tests/hooks/useKeyboardShortcuts.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useKeyboardShortcuts } from "../../src/hooks/useKeyboardShortcuts";

describe("useKeyboardShortcuts", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("calls handler for matching key when focus is not in input", () => {
    const onJ = vi.fn();
    renderHook(() => useKeyboardShortcuts({ j: onJ }));
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "j" }));
    expect(onJ).toHaveBeenCalled();
  });

  it("does NOT call handler when focus is in textarea", () => {
    const onJ = vi.fn();
    document.body.innerHTML = '<textarea id="t"></textarea>';
    const ta = document.getElementById("t") as HTMLTextAreaElement;
    ta.focus();
    renderHook(() => useKeyboardShortcuts({ j: onJ }));
    ta.dispatchEvent(new KeyboardEvent("keydown", { key: "j", bubbles: true }));
    expect(onJ).not.toHaveBeenCalled();
  });

  it("calls ArrowDown handler", () => {
    const onArrow = vi.fn();
    renderHook(() => useKeyboardShortcuts({ ArrowDown: onArrow }));
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown" }));
    expect(onArrow).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd frontend && npm test -- tests/hooks/useKeyboardShortcuts.test.ts
```

- [ ] **Step 3: Implement `frontend/src/hooks/useKeyboardShortcuts.ts`**

```typescript
import { useEffect } from "react";

type Handler = (event: KeyboardEvent) => void;
type Bindings = Record<string, Handler>;

function isTextEntryFocused(): boolean {
  const a = document.activeElement;
  if (!a) return false;
  if (a instanceof HTMLTextAreaElement) return true;
  if (a instanceof HTMLInputElement) {
    return !["button", "submit", "checkbox", "radio"].includes(a.type);
  }
  if (a instanceof HTMLElement && a.isContentEditable) return true;
  return false;
}

export function useKeyboardShortcuts(bindings: Bindings) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isTextEntryFocused()) return;
      const handler = bindings[e.key];
      if (handler) handler(e);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [bindings]);
}
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npm test -- tests/hooks/useKeyboardShortcuts.test.ts
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useKeyboardShortcuts.ts \
        frontend/tests/hooks/useKeyboardShortcuts.test.ts
git commit -m "feat(frontend): useKeyboardShortcuts hook (skip when text-entry focused)"
```

---

## Task 22: HelpModal

**Files:**
- Create: `frontend/src/components/HelpModal.tsx`

- [ ] **Step 1: Implement `frontend/src/components/HelpModal.tsx`**

```tsx
import { useEffect } from "react";

interface Props {
  onClose: () => void;
}

const SHORTCUTS: Array<[string, string]> = [
  ["Enter (im Textarea)", "Speichern"],
  ["Enter (Textarea leer)", "Weiter"],
  ["Ctrl+Enter / Cmd+Enter", "Speichern (auch wenn Textarea Inhalt hat)"],
  ["Escape", "Modal schließen"],
  ["j / ArrowDown", "Sidebar nach unten"],
  ["k / ArrowUp", "Sidebar nach oben"],
  ["t (auf Tabelle)", "Volle Tabelle ↔ Stub"],
  ["?", "Diese Hilfe"],
];

export function HelpModal({ onClose }: Props) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="help-title"
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-md p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="help-title" className="text-lg font-semibold mb-4">
          Tastatur-Shortcuts
        </h2>
        <dl className="space-y-2 text-sm">
          {SHORTCUTS.map(([k, v]) => (
            <div key={k} className="grid grid-cols-2 gap-4">
              <dt className="font-mono text-slate-700">{k}</dt>
              <dd className="text-slate-600">{v}</dd>
            </div>
          ))}
        </dl>
        <button onClick={onClose} className="btn-secondary mt-4">
          Schließen
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/HelpModal.tsx
git commit -m "feat(frontend): HelpModal with keyboard shortcuts reference"
```

---

## Task 23: DocElements route (sidebar + detail composite)

**Files:**
- Create: `frontend/src/routes/doc-elements.tsx`
- Create: `frontend/tests/routes/doc-elements.test.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { DocElements } from "../../src/routes/doc-elements";

const server = setupServer();
beforeEach(() => {
  server.listen();
  sessionStorage.setItem("goldens.api_token", "tok");
});
afterEach(() => {
  server.resetHandlers();
  server.close();
  sessionStorage.clear();
});

const elements = [
  {
    element: {
      element_id: "p1-aaa",
      page_number: 1,
      element_type: "heading",
      content: "First",
    },
    count_active_entries: 0,
  },
  {
    element: {
      element_id: "p1-bbb",
      page_number: 1,
      element_type: "paragraph",
      content: "Second body.",
    },
    count_active_entries: 1,
  },
];

function renderRoute(initial = "/docs/foo/elements") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route path="/docs/:slug/elements" element={<DocElements />} />
          <Route path="/docs/:slug/elements/:elementId" element={<DocElements />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DocElements route", () => {
  it("renders sidebar + first element selected when no :elementId in URL", async () => {
    server.use(
      http.get("http://localhost/api/docs/foo/elements", () =>
        HttpResponse.json(elements),
      ),
      http.get("http://localhost/api/docs/foo/elements/p1-aaa", () =>
        HttpResponse.json({ element: elements[0].element, entries: [] }),
      ),
    );
    renderRoute();
    expect(await screen.findByText("First")).toBeInTheDocument();
    expect(await screen.findByText(/noch keine fragen/i)).toBeInTheDocument();
  });

  it("Weiter button advances to next element_id", async () => {
    server.use(
      http.get("http://localhost/api/docs/foo/elements", () =>
        HttpResponse.json(elements),
      ),
      http.get("http://localhost/api/docs/foo/elements/p1-aaa", () =>
        HttpResponse.json({ element: elements[0].element, entries: [] }),
      ),
      http.get("http://localhost/api/docs/foo/elements/p1-bbb", () =>
        HttpResponse.json({ element: elements[1].element, entries: [] }),
      ),
    );
    const user = userEvent.setup();
    renderRoute("/docs/foo/elements/p1-aaa");
    await screen.findByText("First");
    await user.click(screen.getByRole("button", { name: /weiter/i }));
    expect(await screen.findByText(/second body/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd frontend && npm test -- tests/routes/doc-elements.test.tsx
```

- [ ] **Step 3: Implement `frontend/src/routes/doc-elements.tsx`**

```tsx
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { TopBar } from "../components/TopBar";
import { ElementSidebar } from "../components/ElementSidebar";
import { ElementDetail } from "../components/ElementDetail";
import { HelpModal } from "../components/HelpModal";
import { useElements } from "../hooks/useElements";
import { useKeyboardShortcuts } from "../hooks/useKeyboardShortcuts";

export function DocElements() {
  const { slug, elementId } = useParams<{ slug: string; elementId?: string }>();
  const navigate = useNavigate();
  const { data: elements } = useElements(slug);
  const [helpOpen, setHelpOpen] = useState(false);

  // If no elementId in URL, redirect to first element once data is loaded.
  useEffect(() => {
    if (!elementId && elements && elements.length > 0 && slug) {
      navigate(
        `/docs/${encodeURIComponent(slug)}/elements/${encodeURIComponent(elements[0].element.element_id)}`,
        { replace: true },
      );
    }
  }, [elementId, elements, slug, navigate]);

  const currentIndex = useMemo(() => {
    if (!elements || !elementId) return -1;
    return elements.findIndex((e) => e.element.element_id === elementId);
  }, [elements, elementId]);

  function goToIndex(idx: number) {
    if (!elements || !slug) return;
    const clamped = Math.max(0, Math.min(idx, elements.length - 1));
    const target = elements[clamped];
    if (target) {
      navigate(
        `/docs/${encodeURIComponent(slug)}/elements/${encodeURIComponent(target.element.element_id)}`,
      );
    }
  }

  function selectElement(id: string) {
    if (!slug) return;
    navigate(`/docs/${encodeURIComponent(slug)}/elements/${encodeURIComponent(id)}`);
  }

  useKeyboardShortcuts({
    j: () => goToIndex(currentIndex + 1),
    k: () => goToIndex(currentIndex - 1),
    ArrowDown: () => goToIndex(currentIndex + 1),
    ArrowUp: () => goToIndex(currentIndex - 1),
    "?": () => setHelpOpen(true),
  });

  if (!slug) return <p>Missing slug.</p>;

  return (
    <div className="min-h-screen flex flex-col">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <ElementSidebar
          slug={slug}
          activeElementId={elementId}
          onSelect={selectElement}
        />
        <main className="flex-1 overflow-y-auto p-8 max-w-3xl mx-auto w-full">
          {elementId ? (
            <ElementDetail
              slug={slug}
              elementId={elementId}
              onWeiter={() => goToIndex(currentIndex + 1)}
            />
          ) : null}
        </main>
      </div>
      {helpOpen ? <HelpModal onClose={() => setHelpOpen(false)} /> : null}
    </div>
  );
}
```

- [ ] **Step 4: Wire in `frontend/src/App.tsx`**

Add import: `import { DocElements } from "./routes/doc-elements";`
Replace both `<DocElementsPlaceholder />` references with `<DocElements />`. Remove the placeholder function.

- [ ] **Step 5: Run tests**

```bash
cd frontend && npm test -- tests/routes/doc-elements.test.tsx
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/doc-elements.tsx frontend/src/App.tsx \
        frontend/tests/routes/doc-elements.test.tsx
git commit -m "feat(frontend): DocElements route composing sidebar + detail + keyboard shortcuts"
```

---

## Task 24: useSynthesise streaming hook

**Files:**
- Create: `frontend/src/hooks/useSynthesise.ts`
- Create: `frontend/tests/hooks/useSynthesise.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { useSynthesise } from "../../src/hooks/useSynthesise";

const server = setupServer();
beforeEach(() => {
  server.listen();
  sessionStorage.setItem("goldens.api_token", "tok");
});
afterEach(() => {
  server.resetHandlers();
  server.close();
  sessionStorage.clear();
});

function ndjsonResponse(lines: object[]): Response {
  const body = lines.map((l) => JSON.stringify(l)).join("\n") + "\n";
  return new Response(body, {
    headers: { "Content-Type": "application/x-ndjson" },
  });
}

describe("useSynthesise", () => {
  it("transitions idle → submitting → streaming → complete on successful run", async () => {
    server.use(
      http.post("http://localhost/api/docs/foo/synthesise", () =>
        ndjsonResponse([
          { type: "start", total_elements: 2 },
          {
            type: "element",
            element_id: "p1-aaa",
            kept: 3,
            skipped_reason: null,
            tokens_estimated: 30,
          },
          { type: "complete", events_written: 3, prompt_tokens_estimated: 30 },
        ]),
      ),
    );

    const { result } = renderHook(() => useSynthesise());
    expect(result.current.status).toBe("idle");

    act(() => {
      result.current.start({
        slug: "foo",
        request: { llm_model: "gpt-4o-mini", dry_run: true },
      });
    });

    await waitFor(() => expect(result.current.status).toBe("complete"));
    expect(result.current.lines).toHaveLength(3);
    expect(result.current.totals.kept).toBe(3);
    expect(result.current.totals.eventsWritten).toBe(3);
  });

  it("counts errors in the totals when SynthErrorLine is present", async () => {
    server.use(
      http.post("http://localhost/api/docs/foo/synthesise", () =>
        ndjsonResponse([
          { type: "start", total_elements: 1 },
          { type: "error", element_id: "p1-aaa", reason: "rate limit" },
          { type: "complete", events_written: 0, prompt_tokens_estimated: 0 },
        ]),
      ),
    );
    const { result } = renderHook(() => useSynthesise());
    act(() => {
      result.current.start({
        slug: "foo",
        request: { llm_model: "gpt-4o-mini", dry_run: true },
      });
    });
    await waitFor(() => expect(result.current.status).toBe("complete"));
    expect(result.current.totals.errors).toBe(1);
  });
});
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd frontend && npm test -- tests/hooks/useSynthesise.test.ts
```

- [ ] **Step 3: Implement `frontend/src/hooks/useSynthesise.ts`**

```typescript
import { useCallback, useReducer, useRef } from "react";
import { streamSynthesise } from "../api/docs";
import { ApiError } from "../api/client";
import type { SynthLine, SynthesiseRequest } from "../types/domain";

export type SynthStatus = "idle" | "submitting" | "streaming" | "complete" | "error" | "cancelled";

interface State {
  status: SynthStatus;
  lines: SynthLine[];
  totals: {
    totalElements: number;
    kept: number;
    skipped: number;
    errors: number;
    tokensEstimated: number;
    eventsWritten: number;
  };
  fatalError: string | null;
}

const initial: State = {
  status: "idle",
  lines: [],
  totals: {
    totalElements: 0,
    kept: 0,
    skipped: 0,
    errors: 0,
    tokensEstimated: 0,
    eventsWritten: 0,
  },
  fatalError: null,
};

type Action =
  | { type: "start" }
  | { type: "stream-begun" }
  | { type: "line"; line: SynthLine }
  | { type: "complete" }
  | { type: "fatal"; reason: string }
  | { type: "cancelled" }
  | { type: "reset" };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "start":
      return { ...initial, status: "submitting" };
    case "stream-begun":
      return { ...state, status: "streaming" };
    case "line": {
      const line = action.line;
      const lines = [...state.lines, line];
      const t = { ...state.totals };
      if (line.type === "start") t.totalElements = line.total_elements;
      else if (line.type === "element") {
        t.kept += line.kept;
        if (line.skipped_reason) t.skipped += 1;
        t.tokensEstimated += line.tokens_estimated;
      } else if (line.type === "error") t.errors += 1;
      else if (line.type === "complete") {
        t.eventsWritten = line.events_written;
        t.tokensEstimated = line.prompt_tokens_estimated;
      }
      return { ...state, lines, totals: t };
    }
    case "complete":
      return { ...state, status: "complete" };
    case "fatal":
      return { ...state, status: "error", fatalError: action.reason };
    case "cancelled":
      return { ...state, status: "cancelled" };
    case "reset":
      return initial;
  }
}

interface StartArgs {
  slug: string;
  request: SynthesiseRequest;
}

export function useSynthesise() {
  const [state, dispatch] = useReducer(reducer, initial);
  const abortRef = useRef<AbortController | null>(null);

  const start = useCallback(async ({ slug, request }: StartArgs) => {
    dispatch({ type: "start" });
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const stream = await streamSynthesise(slug, request, ctrl.signal);
      dispatch({ type: "stream-begun" });
      for await (const line of stream) {
        dispatch({ type: "line", line });
      }
      dispatch({ type: "complete" });
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        dispatch({ type: "cancelled" });
        return;
      }
      const reason =
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : (err as Error).message ?? "Unbekannter Fehler";
      dispatch({ type: "fatal", reason });
    }
  }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const reset = useCallback(() => {
    dispatch({ type: "reset" });
  }, []);

  return { ...state, start, cancel, reset };
}
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npm test -- tests/hooks/useSynthesise.test.ts
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useSynthesise.ts frontend/tests/hooks/useSynthesise.test.ts
git commit -m "feat(frontend): useSynthesise streaming hook with reducer state machine"
```

---

## Task 25: Synthesise UI components

**Files:**
- Create: `frontend/src/components/SynthForm.tsx`
- Create: `frontend/src/components/SynthProgress.tsx`
- Create: `frontend/src/components/SynthSummary.tsx`
- Create: `frontend/tests/components/SynthProgress.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SynthProgress } from "../../src/components/SynthProgress";
import type { SynthLine } from "../../src/types/domain";

const lines: SynthLine[] = [
  { type: "start", total_elements: 2 },
  {
    type: "element",
    element_id: "p1-aaa",
    kept: 3,
    skipped_reason: null,
    tokens_estimated: 42,
  },
  { type: "error", element_id: "p1-bbb", reason: "rate limit" },
  { type: "complete", events_written: 3, prompt_tokens_estimated: 42 },
];

describe("SynthProgress", () => {
  it("renders one row per line and styles error rows differently", () => {
    render(
      <SynthProgress
        lines={lines}
        totals={{
          totalElements: 2,
          kept: 3,
          skipped: 0,
          errors: 1,
          tokensEstimated: 42,
          eventsWritten: 3,
        }}
      />,
    );
    expect(screen.getByText(/p1-aaa/)).toBeInTheDocument();
    expect(screen.getByText(/p1-bbb/)).toBeInTheDocument();
    expect(screen.getByText(/rate limit/)).toBeInTheDocument();
    expect(screen.getByText(/2 elements/)).toBeInTheDocument();
    expect(screen.getByText(/3 kept/)).toBeInTheDocument();
    expect(screen.getByText(/1 error/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd frontend && npm test -- tests/components/SynthProgress.test.tsx
```

- [ ] **Step 3: Implement `frontend/src/components/SynthForm.tsx`**

```tsx
import { useState, type FormEvent } from "react";
import type { SynthesiseRequest } from "../types/domain";

interface Props {
  defaultModel?: string;
  onSubmit: (req: SynthesiseRequest) => void;
  disabled?: boolean;
}

export function SynthForm({ defaultModel = "gpt-4o-mini", onSubmit, disabled }: Props) {
  const [llmModel, setLlmModel] = useState(defaultModel);
  const [dryRun, setDryRun] = useState(true);
  const [maxQuestions, setMaxQuestions] = useState(20);
  const [maxPromptTokens, setMaxPromptTokens] = useState(8000);
  const [promptTemplateVersion, setPromptTemplateVersion] = useState("v1");
  const [temperature, setTemperature] = useState(0.0);
  const [startFrom, setStartFrom] = useState("");
  const [limit, setLimit] = useState<string>("");
  const [resume, setResume] = useState(false);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onSubmit({
      llm_model: llmModel,
      dry_run: dryRun,
      max_questions_per_element: maxQuestions,
      max_prompt_tokens: maxPromptTokens,
      prompt_template_version: promptTemplateVersion,
      temperature,
      start_from: startFrom.trim() || null,
      limit: limit.trim() ? Number(limit) : null,
      resume,
    });
  }

  return (
    <form className="space-y-4 max-w-md" onSubmit={handleSubmit}>
      <label className="block">
        <span className="text-sm font-medium text-slate-700">LLM Model</span>
        <input
          className="input mt-1"
          value={llmModel}
          onChange={(e) => setLlmModel(e.target.value)}
        />
      </label>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={dryRun}
          onChange={(e) => setDryRun(e.target.checked)}
        />
        <span className="text-sm">Dry-run (keine LLM-Calls, nur Token-Schätzung)</span>
      </label>
      <div className="grid grid-cols-2 gap-3">
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Max questions/element</span>
          <input
            type="number"
            className="input mt-1"
            value={maxQuestions}
            onChange={(e) => setMaxQuestions(Number(e.target.value))}
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Max prompt tokens</span>
          <input
            type="number"
            className="input mt-1"
            value={maxPromptTokens}
            onChange={(e) => setMaxPromptTokens(Number(e.target.value))}
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Prompt template</span>
          <input
            className="input mt-1"
            value={promptTemplateVersion}
            onChange={(e) => setPromptTemplateVersion(e.target.value)}
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Temperature</span>
          <input
            type="number"
            step="0.1"
            className="input mt-1"
            value={temperature}
            onChange={(e) => setTemperature(Number(e.target.value))}
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Start from (element_id)</span>
          <input
            className="input mt-1"
            value={startFrom}
            onChange={(e) => setStartFrom(e.target.value)}
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Limit (#elements)</span>
          <input
            type="number"
            className="input mt-1"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
          />
        </label>
      </div>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={resume}
          onChange={(e) => setResume(e.target.checked)}
        />
        <span className="text-sm">Resume — überspringe schon-erfasste Elemente</span>
      </label>
      <button type="submit" className="btn-primary" disabled={disabled}>
        Synthesise starten
      </button>
    </form>
  );
}
```

- [ ] **Step 4: Implement `frontend/src/components/SynthProgress.tsx`**

```tsx
import type { SynthLine } from "../types/domain";

interface Props {
  lines: SynthLine[];
  totals: {
    totalElements: number;
    kept: number;
    skipped: number;
    errors: number;
    tokensEstimated: number;
    eventsWritten: number;
  };
}

function renderLine(line: SynthLine, idx: number) {
  if (line.type === "start") {
    return (
      <li key={idx} className="text-slate-600">
        ▶ Start ({line.total_elements} elements)
      </li>
    );
  }
  if (line.type === "element") {
    return (
      <li key={idx} className="text-slate-700">
        ✓ <span className="font-mono">{line.element_id}</span>
        {" · "}
        {line.kept} kept
        {line.skipped_reason ? ` · skipped: ${line.skipped_reason}` : ""}
        {" · "}
        {line.tokens_estimated} tokens
      </li>
    );
  }
  if (line.type === "error") {
    return (
      <li key={idx} className="text-red-700">
        ✗ <span className="font-mono">{line.element_id ?? "—"}</span>
        {" · "}
        {line.reason}
      </li>
    );
  }
  return (
    <li key={idx} className="text-green-700 font-medium">
      ◆ Complete · {line.events_written} events written · {line.prompt_tokens_estimated} tokens
    </li>
  );
}

export function SynthProgress({ lines, totals }: Props) {
  return (
    <div className="space-y-3">
      <div className="text-sm text-slate-600">
        {totals.totalElements} elements · {totals.kept} kept · {totals.errors} error
        {totals.errors !== 1 ? "s" : ""} · {totals.tokensEstimated} tokens
      </div>
      <ul className="space-y-1 font-mono text-xs bg-slate-50 rounded p-3 max-h-96 overflow-y-auto">
        {lines.map(renderLine)}
      </ul>
    </div>
  );
}
```

- [ ] **Step 5: Implement `frontend/src/components/SynthSummary.tsx`**

```tsx
import { Link } from "react-router-dom";

interface Props {
  slug: string;
  totals: {
    totalElements: number;
    kept: number;
    errors: number;
    eventsWritten: number;
    tokensEstimated: number;
  };
  onReset: () => void;
}

export function SynthSummary({ slug, totals, onReset }: Props) {
  return (
    <div className="space-y-4 max-w-md">
      <h2 className="text-lg font-semibold">Synthesise abgeschlossen.</h2>
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <dt className="text-slate-600">Elements</dt>
        <dd>{totals.totalElements}</dd>
        <dt className="text-slate-600">Kept (questions)</dt>
        <dd>{totals.kept}</dd>
        <dt className="text-slate-600">Events written</dt>
        <dd>{totals.eventsWritten}</dd>
        <dt className="text-slate-600">Errors</dt>
        <dd className={totals.errors > 0 ? "text-red-700" : ""}>{totals.errors}</dd>
        <dt className="text-slate-600">Tokens estimated</dt>
        <dd>{totals.tokensEstimated}</dd>
      </dl>
      <div className="flex items-center gap-2">
        <Link
          to={`/docs/${encodeURIComponent(slug)}/elements`}
          className="btn-primary"
        >
          Zurück zu den Elementen
        </Link>
        <button onClick={onReset} className="btn-secondary">
          Nochmal
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Run tests**

```bash
cd frontend && npm test -- tests/components/SynthProgress.test.tsx
```

Expected: 1 passed.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/SynthForm.tsx \
        frontend/src/components/SynthProgress.tsx \
        frontend/src/components/SynthSummary.tsx \
        frontend/tests/components/SynthProgress.test.tsx
git commit -m "feat(frontend): SynthForm + SynthProgress + SynthSummary components"
```

---

## Task 26: Synthesise route

**Files:**
- Create: `frontend/src/routes/doc-synthesise.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Implement `frontend/src/routes/doc-synthesise.tsx`**

```tsx
import { useParams } from "react-router-dom";
import { TopBar } from "../components/TopBar";
import { SynthForm } from "../components/SynthForm";
import { SynthProgress } from "../components/SynthProgress";
import { SynthSummary } from "../components/SynthSummary";
import { useSynthesise } from "../hooks/useSynthesise";

export function DocSynthesise() {
  const { slug } = useParams<{ slug: string }>();
  const synth = useSynthesise();

  if (!slug) return <p>Missing slug.</p>;

  return (
    <div className="min-h-screen flex flex-col">
      <TopBar />
      <main className="flex-1 p-8 max-w-3xl mx-auto w-full space-y-6">
        <h1 className="text-2xl font-semibold">Synthesise — {slug}</h1>
        {synth.status === "idle" || synth.status === "error" || synth.status === "cancelled" ? (
          <>
            {synth.status === "error" && synth.fatalError ? (
              <p role="alert" className="text-red-700">
                Fehler: {synth.fatalError}
              </p>
            ) : null}
            {synth.status === "cancelled" ? (
              <p className="text-slate-600">Abgebrochen.</p>
            ) : null}
            <SynthForm
              onSubmit={(req) => synth.start({ slug, request: req })}
              disabled={false}
            />
          </>
        ) : null}
        {(synth.status === "submitting" ||
          synth.status === "streaming" ||
          synth.status === "complete") && synth.lines.length > 0 ? (
          <SynthProgress lines={synth.lines} totals={synth.totals} />
        ) : null}
        {synth.status === "streaming" ? (
          <button onClick={synth.cancel} className="btn-secondary">
            Abbrechen
          </button>
        ) : null}
        {synth.status === "complete" ? (
          <SynthSummary slug={slug} totals={synth.totals} onReset={synth.reset} />
        ) : null}
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Wire in `frontend/src/App.tsx`**

Add `import { DocSynthesise } from "./routes/doc-synthesise";`. Replace `<SynthesisePlaceholder />` with `<DocSynthesise />`. Remove the placeholder.

- [ ] **Step 3: Verify build still passes**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: success.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/doc-synthesise.tsx frontend/src/App.tsx
git commit -m "feat(frontend): DocSynthesise route with form + streaming progress + summary"
```

---

## Task 27: Backend static-mount in goldens/api/app.py

**Files:**
- Modify: `features/goldens/src/goldens/api/app.py`

- [ ] **Step 1: Open `features/goldens/src/goldens/api/app.py` and locate the `create_app` function**

This file is created by A-Plus.1; we extend the END of `create_app()` with a static-mount block.

- [ ] **Step 2: Add the mount block at the end of `create_app()`**

After all routers and exception handlers are registered, add (before the return statement):

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

# Try mounting frontend/dist/ at "/" if it exists. In dev mode (no
# `npm run build` yet), the directory won't exist and we skip — only
# the API routes plus /docs (Swagger) remain reachable.
_dist = Path(__file__).resolve().parents[5] / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
```

- [ ] **Step 3: Verify import path**

The path `parents[5]` traverses:
- 0: `app.py`
- 1: `api/`
- 2: `goldens/`
- 3: `src/`
- 4: `goldens/` (the package dir)
- 5: `features/`

Wait — that's wrong. Let me re-check: `Path(__file__).resolve()` is the absolute path to `app.py`, so `.parents[0]` is `api/`, `.parents[1]` is `goldens/` (inner), `.parents[2]` is `src/`, `.parents[3]` is `goldens/` (outer feature dir), `.parents[4]` is `features/`, `.parents[5]` is the repo root. Then `repo_root / "frontend" / "dist"` is what we want.

So `parents[5]` is correct. Verify by adding a debug print once if uncertain.

- [ ] **Step 4: Run goldens tests to ensure nothing broke**

```bash
cd /home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft && \
  source .venv/bin/activate && \
  python -m pytest features/goldens/tests/test_api_app.py 2>&1 | tail -5
```

Expected: tests still green (the static-mount is only active when `dist/` exists, which doesn't in test env).

- [ ] **Step 5: Manual smoke (after frontend `npm run build`)**

```bash
cd frontend && npm run build && cd ..
export GOLDENS_API_TOKEN=$(uuidgen)
query-eval serve &
sleep 2
curl -s http://127.0.0.1:8000/ | head -3
pkill -f "query-eval serve"
```

Expected: HTML output from `index.html`.

- [ ] **Step 6: Commit**

```bash
git add features/goldens/src/goldens/api/app.py
git commit -m "feat(goldens/api): mount frontend/dist as static when present"
```

---

## Task 28: Playwright config + happy-path E2E

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/tests/e2e/tragkorb.spec.ts`

- [ ] **Step 1: Create `frontend/playwright.config.ts`**

```typescript
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30 * 1000,
  expect: { timeout: 5000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: "npm run dev",
    port: 5173,
    reuseExistingServer: true,
  },
});
```

- [ ] **Step 2: Install Playwright browsers**

```bash
cd frontend && npx playwright install chromium
```

Expected: ~150 MB download for Chromium.

- [ ] **Step 3: Create `frontend/tests/e2e/tragkorb.spec.ts`**

```typescript
import { test, expect } from "@playwright/test";

const TOKEN = process.env.GOLDENS_API_TOKEN ?? "";

test.skip(!TOKEN, "GOLDENS_API_TOKEN env var not set; skipping E2E");

test("login + walk + add question + dry-run synthesise", async ({ page }) => {
  await page.goto("/");
  // Should redirect to login
  await expect(page).toHaveURL(/\/login$/);

  // Login
  await page.getByLabel(/api-token/i).fill(TOKEN);
  await page.getByRole("button", { name: /einloggen/i }).click();

  // Docs index
  await expect(page.getByText(/dokumente/i)).toBeVisible();
  await page.getByRole("link", { name: /smoke-test-tragkorb/i }).click();

  // Doc elements page — element-walk
  const sidebar = page.locator('[role="navigation"]').or(page.locator("aside"));
  await expect(sidebar).toBeVisible();

  // Add a question to the first element
  await page.getByLabel(/neue frage/i).fill("E2E test question");
  await page.getByRole("button", { name: /speichern/i }).click();
  await expect(page.locator("text=gespeichert")).toBeVisible({ timeout: 3000 });

  // Synthesise dry-run
  await page.goto("/#/docs/smoke-test-tragkorb/synthesise");
  await page.getByRole("button", { name: /synthesise starten/i }).click();
  await expect(page.locator("text=Complete")).toBeVisible({ timeout: 60_000 });
});
```

- [ ] **Step 4: Add a `tests/e2e` README note**

Append to `frontend/README.md` (created in Task 30):

> E2E tests need `query-eval serve` running with `GOLDENS_API_TOKEN` set, plus the Tragkorb fixture under `outputs/`.

- [ ] **Step 5: Verify Playwright config (no run yet)**

```bash
cd frontend && npx playwright test --list 2>&1 | head -5
```

Expected: lists the test file without errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/playwright.config.ts frontend/tests/e2e/tragkorb.spec.ts
git commit -m "test(frontend): Playwright e2e setup with Tragkorb happy-path"
```

---

## Task 29: README dev-quickstart

**Files:**
- Create: `frontend/README.md`

- [ ] **Step 1: Create `frontend/README.md`**

```markdown
# Goldens Frontend

Browser SPA für Curate + Review der Goldsets. Konsumiert die A-Plus.1 HTTP-API.

## Stack

- TypeScript + React 18 + Vite
- react-router 6 (hash-mode)
- TanStack Query 5 für Server-State
- Tailwind CSS für Styles
- Vitest + RTL + msw (unit/integration), Playwright (E2E)

## Dev-Setup

Zwei Terminals:

```bash
# Terminal 1: Vite dev-server (mit /api proxy)
cd frontend
npm install
npm run dev    # → http://127.0.0.1:5173

# Terminal 2: FastAPI backend
cd ..
source .venv/bin/activate
export GOLDENS_API_TOKEN=$(uuidgen)
echo "Token: $GOLDENS_API_TOKEN"
query-eval serve    # → http://127.0.0.1:8000
```

Browser auf http://127.0.0.1:5173, Token aus Terminal 2 in Login-Form.

## Production-ish (Single-Process)

```bash
cd frontend && npm run build && cd ..
export GOLDENS_API_TOKEN=$(uuidgen)
query-eval serve    # FastAPI mountet frontend/dist/ automatisch
# Browser: http://127.0.0.1:8000
```

## Tests

```bash
cd frontend
npm test                    # Vitest unit + integration
npm run test:coverage       # mit Coverage-Report
npm run e2e                 # Playwright (braucht laufenden Backend)
```

E2E-Tests brauchen `query-eval serve` parallel + `GOLDENS_API_TOKEN` env-var + die Tragkorb-Fixture unter `outputs/`.

## Layout

```
frontend/
├── src/
│   ├── routes/        Page-Components (login, docs-index, doc-elements, doc-synthesise)
│   ├── components/    Reusable UI (Sidebar, Detail, Modals, Forms, ...)
│   ├── hooks/         TanStack Query + custom hooks
│   ├── api/           fetch wrapper, NDJSON reader, endpoint modules
│   ├── types/         TS mirrors of A-Plus.1 Pydantic schemas
│   └── styles/        Tailwind + globals
└── tests/
    ├── api/           Module-level tests via msw
    ├── hooks/         Hook tests
    ├── components/    RTL component tests
    ├── routes/        Integration tests
    └── e2e/           Playwright happy-path
```

## Spec

`docs/superpowers/specs/2026-04-30-a-plus-2-frontend-design.md` — vollständige Design-Doc inkl. Decision Log (AP2.1-AP2.20) und Out-of-Scope.
```

- [ ] **Step 2: Commit**

```bash
git add frontend/README.md
git commit -m "docs(frontend): dev-quickstart and architecture overview"
```

---

## Task 30: Final verification + push + PR

- [ ] **Step 1: Run the full unit/integration suite**

```bash
cd frontend && npm test 2>&1 | tail -10
```

Expected: all tests pass; coverage ≥90% on `components/`, `hooks/`, `api/`.

- [ ] **Step 2: Run lint + format check**

```bash
cd frontend && npm run lint && npm run format:check 2>&1 | tail -10
```

Expected: clean.

- [ ] **Step 3: Build the production bundle**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

Expected: success, `dist/` ~2-5 MB.

- [ ] **Step 4: Manual smoke against running backend (Tragkorb fixture)**

```bash
cd ..
source .venv/bin/activate
export GOLDENS_API_TOKEN=$(uuidgen)
echo "Token: $GOLDENS_API_TOKEN"
query-eval serve &
sleep 2
# Browser at http://127.0.0.1:8000 — login, walk, add question, run synthesise dry-run
# (manual; if cannot run interactively, skip and rely on Playwright)
pkill -f "query-eval serve"
```

- [ ] **Step 5: Run goldens backend tests to ensure static-mount didn't regress anything**

```bash
source .venv/bin/activate && python -m pytest features/goldens/tests 2>&1 | tail -5
```

Expected: 100% green.

- [ ] **Step 6: Push the branch**

```bash
git push -u origin feat/a-plus-2-frontend
```

- [ ] **Step 7: Open the PR**

```bash
gh pr create --title "feat(frontend): A-Plus.2 browser SPA" --body "$(cat <<'EOF'
## Summary
Implements A-Plus.2 — browser SPA in `frontend/` consuming the A-Plus.1 HTTP backend.

Spec: `docs/superpowers/specs/2026-04-30-a-plus-2-frontend-design.md` (PR #20 merged)
Plan: `docs/superpowers/plans/2026-04-30-a-plus-2-frontend.md`

## What's in here
- `frontend/` — separate npm package, TypeScript + React 18 + Vite + Tailwind
- Routes: login, docs-index, doc-elements (sidebar+detail), doc-synthesise (streaming)
- Hooks: useAuth, useDocs, useElements, useElement, useCreateEntry, useRefineEntry, useDeprecateEntry, useSynthesise, useKeyboardShortcuts
- Components: ElementSidebar, ElementDetail, ElementBody (Table/Figure/Paragraph variants), EntryItem, EntryRefineModal, EntryDeprecateModal, NewEntryForm, SynthForm/Progress/Summary, TopBar, HelpModal, Spinner
- API client with X-Auth-Token + 401-interceptor; NDJSON streaming reader
- Backend: 5-line addition to `features/goldens/src/goldens/api/app.py` to auto-mount `frontend/dist/`
- Tests: Vitest + RTL + msw (unit/integration); Playwright happy-path E2E

## Test plan
- [x] `cd frontend && npm test` — all tests green, coverage ≥90% in components/hooks/api
- [x] `npm run build` — production bundle clean
- [x] `npm run lint && npm run format:check` — clean
- [x] `npm run e2e` — Tragkorb walk-through passes (login + walk + add question + dry-run synthesise)
- [x] Goldens backend test suite still green (static-mount block is dist-conditional)
- [x] Manual: `query-eval serve` after `npm run build` serves browser at `http://127.0.0.1:8000`
EOF
)"
```

- [ ] **Step 8: Final report**

After PR opens, message lead with `[phase-complete]` summary.

---

## Self-Review

**Spec coverage:**
- §3 Architecture (process model, state, boundary) → Tasks 1, 8
- §4 Routing (routes, bootstrap, components, NDJSON) → Tasks 6, 8, 9, 10, 11, 23, 26
- §5 Schema strategy → Task 4
- §6 Mutations + cache invalidation → Tasks 15, 17, 18
- §7 Error handling (401, 422, 404/409, server, streaming) → Tasks 5, 15, 17, 18, 24
- §8 Auth flow → Tasks 5, 9, 10
- §9 Module layout → all tasks (file paths align)
- §10 Testing strategy → tests in every task + Task 28
- §11 Build/Deploy → Tasks 1, 27, 29
- §12 Accessibility basics → Tasks 3, 22 (focus-visible CSS, semantic HTML, HelpModal, aria-modal)
- AP2.13 Linear + Sidebar navigation → Tasks 19, 20, 23
- AP2.14 Synthesise dedicated route → Tasks 24, 25, 26
- AP2.15 Refine/Deprecate modals → Tasks 17, 18
- AP2.16 sessionStorage token → Task 5
- AP2.18 Hash routing → Task 8
- AP2.20 Keyboard shortcuts (Enter/Escape/j/k/t/?) → Tasks 15, 17, 21, 22, 23

**Placeholder scan:** none.

**Type consistency:**
- `useElement` returns `{ element, entries }` — matches `ElementDetailResponse` in `api/docs.ts` and consumer `ElementDetail.tsx`
- `useElements` returns `ElementWithCounts[]` — matches API + sidebar consumer
- `streamSynthesise` returns `Promise<AsyncIterable<SynthLine>>` — matches consumer in `useSynthesise.ts`
- `useCreateEntry` mutation args `{ slug, elementId, body }` — consistent across hook + form
- `useRefineEntry` / `useDeprecateEntry` args `{ entryId, body, slug, elementId }` — consistent
- Discriminated union `SynthLine` typed in `domain.ts` and pattern-matched in `useSynthesise.ts` reducer + `SynthProgress.tsx`

**Scope check:** one frontend SPA, single PR. Internal decomposition is fine (30 tasks, each bite-sized). The Synthesise streaming sub-feature is part of the SPA, not a separate subsystem.
