# Independent Workspace Tabs + Global File Selector — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the workflow tabs top-level/independent, driven by a global `?file=` selector and a shared workspace shell, with each tab an auto-discovered feature module so tabs can be built in parallel and merged with no shared-file conflicts.

**Architecture:** A `WorkspaceLayout` renders the tab bar + file dropdown once; tabs are top-level routes derived from an auto-discovered registry (`import.meta.glob`); a `useActiveFile()` hook (the `?file=` URL query) is the single source of truth; a `TabRoute` gate shows an empty state for file-requiring tabs with no file. Existing tab files are wrapped by thin descriptors **in place** and converted one at a time.

**Tech Stack:** React 18, react-router-dom (HashRouter), TanStack Query, Vite (`import.meta.glob`), Tailwind, vitest + @testing-library/react + msw.

**Spec:** `docs/superpowers/specs/2026-06-29-independent-tabs-workspace-design.md`

## Global Constraints

- **Frontend-only.** No backend changes; `useDocs`/upload already exist. No import-boundary exposure.
- **Do not move or rewrite the big existing tab files** (`extract.tsx`, `Comparison.tsx`, `Provenienz.tsx`, etc.). Feature descriptors wrap them in place; conversions are surgical (remove the local bar, swap `useParams`→`useActiveFile`).
- **Feature descriptors import their icon directly from `lucide-react`** (NOT the `shared/icons` barrel) so adding a tab edits zero shared files.
- **`TabDescriptor.icon` type is `ComponentType<{ className?: string }>`** (matches `IconRail.RailItem.icon`; lucide icons satisfy it).
- **Active file = the `?file=<slug>` URL query param.** Verified to round-trip under HashRouter (`auth/routes/Login.tsx:15` already uses `useSearchParams`).
- **Tab order** (descriptor `order`): Dateien=0, Extrahieren=1, Synthese=2, Vergleich=3, Provenienz=4, Agent=5, Statistik=6.
- **Tab keys = route segments:** `files, extract, synthesise, compare, provenienz, agent, statistics`.
- **German UI copy**; match existing Tailwind tokens (`bam-cyan`, `text-ink-muted`, `border-line`, `bg-rail`).
- **Run tests:** `cd frontend && npx vitest run <path>`. Typecheck: `cd frontend && npm run typecheck` (or `npx tsc --noEmit`).
- **Transition is incremental:** during conversion, un-converted tabs keep their existing `/admin/doc/:slug/<tab>` routes + `DocStepTabs`; converted tabs move to the workspace. Redirects bridge converted tabs. Every intermediate state must stay functional. `DocStepTabs.tsx` is retired only in the final task.
- **Never mention AI/assistant tools** in commits/code/docs.

## File Structure

**New:**
- `frontend/src/admin/features/types.ts` — `TabDescriptor` interface.
- `frontend/src/admin/features/registry.ts` — auto-discovery (`import.meta.glob`) → `WORKSPACE_TABS`.
- `frontend/src/admin/features/<key>/tab.tsx` — one per tab (descriptor; default export). Slice 1: `files/`, `statistics/`. Slices 2–6: `extract/`, `synthesise/`, `compare/`, `provenienz/`, `agent/`.
- `frontend/src/admin/hooks/useActiveFile.ts` — the global selector hook.
- `frontend/src/admin/components/TabRoute.tsx` — file gate.
- `frontend/src/admin/components/WorkspaceLayout.tsx` — bar + dropdown + `<Outlet/>`.

**Modified:**
- `frontend/src/App.tsx` — registry-driven workspace routes + redirects + index→files.
- `frontend/src/shell/AdminShell.tsx` — drop the "Dokumente" rail item.
- Each tab route file (one per conversion) — remove its local `DocStepTabs` bar; swap `useParams`→`useActiveFile`.
- `frontend/src/admin/routes/inbox.tsx` — row-link retargeted (in the extract-conversion task).

**Retired (final task):** `frontend/src/admin/components/DocStepTabs.tsx`.

**Tests (new):** `useActiveFile.test.tsx`, `TabRoute.test.tsx`, `registry.test.ts`, `WorkspaceLayout.test.tsx`, plus a redirects test; existing per-tab tests updated as each converts.

---

## Task 1: `useActiveFile` hook

**Files:**
- Create: `frontend/src/admin/hooks/useActiveFile.ts`
- Test: `frontend/src/admin/hooks/__tests__/useActiveFile.test.tsx`

**Interfaces:**
- Produces: `useActiveFile(): { file: string | null; setFile: (slug: string | null) => void }`. `file` = the `?file=` query value or null; `setFile(slug)` sets it, `setFile(null)` removes it.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/admin/hooks/__tests__/useActiveFile.test.tsx
import { MemoryRouter, useLocation } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { useActiveFile } from "../useActiveFile";

function Probe() {
  const { file, setFile } = useActiveFile();
  const loc = useLocation();
  return (
    <div>
      <span data-testid="file">{file ?? "none"}</span>
      <span data-testid="search">{loc.search}</span>
      <button onClick={() => setFile("b")}>set-b</button>
      <button onClick={() => setFile(null)}>clear</button>
    </div>
  );
}

describe("useActiveFile", () => {
  it("reads, sets, and clears the ?file= param", async () => {
    render(
      <MemoryRouter initialEntries={["/admin/extract?file=a"]}>
        <Probe />
      </MemoryRouter>
    );
    expect(screen.getByTestId("file")).toHaveTextContent("a");

    await userEvent.click(screen.getByText("set-b"));
    expect(screen.getByTestId("file")).toHaveTextContent("b");
    expect(screen.getByTestId("search")).toHaveTextContent("file=b");

    await userEvent.click(screen.getByText("clear"));
    expect(screen.getByTestId("file")).toHaveTextContent("none");
    expect(screen.getByTestId("search")).not.toHaveTextContent("file=");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/admin/hooks/__tests__/useActiveFile.test.tsx`
Expected: FAIL — cannot resolve `../useActiveFile`.

- [ ] **Step 3: Implement the hook**

```ts
// frontend/src/admin/hooks/useActiveFile.ts
import { useSearchParams } from "react-router-dom";

/** Global "active file" = the ?file=<slug> URL query param. Single source of
 * truth shared across all workspace tabs (the dropdown writes it, tabs read it). */
export function useActiveFile(): {
  file: string | null;
  setFile: (slug: string | null) => void;
} {
  const [params, setParams] = useSearchParams();
  const file = params.get("file");
  const setFile = (slug: string | null) => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (slug) next.set("file", slug);
        else next.delete("file");
        return next;
      },
      { replace: false }
    );
  };
  return { file, setFile };
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npx vitest run src/admin/hooks/__tests__/useActiveFile.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/admin/hooks/useActiveFile.ts frontend/src/admin/hooks/__tests__/useActiveFile.test.tsx
git commit -m "feat(workspace): useActiveFile hook (?file= global selector)"
```

---

## Task 2: `TabDescriptor` type + `TabRoute` gate

**Files:**
- Create: `frontend/src/admin/features/types.ts`
- Create: `frontend/src/admin/components/TabRoute.tsx`
- Test: `frontend/src/admin/components/__tests__/TabRoute.test.tsx`

**Interfaces:**
- Consumes: `useActiveFile` (Task 1).
- Produces:
  - `interface TabDescriptor { key: string; label: string; icon: ComponentType<{ className?: string }>; order: number; requiresFile: boolean; Component: ComponentType }`
  - `TabRoute({ descriptor }: { descriptor: TabDescriptor }): JSX.Element` — renders `descriptor.Component`, or an empty state when `requiresFile && !file`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/admin/components/__tests__/TabRoute.test.tsx
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Folder } from "lucide-react";
import { TabRoute } from "../TabRoute";
import type { TabDescriptor } from "../../features/types";

function makeDesc(requiresFile: boolean): TabDescriptor {
  return {
    key: "demo", label: "Demo", icon: Folder, order: 1, requiresFile,
    Component: () => <div>TAB-BODY</div>,
  };
}

describe("TabRoute", () => {
  it("shows the empty state when a file is required but none is selected", () => {
    render(
      <MemoryRouter initialEntries={["/admin/demo"]}>
        <TabRoute descriptor={makeDesc(true)} />
      </MemoryRouter>
    );
    expect(screen.queryByText("TAB-BODY")).not.toBeInTheDocument();
    expect(screen.getByText(/Bitte wählen Sie oben rechts eine Datei/)).toBeInTheDocument();
  });

  it("renders the tab when a file is selected", () => {
    render(
      <MemoryRouter initialEntries={["/admin/demo?file=a"]}>
        <TabRoute descriptor={makeDesc(true)} />
      </MemoryRouter>
    );
    expect(screen.getByText("TAB-BODY")).toBeInTheDocument();
  });

  it("renders a file-agnostic tab regardless of file", () => {
    render(
      <MemoryRouter initialEntries={["/admin/demo"]}>
        <TabRoute descriptor={makeDesc(false)} />
      </MemoryRouter>
    );
    expect(screen.getByText("TAB-BODY")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/admin/components/__tests__/TabRoute.test.tsx`
Expected: FAIL — cannot resolve `../TabRoute` / `../../features/types`.

- [ ] **Step 3: Implement the type**

```ts
// frontend/src/admin/features/types.ts
import type { ComponentType } from "react";

/** A workspace tab, self-described by its own feature module. The registry
 * auto-discovers these (admin/features/<key>/tab.tsx default export), so adding
 * a tab edits zero shared files. */
export interface TabDescriptor {
  key: string; // URL segment + identity, e.g. "extract"
  label: string; // bar label, e.g. "Extrahieren"
  icon: ComponentType<{ className?: string }>; // import from lucide-react
  order: number; // bar position (Dateien=0 … Statistik=6)
  requiresFile: boolean; // true → gated behind a selected file
  Component: ComponentType; // the tab UI; reads useActiveFile() when requiresFile
}
```

- [ ] **Step 4: Implement `TabRoute`**

```tsx
// frontend/src/admin/components/TabRoute.tsx
import { useActiveFile } from "../hooks/useActiveFile";
import type { TabDescriptor } from "../features/types";

/** Shell-gated mount: a file-requiring tab shows a single empty state until a
 * file is selected, so each tab's body can assume a file is present. */
export function TabRoute({ descriptor }: { descriptor: TabDescriptor }): JSX.Element {
  const { file } = useActiveFile();
  const { Component, requiresFile } = descriptor;
  if (requiresFile && !file) {
    return (
      <div className="p-8 text-ink-muted text-sm">
        Bitte wählen Sie oben rechts eine Datei.
      </div>
    );
  }
  return <Component />;
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd frontend && npx vitest run src/admin/components/__tests__/TabRoute.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/admin/features/types.ts frontend/src/admin/components/TabRoute.tsx frontend/src/admin/components/__tests__/TabRoute.test.tsx
git commit -m "feat(workspace): TabDescriptor type + TabRoute file-gate"
```

---

## Task 3: Feature registry (auto-discovery) + Dateien & Statistik descriptors

**Files:**
- Create: `frontend/src/admin/features/registry.ts`
- Create: `frontend/src/admin/features/files/tab.tsx`
- Create: `frontend/src/admin/features/statistics/tab.tsx`
- Test: `frontend/src/admin/features/__tests__/registry.test.ts`

**Interfaces:**
- Consumes: `TabDescriptor` (Task 2); the existing `Inbox` (`admin/routes/inbox.tsx`) and `Statistics` (`admin/routes/Statistics.tsx`) components (wrapped, not modified here).
- Produces: `WORKSPACE_TABS: TabDescriptor[]` — all discovered descriptors, sorted ascending by `order`.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/admin/features/__tests__/registry.test.ts
import { describe, expect, it } from "vitest";
import { WORKSPACE_TABS } from "../registry";

describe("workspace registry", () => {
  it("auto-discovers descriptors, sorted by order, Dateien first", () => {
    expect(WORKSPACE_TABS.length).toBeGreaterThanOrEqual(2);
    const orders = WORKSPACE_TABS.map((t) => t.order);
    expect([...orders]).toEqual([...orders].sort((a, b) => a - b));
    expect(WORKSPACE_TABS[0].key).toBe("files");
    for (const t of WORKSPACE_TABS) {
      expect(typeof t.key).toBe("string");
      expect(typeof t.label).toBe("string");
      expect(typeof t.requiresFile).toBe("boolean");
      expect(t.Component).toBeTruthy();
      expect(t.icon).toBeTruthy();
    }
    expect(WORKSPACE_TABS.find((t) => t.key === "statistics")?.requiresFile).toBe(true);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/admin/features/__tests__/registry.test.ts`
Expected: FAIL — cannot resolve `../registry`.

- [ ] **Step 3: Create the Dateien descriptor**

```tsx
// frontend/src/admin/features/files/tab.tsx
import { Folder } from "lucide-react";
import { Inbox } from "../../routes/inbox";
import type { TabDescriptor } from "../types";

const descriptor: TabDescriptor = {
  key: "files",
  label: "Dateien",
  icon: Folder,
  order: 0,
  requiresFile: false,
  Component: Inbox,
};
export default descriptor;
```

- [ ] **Step 4: Create the Statistik descriptor**

```tsx
// frontend/src/admin/features/statistics/tab.tsx
import { BarChart3 } from "lucide-react";
import { Statistics } from "../../routes/Statistics";
import type { TabDescriptor } from "../types";

const descriptor: TabDescriptor = {
  key: "statistics",
  label: "Statistik",
  icon: BarChart3,
  order: 6,
  requiresFile: true,
  Component: Statistics,
};
export default descriptor;
```

- [ ] **Step 5: Implement the registry**

```ts
// frontend/src/admin/features/registry.ts
import type { TabDescriptor } from "./types";

// Auto-discover every admin/features/<key>/tab.tsx default export. Adding a tab
// = drop a folder; no shared file is edited. eager:true so the list is
// available synchronously for route + bar construction.
const modules = import.meta.glob("./*/tab.tsx", { eager: true });

export const WORKSPACE_TABS: TabDescriptor[] = Object.values(modules)
  .map((m) => (m as { default: TabDescriptor }).default)
  .sort((a, b) => a.order - b.order);
```

- [ ] **Step 6: Run to verify it passes**

Run: `cd frontend && npx vitest run src/admin/features/__tests__/registry.test.ts`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/admin/features/
git commit -m "feat(workspace): auto-discovery registry + Dateien & Statistik descriptors"
```

---

## Task 4: `WorkspaceLayout` (tab bar + file dropdown)

**Files:**
- Create: `frontend/src/admin/components/WorkspaceLayout.tsx`
- Test: `frontend/src/admin/components/__tests__/WorkspaceLayout.test.tsx`

**Interfaces:**
- Consumes: `WORKSPACE_TABS` (Task 3), `useActiveFile` (Task 1), `useDocs` (`admin/hooks/useDocs` → `DocMeta[]` with `slug`/`filename`), `useAuth`.
- Produces: `WorkspaceLayout(): JSX.Element` — a layout component rendering the tab bar (from the registry) + the file `<select>` on the right + `<Outlet/>`. Tab links preserve the active `?file=`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/admin/components/__tests__/WorkspaceLayout.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { WorkspaceLayout } from "../WorkspaceLayout";

vi.mock("../../../auth/useAuth", () => ({ useAuth: () => ({ token: "tok" }) }));

const server = setupServer(
  http.get("*/api/admin/docs", () =>
    HttpResponse.json([
      { slug: "doc-a", filename: "A.pdf", pages: 1, status: "raw", last_touched_utc: "t", box_count: 0 },
      { slug: "doc-b", filename: "B.pdf", pages: 2, status: "done", last_touched_utc: "t", box_count: 3 },
    ])
  )
);
beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<WorkspaceLayout />}>
            <Route path="admin/files" element={<div>FILES-OUTLET</div>} />
            <Route path="admin/statistics" element={<div>STATS-OUTLET</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("WorkspaceLayout", () => {
  it("renders the tab bar, the file dropdown, and the outlet", async () => {
    renderAt("/admin/files?file=doc-a");
    expect(screen.getByText("Dateien")).toBeInTheDocument();
    expect(screen.getByText("Statistik")).toBeInTheDocument();
    expect(screen.getByText("FILES-OUTLET")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("option", { name: "A.pdf" })).toBeInTheDocument());
    // dropdown reflects the active file
    expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("doc-a");
  });

  it("tab links carry the active ?file=", () => {
    renderAt("/admin/files?file=doc-a");
    const statsLink = screen.getByText("Statistik").closest("a") as HTMLAnchorElement;
    expect(statsLink.getAttribute("href")).toContain("file=doc-a");
  });

  it("changing the dropdown updates ?file= (outlet still mounts)", async () => {
    renderAt("/admin/statistics?file=doc-a");
    await waitFor(() => expect(screen.getByRole("option", { name: "B.pdf" })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByRole("combobox"), "doc-b");
    const statsLink = screen.getByText("Statistik").closest("a") as HTMLAnchorElement;
    expect(statsLink.getAttribute("href")).toContain("file=doc-b");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/admin/components/__tests__/WorkspaceLayout.test.tsx`
Expected: FAIL — cannot resolve `../WorkspaceLayout`.

- [ ] **Step 3: Implement `WorkspaceLayout`**

```tsx
// frontend/src/admin/components/WorkspaceLayout.tsx
import { Link, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../../auth/useAuth";
import { useDocs } from "../hooks/useDocs";
import { useActiveFile } from "../hooks/useActiveFile";
import { WORKSPACE_TABS } from "../features/registry";

/** The workspace shell: one tab bar (derived from the registry) + a global file
 * dropdown on the right, with the active tab below. Replaces the per-route
 * DocStepTabs bars. */
export function WorkspaceLayout(): JSX.Element {
  const { pathname } = useLocation();
  const { token } = useAuth();
  const docs = useDocs(token ?? "");
  const { file, setFile } = useActiveFile();
  const query = file ? `?file=${encodeURIComponent(file)}` : "";

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-1 px-4 py-2 bg-white flex-shrink-0 border-b border-line">
        {WORKSPACE_TABS.map((t) => {
          const active = pathname.endsWith(`/${t.key}`);
          const Icon = t.icon;
          return (
            <Link
              key={t.key}
              to={`/admin/${t.key}${query}`}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-sm ${
                active ? "bg-cyan-50 text-bam-cyan" : "text-ink-muted hover:bg-slate-100"
              }`}
            >
              <Icon className="w-4 h-4" />
              {t.label}
            </Link>
          );
        })}
        <select
          aria-label="Aktive Datei"
          className="ml-auto rounded border border-slate-300 px-2 py-1 text-sm max-w-xs"
          value={file ?? ""}
          onChange={(e) => setFile(e.target.value || null)}
        >
          <option value="">— Datei wählen —</option>
          {(docs.data ?? []).map((d) => (
            <option key={d.slug} value={d.slug}>
              {d.filename}
            </option>
          ))}
        </select>
      </div>
      <div className="flex-1 min-h-0 overflow-auto">
        <Outlet />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npx vitest run src/admin/components/__tests__/WorkspaceLayout.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/admin/components/WorkspaceLayout.tsx frontend/src/admin/components/__tests__/WorkspaceLayout.test.tsx
git commit -m "feat(workspace): WorkspaceLayout bar + global file dropdown"
```

---

## Task 5: Wire the workspace + convert Dateien & Statistik end-to-end

This is the integration task that makes Slice 1 a working vertical slice: registry-driven routing under `WorkspaceLayout`, the rail loses "Dokumente", redirects bridge the two converted tabs, and the two converted route files drop their own `DocStepTabs` bar (Statistik also swaps `useParams`→`useActiveFile`). Un-converted tabs (extract/synthesise/compare/provenienz/agent) keep their existing doc-scoped routes + `DocStepTabs` and stay reachable via the inbox row link.

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/shell/AdminShell.tsx:12-19` (drop the Dokumente rail item)
- Modify: `frontend/src/admin/routes/Statistics.tsx:1,4,35,47-52` (remove bar; `useParams`→`useActiveFile`)
- Modify: `frontend/src/admin/routes/inbox.tsx:10,44-46` (remove the `DocStepTabs` bar)
- Test: `frontend/src/__tests__/workspace-routing.test.tsx`

**Interfaces:**
- Consumes: `WorkspaceLayout` (Task 4), `TabRoute` (Task 2), `WORKSPACE_TABS` (Task 3), `useActiveFile` (Task 1).

- [ ] **Step 1: Savepoint tag before integration**

```bash
cd /home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft
git tag -f pre-workspace-tabs
git tag --list pre-workspace-tabs
```

- [ ] **Step 2: Write the failing routing/redirect test**

```tsx
// frontend/src/__tests__/workspace-routing.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { render, screen, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { App } from "../App";

vi.mock("../auth/useAuth", () => ({ useAuth: () => ({ token: "tok", role: "admin", name: "x", tenantSlug: null, logout: () => {} }) }));

const server = setupServer(
  http.get("*/api/admin/docs", () => HttpResponse.json([])),
  http.get("*/api/admin/tenants", () => HttpResponse.json({ tenants: [] })),
  http.get("*/api/admin/statistics/extract/:slug", () => HttpResponse.json({ slug: "doc-a", diagnostics: { split: 0, no_decomposition: 0, clean: 0, total: 0 }, register_boxes: 0, total_boxes: 0, register_rate: 0 })),
  http.get("*/api/admin/statistics/synthese/:slug", () => HttpResponse.json({ slug: "doc-a", questions_created: 0, questions_deprecated: 0, survival_rate: 1, vote_approved: 0, vote_rejected: 0, vote_approval_rate: null, vote_distribution: [] })),
  http.get("*/api/admin/statistics/provenienz/:slug", () => HttpResponse.json({ slug: "doc-a", plan_proposals: 0, expert_overrides: 0, correction_rate: null })),
  http.get("*/api/admin/statistics/capability-wishes", () => HttpResponse.json({ wishes: [] })),
);
beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("workspace routing", () => {
  it("legacy /admin/inbox redirects to /admin/files (Dateien tab)", async () => {
    renderAt("/admin/inbox");
    await waitFor(() => expect(screen.getByText("Dateien")).toBeInTheDocument());
  });

  it("legacy /admin/doc/:slug/statistics redirects to /admin/statistics?file=slug and renders", async () => {
    renderAt("/admin/doc/doc-a/statistics");
    await waitFor(() => expect(screen.getByRole("heading", { name: "Extrahieren", level: 2 })).toBeInTheDocument());
  });

  it("statistics tab with no file shows the empty state", async () => {
    renderAt("/admin/statistics");
    await waitFor(() => expect(screen.getByText(/Bitte wählen Sie oben rechts eine Datei/)).toBeInTheDocument());
  });
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/workspace-routing.test.tsx`
Expected: FAIL (no workspace routes / redirects yet).

- [ ] **Step 4: Convert `Statistics.tsx` — remove its bar, read the active file**

Replace the import line `import { useParams } from "react-router-dom";` (line 1) with `import { useActiveFile } from "../hooks/useActiveFile";`, delete the `import { DocStepTabs } from "../components/DocStepTabs";` line (4), change the slug read (line 35) and remove the bar wrapper (lines 49-51). The new top of the component + return:

```tsx
export function Statistics(): JSX.Element {
  const { file } = useActiveFile();
  const slug = file ?? "";
  const { token } = useAuth();
  const tokenStr = token ?? "";
  const extract = useExtractStats(slug, tokenStr);
  const synthese = useSyntheseStats(slug, tokenStr);
  const provenienz = useProvenienzStats(slug, tokenStr);
  const wishes = useCapabilityWishes(tokenStr);

  if (token === null) {
    return <div className="p-6 text-ink">Bitte zuerst anmelden.</div>;
  }

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 space-y-6">
```
(The `<div className="flex items-center px-4 py-2 bg-white flex-shrink-0"><DocStepTabs slug={slug} /></div>` block is removed; the bar now comes from `WorkspaceLayout`. Everything below the old bar — the `<section>` blocks — is unchanged.)

- [ ] **Step 5: Convert `inbox.tsx` — remove its bar**

Delete `import { DocStepTabs } from "../components/DocStepTabs";` (line 10) and remove the bar wrapper (lines 44-46), so the component returns its content directly:

```tsx
  return (
    <div className="flex flex-col h-full">
      <div className="p-6 flex-1 overflow-auto">
```
(Leave the row `Link` at line 85 → `/admin/doc/${d.slug}/extract` UNCHANGED for now — extract is not yet converted, so the old doc route keeps un-converted tabs reachable. It is retargeted in Task 6.)

- [ ] **Step 6: Drop "Dokumente" from the rail**

In `frontend/src/shell/AdminShell.tsx`, remove this line from `ADMIN_NAV` (line 13):
```ts
  { to: "/admin/inbox", match: "/admin/inbox", label: "Dokumente", icon: Inbox },
```
and drop the now-unused `Inbox` from the icon import on line 8.

- [ ] **Step 7: Wire registry routing + redirects in `App.tsx`**

Add imports near the other admin imports:
```tsx
import { WorkspaceLayout } from "./admin/components/WorkspaceLayout";
import { TabRoute } from "./admin/components/TabRoute";
import { WORKSPACE_TABS } from "./admin/features/registry";
```
Inside `<Route path="/admin" element={<AdminShell />}>`, replace the existing `<Route index element={<Navigate to="inbox" replace />} />` with `<Route index element={<Navigate to="files" replace />} />`, add the workspace layout block, and add the two converted-tab redirects. Remove the now-obsolete `<Route path="inbox" element={<Inbox />} />` and `<Route path="doc/:slug/statistics" element={<Statistics />} />` lines (they are replaced by the registry route + redirect). Keep the other `doc/:slug/*` routes:

```tsx
<Route index element={<Navigate to="files" replace />} />

{/* Workspace: registry-driven top-level tabs (Dateien, Statistik, …). */}
<Route element={<WorkspaceLayout />}>
  {WORKSPACE_TABS.map((d) => (
    <Route key={d.key} path={d.key} element={<TabRoute descriptor={d} />} />
  ))}
</Route>

{/* Bridges for converted tabs. */}
<Route path="inbox" element={<Navigate to="/admin/files" replace />} />
<Route path="doc/:slug/statistics" element={<RedirectWithSlug to="/admin/statistics?file=:slug" />} />
```

(`RedirectWithSlug` already exists in `App.tsx` and substitutes `:slug`; confirm it appends the query correctly — it replaces `:slug` anywhere in the target string including the query.)

- [ ] **Step 8: Run the routing test + the earlier suites**

Run: `cd frontend && npx vitest run src/__tests__/workspace-routing.test.tsx src/admin/hooks/__tests__/useActiveFile.test.tsx src/admin/components/__tests__/TabRoute.test.tsx src/admin/features/__tests__/registry.test.ts src/admin/components/__tests__/WorkspaceLayout.test.tsx`
Expected: PASS. Also run the existing Statistics test (now needs `?file=`): `npx vitest run src/admin/routes/__tests__/Statistics.test.tsx` — if it asserts via a `:slug` route, update it to mount `<Statistics/>` under `MemoryRouter initialEntries={['/admin/statistics?file=doc-a']}` (the component now reads `useActiveFile`, not `useParams`).

- [ ] **Step 9: Typecheck**

Run: `cd frontend && npm run typecheck` (or `npx tsc --noEmit`)
Expected: no errors. Confirm no remaining references to a removed `DocStepTabs` import in `Statistics.tsx`/`inbox.tsx`.

- [ ] **Step 10: Commit + savepoint**

```bash
git add frontend/src/App.tsx frontend/src/shell/AdminShell.tsx frontend/src/admin/routes/Statistics.tsx frontend/src/admin/routes/inbox.tsx frontend/src/admin/routes/__tests__/Statistics.test.tsx frontend/src/__tests__/workspace-routing.test.tsx
git commit -m "feat(workspace): registry routing + convert Dateien & Statistik to the shell"
git tag -f workspace-tabs-slice1
```

---

## Tasks 6–10: convert the remaining workflow tabs

Each follows the same shape (written out in full per task): add a feature
descriptor → remove the route's own `DocStepTabs` bar (preserving any
tab-specific controls in a body toolbar) → swap `useParams`→`useActiveFile` →
add the legacy redirect + remove the doc route in `App.tsx` → add an empty-state
assertion. The descriptor auto-appears in the workspace bar via the registry.

**Shared conversion recipe (applies to the route-file edit in each task):**
1. Delete `import { DocStepTabs } from "../components/DocStepTabs";`.
2. Replace the slug read with:
   ```tsx
   import { useActiveFile } from "../hooks/useActiveFile";
   // …inside the component:
   const { file } = useActiveFile();
   const slug = file ?? "";
   ```
   (Leave all existing `slug` / `slug!` usages unchanged — `slug` is still a
   string. Remove the now-unused `useParams` import **only if** nothing else in
   the file uses it.)
3. Edit the bar block as shown per task (remove `<DocStepTabs .../>`, keep
   controls).

### Task 6: Convert Extrahieren

**Files:**
- Create: `frontend/src/admin/features/extract/tab.tsx`
- Modify: `frontend/src/admin/routes/extract.tsx:11,92,383-388`
- Modify: `frontend/src/admin/routes/inbox.tsx:85` (retarget row link)
- Modify: `frontend/src/App.tsx` (redirect + remove doc route)
- Modify: `frontend/src/__tests__/workspace-routing.test.tsx`

- [ ] **Step 1: Descriptor**

```tsx
// frontend/src/admin/features/extract/tab.tsx
import { FileText } from "lucide-react";
import { Extract } from "../../routes/extract";
import type { TabDescriptor } from "../types";

const descriptor: TabDescriptor = {
  key: "extract", label: "Extrahieren", icon: FileText,
  order: 1, requiresFile: true, Component: Extract,
};
export default descriptor;
```

- [ ] **Step 2: Convert `extract.tsx`** — apply the shared recipe (steps 1–2 at
line 11 import + line 92 slug). For the bar (lines 383-388), drop `DocStepTabs`
and keep the controls as a right-aligned toolbar:

```tsx
const topBar = (
  <div className="flex items-center justify-end px-4 py-2 bg-white border-b border-line flex-shrink-0">
    {actionButtons}
  </div>
);
```

- [ ] **Step 3: Retarget the inbox row link** — in `inbox.tsx:85`, change
`to={`/admin/doc/${d.slug}/extract`}` to `to={`/admin/extract?file=${d.slug}`}`.

- [ ] **Step 4: `App.tsx`** — remove `<Route path="doc/:slug/extract" element={<Extract />} />` and add:
```tsx
<Route path="doc/:slug/extract" element={<RedirectWithSlug to="/admin/extract?file=:slug" />} />
```
(Remove the now-unused `Extract` import if `App.tsx` no longer references it directly.)

- [ ] **Step 5: Add the empty-state assertion** to `workspace-routing.test.tsx`:
```tsx
it("extract tab with no file shows the empty state", async () => {
  renderAt("/admin/extract");
  await waitFor(() => expect(screen.getByText(/Bitte wählen Sie oben rechts eine Datei/)).toBeInTheDocument());
});
```

- [ ] **Step 6: Run + typecheck**

Run: `cd frontend && npx vitest run src/__tests__/workspace-routing.test.tsx && npm run typecheck`
Expected: PASS, no type errors, no dangling `DocStepTabs` import in `extract.tsx`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/admin/features/extract/ frontend/src/admin/routes/extract.tsx frontend/src/admin/routes/inbox.tsx frontend/src/App.tsx frontend/src/__tests__/workspace-routing.test.tsx
git commit -m "feat(workspace): convert Extrahieren to a workspace tab"
```

### Task 7: Convert Synthese

**Files:** Create `frontend/src/admin/features/synthesise/tab.tsx`; Modify `Synthesise.tsx` (slug line 661, bar 308-343), `App.tsx`, `workspace-routing.test.tsx`.

- [ ] **Step 1: Descriptor**

```tsx
// frontend/src/admin/features/synthesise/tab.tsx
import { Sparkles } from "lucide-react";
import { Synthesise } from "../../routes/Synthesise";
import type { TabDescriptor } from "../types";

const descriptor: TabDescriptor = {
  key: "synthesise", label: "Synthese", icon: Sparkles,
  order: 2, requiresFile: true, Component: Synthesise,
};
export default descriptor;
```

- [ ] **Step 2: Convert `Synthesise.tsx`** — apply the shared recipe (slug at 661). In the bar (308-343), delete only the `<DocStepTabs slug={slug} />` line, keeping the wrapper and the `ml-auto` control group:

```tsx
<div className="flex items-center gap-2 px-4 py-2 bg-white flex-shrink-0">
  <div className="ml-auto flex items-center gap-2">
    {/* …existing duplicate + generate buttons, unchanged… */}
  </div>
</div>
```

- [ ] **Step 3: `App.tsx`** — replace `<Route path="doc/:slug/synthesise" element={<Synthesise />} />` with:
```tsx
<Route path="doc/:slug/synthesise" element={<RedirectWithSlug to="/admin/synthesise?file=:slug" />} />
```

- [ ] **Step 4: Empty-state assertion** in `workspace-routing.test.tsx`:
```tsx
it("synthese tab with no file shows the empty state", async () => {
  renderAt("/admin/synthesise");
  await waitFor(() => expect(screen.getByText(/Bitte wählen Sie oben rechts eine Datei/)).toBeInTheDocument());
});
```

- [ ] **Step 5: Run + typecheck + commit**

```bash
cd frontend && npx vitest run src/__tests__/workspace-routing.test.tsx && npm run typecheck
cd /home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft
git add frontend/src/admin/features/synthesise/ frontend/src/admin/routes/Synthesise.tsx frontend/src/App.tsx frontend/src/__tests__/workspace-routing.test.tsx
git commit -m "feat(workspace): convert Synthese to a workspace tab"
```

### Task 8: Convert Vergleich (clean bar)

**Files:** Create `frontend/src/admin/features/compare/tab.tsx`; Modify `Comparison.tsx` (slug 1233, bar 340-342), `App.tsx`, `workspace-routing.test.tsx`.

- [ ] **Step 1: Descriptor**

```tsx
// frontend/src/admin/features/compare/tab.tsx
import { GitCompare } from "lucide-react";
import { Comparison } from "../../routes/Comparison";
import type { TabDescriptor } from "../types";

const descriptor: TabDescriptor = {
  key: "compare", label: "Vergleich", icon: GitCompare,
  order: 3, requiresFile: true, Component: Comparison,
};
export default descriptor;
```

- [ ] **Step 2: Convert `Comparison.tsx`** — apply the shared recipe (slug at 1233). Remove the entire bar wrapper (lines 340-342):
```tsx
<div className="flex items-center px-4 py-2 bg-white flex-shrink-0">
  <DocStepTabs slug={slug} />
</div>
```
(Delete those three lines; the bar now comes from `WorkspaceLayout`.)

- [ ] **Step 3: `App.tsx`** — replace `<Route path="doc/:slug/compare" element={<Comparison />} />` with:
```tsx
<Route path="doc/:slug/compare" element={<RedirectWithSlug to="/admin/compare?file=:slug" />} />
```

- [ ] **Step 4: Empty-state assertion** in `workspace-routing.test.tsx`:
```tsx
it("compare tab with no file shows the empty state", async () => {
  renderAt("/admin/compare");
  await waitFor(() => expect(screen.getByText(/Bitte wählen Sie oben rechts eine Datei/)).toBeInTheDocument());
});
```

- [ ] **Step 5: Run + typecheck + commit**

```bash
cd frontend && npx vitest run src/__tests__/workspace-routing.test.tsx && npm run typecheck
cd /home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft
git add frontend/src/admin/features/compare/ frontend/src/admin/routes/Comparison.tsx frontend/src/App.tsx frontend/src/__tests__/workspace-routing.test.tsx
git commit -m "feat(workspace): convert Vergleich to a workspace tab"
```

### Task 9: Convert Provenienz

**Files:** Create `frontend/src/admin/features/provenienz/tab.tsx`; Modify `Provenienz.tsx` (slug 33, bar 78-81), `App.tsx`, `workspace-routing.test.tsx`.

- [ ] **Step 1: Descriptor**

```tsx
// frontend/src/admin/features/provenienz/tab.tsx
import { GitMerge } from "lucide-react";
import { Provenienz } from "../../routes/Provenienz";
import type { TabDescriptor } from "../types";

const descriptor: TabDescriptor = {
  key: "provenienz", label: "Provenienz", icon: GitMerge,
  order: 4, requiresFile: true, Component: Provenienz,
};
export default descriptor;
```

- [ ] **Step 2: Convert `Provenienz.tsx`** — apply the shared recipe (slug at 33, already `= ""`). In the bar (78-81), drop `DocStepTabs`, keep `ViewToggle` right-aligned:
```tsx
<div className="flex items-center justify-end px-4 py-2 bg-white border-b border-line">
  <ViewToggle view={view} onChange={setView} />
</div>
```

- [ ] **Step 3: `App.tsx`** — replace `<Route path="doc/:slug/provenienz" element={<Provenienz />} />` with:
```tsx
<Route path="doc/:slug/provenienz" element={<RedirectWithSlug to="/admin/provenienz?file=:slug" />} />
```

- [ ] **Step 4: Empty-state assertion** in `workspace-routing.test.tsx`:
```tsx
it("provenienz tab with no file shows the empty state", async () => {
  renderAt("/admin/provenienz");
  await waitFor(() => expect(screen.getByText(/Bitte wählen Sie oben rechts eine Datei/)).toBeInTheDocument());
});
```

- [ ] **Step 5: Run + typecheck + commit**

```bash
cd frontend && npx vitest run src/__tests__/workspace-routing.test.tsx && npm run typecheck
cd /home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft
git add frontend/src/admin/features/provenienz/ frontend/src/admin/routes/Provenienz.tsx frontend/src/App.tsx frontend/src/__tests__/workspace-routing.test.tsx
git commit -m "feat(workspace): convert Provenienz to a workspace tab"
```

### Task 10: Convert Agent (clean bar)

**Files:** Create `frontend/src/admin/features/agent/tab.tsx`; Modify `Agent.tsx` (slug 10, bar 112-114), `App.tsx`, `workspace-routing.test.tsx`.

- [ ] **Step 1: Descriptor**

```tsx
// frontend/src/admin/features/agent/tab.tsx
import { Bot } from "lucide-react";
import { Agent } from "../../routes/Agent";
import type { TabDescriptor } from "../types";

const descriptor: TabDescriptor = {
  key: "agent", label: "Agent", icon: Bot,
  order: 5, requiresFile: true, Component: Agent,
};
export default descriptor;
```

- [ ] **Step 2: Convert `Agent.tsx`** — apply the shared recipe (slug at 10, already `= ""`). Remove the entire bar wrapper (112-114):
```tsx
<div className="flex items-center px-4 py-2 bg-white flex-shrink-0">
  <DocStepTabs slug={slug} />
</div>
```

- [ ] **Step 3: `App.tsx`** — replace `<Route path="doc/:slug/agent" element={<Agent />} />` with:
```tsx
<Route path="doc/:slug/agent" element={<RedirectWithSlug to="/admin/agent?file=:slug" />} />
```

- [ ] **Step 4: Empty-state assertion** in `workspace-routing.test.tsx`:
```tsx
it("agent tab with no file shows the empty state", async () => {
  renderAt("/admin/agent");
  await waitFor(() => expect(screen.getByText(/Bitte wählen Sie oben rechts eine Datei/)).toBeInTheDocument());
});
```

- [ ] **Step 5: Run + typecheck + commit**

```bash
cd frontend && npx vitest run src/__tests__/workspace-routing.test.tsx && npm run typecheck
cd /home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft
git add frontend/src/admin/features/agent/ frontend/src/admin/routes/Agent.tsx frontend/src/App.tsx frontend/src/__tests__/workspace-routing.test.tsx
git commit -m "feat(workspace): convert Agent to a workspace tab"
```

---

## Task 11: Finalize — retire DocStepTabs, full sweep, savepoint

**Files:**
- Delete: `frontend/src/admin/components/DocStepTabs.tsx`
- Modify: `frontend/src/App.tsx` (verify only `doc/:slug/curators` remains doc-scoped)

- [ ] **Step 1: Confirm `DocStepTabs` has no remaining importers**

Run: `cd frontend && grep -rn "DocStepTabs" src/ | grep -v "DocStepTabs.tsx:"`
Expected: **no output** (all routes converted). If any remain, convert them before deleting.

- [ ] **Step 2: Delete the retired component**

```bash
git rm frontend/src/admin/components/DocStepTabs.tsx
```

- [ ] **Step 3: Confirm the workspace bar shows all seven tabs**

Add to `workspace-routing.test.tsx`:
```tsx
it("the workspace bar shows all seven tabs", async () => {
  renderAt("/admin/files");
  for (const label of ["Dateien", "Extrahieren", "Synthese", "Vergleich", "Provenienz", "Agent", "Statistik"]) {
    expect(await screen.findByText(label)).toBeInTheDocument();
  }
});
```

- [ ] **Step 4: Full frontend test + typecheck**

Run: `cd frontend && npx vitest run && npm run typecheck`
Expected: all PASS (incl. existing suites), no type errors.

- [ ] **Step 5: Confirm leftover doc routes**

Run: `grep -n "doc/:slug" frontend/src/App.tsx`
Expected: only redirects (`RedirectWithSlug`) + `doc/:slug/curators` (the non-tab DocCurators route) remain.

- [ ] **Step 6: Commit + savepoint**

```bash
git add -A frontend/src
git commit -m "feat(workspace): retire DocStepTabs; all tabs are workspace features"
git tag -f workspace-tabs-v1
```

---

## Self-Review (plan author)

**Spec coverage:** C1 TabDescriptor → Task 2. C2 registry + feature modules → Task 3 (+ each conversion adds its module). C3 useActiveFile → Task 1. C4 WorkspaceLayout → Task 4. C5 TabRoute gate → Task 2. C6 registry routing → Task 5. C7 migration (redirects, inbox link, drop Dokumente, DocCurators, bar-control audit) → Tasks 5/6/11 (controls preserved in Tasks 6/7/9). Sequencing (vertical slice → mechanical) → Tasks 1-5 then 6-10. Testing strategy → tests in every task.

**Placeholder scan:** none — every step has exact code/edits. The "shared conversion recipe" is concrete (delete import, swap slug, edit bar) and each task shows its specific bar edit verbatim.

**Type consistency:** `TabDescriptor` fields (`key/label/icon/order/requiresFile/Component`) are identical across the registry, all descriptors, `TabRoute`, and `WorkspaceLayout`. `useActiveFile` returns `{file, setFile}` consumed identically in `TabRoute`, `WorkspaceLayout`, and every converted route. Icon type `ComponentType<{className?:string}>` matches `RailItem`. Redirect target format `"/admin/<key>?file=:slug"` is consistent across Tasks 5-10 and relies on the existing `RedirectWithSlug`.

**Audit note:** Tasks 6 (Extrahieren), 7 (Synthese), 9 (Provenienz) preserve tab-specific bar controls (actionButtons / generate buttons / ViewToggle) in a body toolbar — verified against the current bar blocks. Tasks 8 (Vergleich) + 10 (Agent) have clean bars (only DocStepTabs) — fully removed.
