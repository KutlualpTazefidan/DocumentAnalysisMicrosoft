# Agent Tab (1b) — deepagents Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "Agent" tab (before Statistik) that runs the partner's `deepagents` deep-research agent — Azure GPT-4.1 + Azure AI Search over our existing `push-semantic-chunking-1` index — and streams a cited report into the UI. A *loose, self-contained* vertical slice we can try in-app and rip out or harden later.

**Architecture:** A self-contained `local_pdf.agent` module (the partner's `research_agent` lifted in, env-keys remapped to our `AI_FOUNDRY_*`/`AI_SEARCH_*`) builds a `create_deep_agent(...)` graph. One thin admin endpoint `POST /api/admin/agent/ask` drives `agent.astream(...)` and streams NDJSON activity + a final report. A new doc-step page `Agent.tsx` (the tab you asked for) consumes that NDJSON with the same `fetch`+reader pattern our other streaming pages use. Deliberately *not* threaded through our `LLMClient` abstraction or the Provenienz DAG; deepagents is added as an **optional `agent` extra** and imported **lazily**, so the rest of the backend imports and serves even without it installed.

**Tech Stack:** `deepagents==0.6.11` + `langchain-openai` (Azure GPT-4.1, `text-embedding-3-large`), Azure AI Search (`pocaisearchbam` / `push-semantic-chunking-1`), FastAPI `StreamingResponse` (NDJSON), React + Vite + HashRouter, lucide `Bot` icon. Backend serve venv = root `.venv` (Python 3.12.3).

**Scope guard (explicitly OUT of 1b — productionize-later):** our own orchestrator instead of the framework; doc-scoped retrieval filtering by slug; re-ingesting via our `microsoft` pipeline; any local/Qwen fallback; persistence/checkpointing; a markdown renderer; unit tests for the live-Azure path (1b uses integration **smoke** verification because every meaningful path calls live Azure).

**Verified facts the plan relies on** (from recon + a live Azure probe):
- Our `.env` already targets the partner's resources: `AI_SEARCH_ENDPOINT=https://pocaisearchbam.search.windows.net`, `AI_SEARCH_INDEX_NAME=push-semantic-chunking-1`, `AI_FOUNDRY_ENDPOINT=https://poc-sweden-ai-plattform.services.ai.azure.com/`, `EMBEDDING_DEPLOYMENT_NAME=text-embedding-3-large`, `AZURE_OPENAI_API_VERSION=2024-02-01`, plus `AI_FOUNDRY_KEY` + `AI_SEARCH_KEY`.
- **Self-verified by a read-only check on 2026-06-24** (not a subagent's word): `gpt-4.1` answers chat via `AI_FOUNDRY_ENDPOINT` (the `.services.ai.azure.com` form) + `AI_FOUNDRY_KEY` + api-version `2024-02-01` → returned "OK"; the index returns on-topic German content for the test query (`3.4 Brennelemente und Wärmeleistung`, `5.1.2 Berechnungsergebnisse`). The only missing config is `CHAT_DEPLOYMENT_NAME`.
- **The index `push-semantic-chunking-1` holds exactly ONE document** (`GNB B 147_2001`, ~45 chunks) — self-verified 2026-06-24. So the doc-agnostic endpoint querying the whole index is coherent for the demo (open GNB B 147 → ask → answers come from GNB B 147). Slug-scoped filtering stays OUT precisely because there is nothing else in the index to filter against yet.
- Admin auth is path-prefix ASGI middleware: any route under `/api/admin/...` is admin-gated automatically (no `Depends`).
- Backend serve venv is the **root** `.venv` (plain-pip/editable, NOT uv-workspace-managed). `azure-search-documents` + `openai` are already installed there (via the `retrieval`/`ingestion` features).

---

## File Structure

**Create (backend agent module — self-contained, lazy-imported):**
- `features/pipelines/local-pdf/src/local_pdf/agent/__init__.py` — package marker + re-exports.
- `features/pipelines/local-pdf/src/local_pdf/agent/prompts.py` — verbatim copy of the partner's `prompts.py` (no env coupling).
- `features/pipelines/local-pdf/src/local_pdf/agent/tools.py` — partner's `tools.py` with the 3 `os.getenv` keys remapped to ours + api-version/key from env.
- `features/pipelines/local-pdf/src/local_pdf/agent/build.py` — `build_agent()` factory (model + subagent + `create_deep_agent`); deepagents/langchain imported lazily here.
- `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/agent.py` — `router = APIRouter()` + `POST /api/admin/agent/ask` NDJSON stream.

**Create (frontend):**
- `frontend/src/admin/routes/Agent.tsx` — the new doc-step page (query box + activity log + report).

**Modify:**
- `features/pipelines/local-pdf/pyproject.toml` — add `[project.optional-dependencies].agent`.
- `.env` — add `CHAT_DEPLOYMENT_NAME=gpt-4.1`.
- `features/pipelines/local-pdf/src/local_pdf/api/app.py` — import + `include_router(agent_router)`.
- `frontend/src/admin/components/DocStepTabs.tsx` — `Bot` import, TABS entry, isActive line.
- `frontend/src/App.tsx` — `Agent` import + route.

---

## Task 0: Branch + dependencies + env config

**Files:** `features/pipelines/local-pdf/pyproject.toml`, `.env`

- [x] **Step 1: Branch off main**

```bash
cd /home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft
git checkout -b feat/agent-tab-deepagents-spike
```

- [x] **Step 2: Add the `agent` optional-dependency extra**

In `features/pipelines/local-pdf/pyproject.toml`, extend the existing `[project.optional-dependencies]` block (which currently holds only `test`) with:

```toml
agent = [
    "deepagents==0.6.11",
    "langchain-openai>=0.2",
]
```

- [ ] **Step 3: Install the extra into the ROOT serve venv**

```bash
source .venv/bin/activate
uv pip install -e 'features/pipelines/local-pdf[agent]'
```

Expected: resolves `deepagents==0.6.11` + the LangChain 1.x stack + `langchain-openai`. (May adjust `openai`'s version — verified harmless; re-checked in Step 5.)

> **BLOCKED (2026-06-24):** `uv pip install -e 'features/pipelines/local-pdf[agent]'` fails to resolve — a *pre-existing* pin conflict unrelated to the agent extra. The existing `dependencies` block pins `pypdf>=4.0,<5`, but every `mineru[core]>=3.0` now requires `pypdf>=5.6.0`, so uv concludes `local-pdf==0.1.0 cannot be used`. Same failure on a dry-run *without* the `[agent]` extra. The installed venv currently has `pypdf 6.10.2` + `mineru 3.1.6` (drifted past the pin). `deepagents`/`langchain_openai` are NOT installed. Needs a decision on the `pypdf` pin before Steps 3–6 can proceed; not improvising a fix per task rules.

- [ ] **Step 4: Add the chat deployment name to `.env`**

Append to `/home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft/.env`:

```
CHAT_DEPLOYMENT_NAME=gpt-4.1
```

(Keep `AZURE_OPENAI_API_VERSION=2024-02-01` — verified working with gpt-4.1. Do NOT add `AZURE_OPENAI_ENDPOINT`/`AZURE_OPENAI_API_KEY`: the model is built with explicit `AI_FOUNDRY_*` constructor args in Task 2.)

- [ ] **Step 5: Verify imports + that the existing Azure client still works**

```bash
source .venv/bin/activate
python -c "import deepagents, langchain_openai; from deepagents import create_deep_agent; print('deepagents OK', deepagents.__version__ if hasattr(deepagents,'__version__') else 'ok')"
python -c "from llm_clients.azure_openai import AzureOpenAIClient; print('AzureOpenAIClient import OK')"
```

Expected: both print OK, no `ImportError`.

- [x] **Step 6: Commit**

```bash
git add features/pipelines/local-pdf/pyproject.toml
git commit -m "build(agent): add optional deepagents extra for the Agent spike"
```

(`.env` is gitignored — not committed.)

---

## Task 1: Agent module (tools + prompts + build) and standalone smoke (the 1a checkpoint)

**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/agent/__init__.py`, `agent/prompts.py`, `agent/tools.py`, `agent/build.py`

- [x] **Step 1: Copy the partner prompts verbatim**

```bash
mkdir -p features/pipelines/local-pdf/src/local_pdf/agent
cp /home/ktazefid/Documents/projects/foreign_projects/check-science-documents/deepagents/research_agent/prompts.py \
   features/pipelines/local-pdf/src/local_pdf/agent/prompts.py
```

(`prompts.py` is pure strings with `{date}` / `{max_concurrent_research_units}` / `{max_researcher_iterations}` placeholders — no changes needed.)

- [x] **Step 2: Create `agent/tools.py`** (the two `@tool`s; search delegates to our retrieval pipeline)

> **Why not the partner's inline Azure SDK calls:** the repo's pre-commit hook `scripts/check_import_boundary.sh` restricts `openai.*` / `azure.search.*` imports to `features/pipelines/microsoft/retrieval/` + `features/core/src/llm_clients/`. A `tools.py` under `local-pdf` importing `openai`/`azure.search` would FAIL the commit. So the search tool delegates to our existing `query_index.hybrid_search` (which lives in the allowed package, reads the same `AI_FOUNDRY_*`/`AI_SEARCH_*` env, queries the same index). **Validated 2026-06-24:** `hybrid_search("Gesamtwärmeleistung … Brennelemente", top=3)` returns `§3.4 Brennelemente und Wärmeleistung` as the top hit. `langchain_core.tools` is not boundary-restricted. The tool keeps the name/signature/output-shape `azure_ai_search` so `prompts.py` (which references it) is unchanged. **Deviation from the partner (deferred refinement):** this is BM25+vector, not `query_type="semantic"` reranked — `score` is the search score, not a reranker score.

`features/pipelines/local-pdf/src/local_pdf/agent/tools.py`:

```python
"""Research tools for the Agent spike: corpus search + a reflection tool.

Search delegates to features/pipelines/microsoft/retrieval (`hybrid_search`) rather than
calling the Azure SDKs here, because the repo's import-boundary hook restricts
openai.* / azure.search.* imports to that package + core/llm_clients. hybrid_search reads
the same AI_FOUNDRY_*/AI_SEARCH_* env and queries the same index (push-semantic-chunking-1).
NOTE: BM25+vector, not semantic-reranked — the partner reference used query_type="semantic";
deferred as a refinement.
"""

from langchain_core.tools import tool

from query_index.search import hybrid_search


@tool(parse_docstring=True)
def azure_ai_search(query: str, top: int = 5) -> str:
    """Search the document index for information relevant to a given query.

    Uses the project's hybrid (text + vector) search over the indexed knowledge
    base to find relevant document sections.

    Args:
        query: Search query to execute against the document index
        top: Maximum number of results to return (default: 5)

    Returns:
        Formatted search results with section headings and content
    """
    hits = hybrid_search(query, top=top)
    if not hits:
        return f"No results found for query: '{query}'"
    parts = []
    for i, h in enumerate(hits, 1):
        heading = h.section_heading or "Untitled Section"
        parts.append(f"## [{i}] {heading}\n**Relevance Score:** {h.score}\n\n{h.chunk}\n\n---\n")
    return f"Found {len(parts)} result(s) for '{query}':\n\n" + "\n".join(parts)


@tool(parse_docstring=True)
def think_tool(reflection: str) -> str:
    """Tool for strategic reflection on research progress and decision-making.

    Use this tool after each search to analyze results and plan next steps systematically.

    Args:
        reflection: Your detailed reflection on research progress, findings, gaps, and next steps

    Returns:
        Confirmation that reflection was recorded for decision-making
    """
    return f"Reflection recorded: {reflection}"
```

- [x] **Step 3: Create `agent/build.py`** (model + subagent + `create_deep_agent`; lazy heavy imports)

`features/pipelines/local-pdf/src/local_pdf/agent/build.py`:

```python
"""Build the deepagents research agent (Azure GPT-4.1). Heavy imports are function-local
so importing this module (or the backend) never pulls deepagents/langchain unless the
agent path actually runs — keeps the `agent` extra optional."""

import os
from datetime import datetime


def build_agent():
    """Construct the compiled deepagents graph. Requires the `agent` extra installed."""
    from deepagents import create_deep_agent
    from langchain_openai import AzureChatOpenAI

    from local_pdf.agent.prompts import (
        RESEARCH_WORKFLOW_INSTRUCTIONS,
        RESEARCHER_INSTRUCTIONS,
        SUBAGENT_DELEGATION_INSTRUCTIONS,
    )
    from local_pdf.agent.tools import azure_ai_search, think_tool

    current_date = datetime.now().strftime("%Y-%m-%d")

    model = AzureChatOpenAI(
        azure_endpoint=os.environ["AI_FOUNDRY_ENDPOINT"],
        azure_deployment=os.environ["CHAT_DEPLOYMENT_NAME"],
        api_key=os.environ["AI_FOUNDRY_KEY"],
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
        temperature=0.0,
    )

    research_sub_agent = {
        "name": "research-agent",
        "description": "Delegate research to the sub-agent researcher. Only give this researcher one topic at a time.",
        "system_prompt": RESEARCHER_INSTRUCTIONS.format(date=current_date),
        "tools": [azure_ai_search, think_tool],
    }

    instructions = (
        RESEARCH_WORKFLOW_INSTRUCTIONS
        + "\n\n" + "=" * 80 + "\n\n"
        + SUBAGENT_DELEGATION_INSTRUCTIONS.format(
            max_concurrent_research_units=3,
            max_researcher_iterations=3,
        )
    )

    return create_deep_agent(
        model=model,
        tools=[azure_ai_search, think_tool],
        system_prompt=instructions,
        subagents=[research_sub_agent],
    )
```

- [x] **Step 4: Create `agent/__init__.py`**

`features/pipelines/local-pdf/src/local_pdf/agent/__init__.py`:

```python
"""Self-contained deepagents research agent (Azure GPT-4.1 + Azure AI Search) for the Agent tab spike."""

from local_pdf.agent.build import build_agent

__all__ = ["build_agent"]
```

- [x] **Step 5: Standalone smoke (this is 1a — prove it works before any endpoint/UI)**

Use the **async `astream`** path here (not sync `.stream`) so this cheap gate exercises the exact production code path the endpoint uses (async file accumulation + event shapes + sync tools in langgraph's threadpool):

```bash
source .venv/bin/activate
set -a; source .env; set +a   # load Azure creds into the env
python - <<'PY'
import asyncio
from local_pdf.agent import build_agent
from deepagents.backends.utils import file_data_to_string

async def main():
    agent = build_agent()
    q = "Was ist die Gesamtwärmeleistung und wie wurde sie berechnet? Erkläre jeden einzelnen Schritt der Rechnung mit Quellenangabe, wo die Information herkommt."
    files = {}
    async for ns, chunk in agent.astream({"messages": [{"role": "user", "content": q}]}, stream_mode="updates", subgraphs=True):
        if not ns and isinstance(chunk, dict):
            for out in chunk.values():
                if isinstance(out, dict) and "files" in out:
                    files.update(out["files"])
        print("EVENT", ns, list(chunk.keys()) if isinstance(chunk, dict) else type(chunk))
    print("\n===== FINAL REPORT =====\n")
    print(file_data_to_string(files["/final_report.md"]) if "/final_report.md" in files else "(no report file)")

asyncio.run(main())
PY
```

**Go/no-go gate — CORRECTNESS, not formatting.** A cited report rendering is necessary but not sufficient. The test query is *verifiable*: read the report's cited calculation steps and check them against the actual GNB B 147 source — the Gesamtwärmeleistung is defined in **§3.4 (Brennelemente und Wärmeleistung)** and the results in **§5.1.2 (Berechnungsergebnisse)** (the index surfaces both). The spike PASSES only if the cited steps trace the *right* calculation from the *right* sections; a fluent-but-wrong report is a FAIL and a signal the retrieval/prompt needs work before wiring the UI. (If you don't have the ground-truth value to hand, this is the checkpoint to surface the report to the user for that judgment.)

- [x] **Step 6: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/agent/
git commit -m "feat(agent): self-contained deepagents research agent (Azure GPT-4.1 + AI Search)"
```

---

## Task 2: Backend NDJSON streaming endpoint

**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/agent.py`
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/app.py`

- [x] **Step 1: Create the endpoint** (`/api/admin/agent/ask`, NDJSON; lazy import; async `astream`; cancellation)

`features/pipelines/local-pdf/src/local_pdf/api/routers/admin/agent.py`:

```python
"""Agent spike endpoint: drives the deepagents research agent and streams NDJSON.

Mounted under /api/admin/ so it inherits admin auth from the ASGI middleware.
deepagents is imported lazily inside the handler so this router (and the app) import
fine even when the optional `agent` extra is not installed."""

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()


class AgentAskBody(BaseModel):
    question: str


@router.post("/api/admin/agent/ask")
async def agent_ask(body: AgentAskBody, request: Request) -> StreamingResponse:
    from deepagents.backends.utils import file_data_to_string  # lazy

    from local_pdf.agent import build_agent  # lazy

    agent = build_agent()

    async def _stream():
        files: dict = {}
        try:
            async for ns, chunk in agent.astream(
                {"messages": [{"role": "user", "content": body.question}]},
                stream_mode="updates",
                subgraphs=True,
            ):
                if await request.is_disconnected():
                    yield json.dumps({"event": "cancelled"}) + "\n"
                    return
                scope = " > ".join(ns) if ns else "orchestrator"
                if isinstance(chunk, dict):
                    for node_output in chunk.values():
                        if not isinstance(node_output, dict):
                            continue
                        if not ns and "files" in node_output:
                            files.update(node_output["files"])
                        for msg in node_output.get("messages", []):
                            for tc in getattr(msg, "tool_calls", None) or []:
                                yield json.dumps(
                                    {"event": "tool", "scope": scope, "name": tc.get("name", "?")},
                                    ensure_ascii=False,
                                ) + "\n"
                await asyncio.sleep(0)  # let the loop observe disconnects

            report = file_data_to_string(files["/final_report.md"]) if "/final_report.md" in files else ""
            yield json.dumps({"event": "report", "markdown": report}, ensure_ascii=False) + "\n"
            yield json.dumps({"event": "done"}) + "\n"
        except Exception as exc:  # surface failures to the UI instead of a dead stream
            yield json.dumps({"event": "error", "detail": str(exc)}, ensure_ascii=False) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")
```

- [x] **Step 2: Register the router in `create_app()`**

In `features/pipelines/local-pdf/src/local_pdf/api/app.py`, in the admin-router import block (~lines 94-113) add:

```python
from local_pdf.api.routers.admin.agent import router as agent_router
```

and in the registration block (~lines 115-132) add:

```python
app.include_router(agent_router)
```

- [ ] **Step 3: Restart the backend + smoke the endpoint** (DEFERRED to controller end-to-end; dev backend on :8001 is the user's process — not restarted here)

Restart serve (`bash scripts/dev-local-pdf.sh` in its terminal, or however it's running), then:

```bash
TOKEN=$(grep '^GOLDENS_API_TOKEN=' /tmp/be.env | cut -d= -f2 | tr -d '[:space:]')
curl -N -s -X POST http://127.0.0.1:8001/api/admin/agent/ask \
  -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{"question":"Was ist die Gesamtwärmeleistung und wie wurde sie berechnet? Erkläre jeden Schritt mit Quellenangabe."}' \
  | head -40
```

Expected: a stream of `{"event":"tool",...}` lines, then one `{"event":"report","markdown":"...cited German report..."}`, then `{"event":"done"}`. (A `{"event":"error",...}` line surfaces any failure instead of hanging.)

- [x] **Step 4: Verify the lazy-import guarantee (app still imports without the extra)**

```bash
source .venv/bin/activate
python -c "from local_pdf.api.app import create_app; create_app(); print('create_app OK (router import is lazy)')"
```

Expected: OK — importing the app does not require deepagents at module load.

- [x] **Step 5: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/api/routers/admin/agent.py features/pipelines/local-pdf/src/local_pdf/api/app.py
git commit -m "feat(agent): /api/admin/agent/ask NDJSON streaming endpoint"
```

---

## Task 3: Frontend Agent tab + page

**Files:**
- Modify: `frontend/src/admin/components/DocStepTabs.tsx`, `frontend/src/App.tsx`
- Create: `frontend/src/admin/routes/Agent.tsx`

- [x] **Step 1: Add `Bot` to the lucide import** (`DocStepTabs.tsx` line 2)

Change:
```ts
import { BarChart3, FileText, Folder, GitCompare, GitMerge, Sparkles } from "lucide-react";
```
to:
```ts
import { BarChart3, Bot, FileText, Folder, GitCompare, GitMerge, Sparkles } from "lucide-react";
```

- [x] **Step 2: Insert the Agent TABS entry** before the `statistics` entry (between current L15 provenienz and L16 statistics):

```ts
  { key: "agent", label: "Agent", icon: Bot, href: (slug: string) => `/admin/doc/${slug}/agent` },
```

- [x] **Step 3: Insert the isActive line** before the `statistics` check (current L28):

```ts
    if (key === "agent") return pathname.endsWith("/agent");
```

- [x] **Step 4: Add the route import + route in `App.tsx`**

Import (after the Provenienz import, current L10):
```ts
import { Agent } from "./admin/routes/Agent";
```
Route (inside the `<Route path="/admin" element={<AdminShell />}>` block, immediately before the statistics route at current L38):
```tsx
          <Route path="doc/:slug/agent" element={<Agent />} />
```

- [x] **Step 5: Create `frontend/src/admin/routes/Agent.tsx`** (tab-bar shell + query box + activity log + report; NDJSON via fetch+reader, `X-Auth-Token` auth, AbortController cancel)

```tsx
import { useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useAuth } from "../../auth/useAuth";
import { DocStepTabs } from "../components/DocStepTabs";
import { apiBase } from "../api/adminClient";

type ToolEvent = { scope: string; name: string };

export function Agent(): JSX.Element {
  const { slug = "" } = useParams<{ slug: string }>();
  const { token } = useAuth();
  const [question, setQuestion] = useState(
    "Was ist die Gesamtwärmeleistung und wie wurde sie berechnet? Erkläre jeden Schritt mit Quellenangabe.",
  );
  const [events, setEvents] = useState<ToolEvent[]>([]);
  const [report, setReport] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  async function run() {
    setEvents([]); setReport(""); setError(null); setRunning(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const r = await fetch(`${apiBase()}/api/admin/agent/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Auth-Token": token },
        body: JSON.stringify({ question }),
        signal: ctrl.signal,
      });
      if (!r.body) throw new Error("no response body");
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let nl = buf.indexOf("\n");
        while (nl !== -1) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (line) {
            const ev = JSON.parse(line);
            if (ev.event === "tool") setEvents((e) => [...e, { scope: ev.scope, name: ev.name }]);
            else if (ev.event === "report") setReport(ev.markdown);
            else if (ev.event === "error") setError(ev.detail);
          }
          nl = buf.indexOf("\n");
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError(String(e));
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center px-4 py-2 bg-white flex-shrink-0">
        <DocStepTabs slug={slug} />
      </div>
      <div className="p-6 overflow-auto space-y-4">
        <textarea
          className="w-full border border-line rounded p-2 text-[13px]"
          rows={3}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <div className="flex gap-2">
          <button className="btn-primary" onClick={run} disabled={running || !question.trim()}>
            {running ? "Läuft…" : "Agent fragen"}
          </button>
          {running && (
            <button className="btn-secondary" onClick={() => abortRef.current?.abort()}>
              Abbrechen
            </button>
          )}
        </div>
        {error && <div className="text-red-600 text-[13px]">Fehler: {error}</div>}
        {events.length > 0 && (
          <div className="text-[12px] text-ink-muted font-mono space-y-0.5">
            {events.map((e, i) => (
              <div key={i}>[{e.scope}] {e.name}</div>
            ))}
          </div>
        )}
        {report && (
          <pre className="whitespace-pre-wrap text-[13px] bg-white border border-line rounded p-4">{report}</pre>
        )}
      </div>
    </div>
  );
}
```

(Note: `btn-primary`/`btn-secondary` are existing classes; if the secondary class name differs, mirror whatever Provenienz/Synthese pages use. Report is rendered as preformatted text — no markdown renderer is a dep; prettifying is a later refinement.)

- [x] **Step 6: Typecheck + build**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: `tsc` + `vite build` exit 0.

- [x] **Step 7: Commit**

```bash
cd /home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft
git add frontend/src/admin/components/DocStepTabs.tsx frontend/src/App.tsx frontend/src/admin/routes/Agent.tsx
git commit -m "feat(agent): Agent doc-step tab + page streaming the research report"
```

---

## Task 4: End-to-end smoke + walkthrough guard

**Files:** none (verification)

- [ ] **Step 1: Manual end-to-end**

With backend (`:8001`) + frontend (`:5173`) up, log in as admin, open `GNB B 147_2001`, click the **Agent** tab (it sits right before Statistik), keep the default German question, click **Agent fragen**.

Expected: activity lines stream (write_todos / task / azure_ai_search / think_tool), then a cited German report renders. Confirm: the tab bar is the same height as the other steps (the `px-4 py-2` wrapper), the **Agent** tab shows the active cyan underline, and **Abbrechen** stops a run. **Apply the same correctness bar as Task 1 Step 5** — the in-app report must trace the real Gesamtwärmeleistung calculation (§3.4 / §5.1.2), not merely render; this UI smoke is about plumbing, but the user's accept/reject of the *spike* hinges on whether the answer is right.

- [ ] **Step 2: Confirm the walkthrough guard still passes** (we added a tab; the guard greps selectors)

```bash
cd frontend && npm run wt:guard 2>&1 | tail -3
```

Expected: "Walkthrough guard passed." (No record script references the new tab yet; a walkthrough recording for the Agent flow is a separate, later chore.)

- [ ] **Step 3: Final review pass**

Confirm no stray debug prints, the `.env` secret was not committed (`git status` clean of `.env`), and the four commits are scoped (build / agent module / endpoint / frontend).

---

## Self-Review (author)

- **Spec coverage:** tab-before-Statistik ✅ (Task 3); deepagents agent on Azure GPT-4.1 + our index ✅ (Task 1); loose/self-contained ✅ (optional extra + lazy import + no LLMClient/DAG coupling); triable in-app ✅ (Task 3/4). The 1a checkpoint is folded into Task 1 Step 5 as the go/no-go gate.
- **Placeholder scan:** none — every code file is given in full or is a verbatim `cp`; every command has expected output.
- **Type/name consistency:** endpoint path `/api/admin/agent/ask` matches the frontend `fetch`; event names (`tool`/`report`/`error`/`done`/`cancelled`) match between `agent.py` and `Agent.tsx`; `build_agent` exported from `local_pdf.agent` and imported in both the smoke script and the endpoint.
- **Known residual risks (acceptable for a spike, called out):** (1) `astream` event shape can vary across the LangChain 1.x line — the handler defensively guards types and the activity log is cosmetic, so a shape change degrades the log but not the report (which is read from VFS files). (2) First run is slow (multi-tool agent over Azure) — no timeout is set for the spike. (3) `btn-secondary` class name to be confirmed against existing pages.
