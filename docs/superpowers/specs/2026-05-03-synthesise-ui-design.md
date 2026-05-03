# Synthesise UI — Design Spec

> **Date:** 2026-05-03
> **Phase:** A.1.2 (post-A.1.0 + A.1.1)
> **Goal:** Wire the existing A.5 synthetic-question generator into the SPA's
> Synthesise tab as an admin tool: read-only HTML preview + per-box question
> sidebar with generate/edit/delete + cancel.

## Problem

A.5 already shipped `goldens/creation/synthetic.py` (the LLM-driven generator
+ pysbd decomposition + embedding-dedup) and A.6 shipped the goldset
operations (`refine` / `deprecate`). The SPA's Synthesise tab is currently
a placeholder prompt-test playground. Wire the two together so an admin
can generate, review, and curate questions per element using the same
`mineru.json` + `segments.json` artifacts the extract pipeline produces.

## User flow

```
Files → Extract → Synthesise (active tab)

┌──────────────┬──────────────────────────┬───────────────────────┐
│ PDF viewer   │ HTML pane (read-only)    │ Questions sidebar     │
│              │                          │                       │
│ pages 1..N   │ <p data-source-box=...>  │ Selected box: p7-b3   │
│              │   "Body text…"           │                       │
│              │ </p>                     │ [⚡ Generate (1)]       │
│              │ <p data-source-box=...>  │ [⚡ Generate page]      │
│              │   "More text…"           │                       │
│              │                          │ Existing questions:   │
│              │                          │ ────────────────      │
│              │                          │ "Wie hoch ist…"        │
│              │                          │   ✏️ edit · 🗑 delete   │
│              │                          │ "Welche Norm…"         │
│              │                          │                       │
│              │                          │ [⚡ Generate file]       │
│              │                          │ ([cancel] while live) │
└──────────────┴──────────────────────────┴───────────────────────┘
```

- 1st click on a `[data-source-box]` → sidebar shows that box's existing questions + buttons.
- "Generate (1 box)" → sync POST, returns within seconds.
- "Generate page" / "Generate file" → NDJSON-streamed POST with progress; **Cancel** button while in flight.
- Each existing question: inline-edit on text (Enter or blur saves via A.6 `refine`); 🗑 button (A.6 `deprecate`).
- `max_questions_per_element = 5` hard-cap (per user direction).

## Backend

### vLLM client

Reuse `core/llm_clients/openai_direct/` since vLLM exposes an OpenAI-compatible API. Add a thin `vllm_remote/` package for self-documenting env names:

```python
# features/core/src/llm_clients/vllm_remote/config.py
@dataclass(frozen=True)
class VllmRemoteConfig:
    base_url: str
    model: str
    api_key: str  # vLLM's default has no auth, but the OpenAI SDK requires
                  # a non-empty key. Default: "vllm".

    @classmethod
    def from_env(cls):
        return cls(
            base_url=os.environ["VLLM_BASE_URL"],   # e.g. http://vllm:8000/v1
            model=os.environ["VLLM_MODEL"],         # e.g. mistralai/Mistral-7B-Instruct-v0.3
            api_key=os.getenv("VLLM_API_KEY", "vllm"),
        )
```

`VllmRemoteClient` constructs `OpenAIDirectClient` under the hood.

### Bridge: `MineruElementsLoader`

```python
# features/pipelines/local-pdf/src/local_pdf/synthetic/elements_loader.py
class MineruElementsLoader:
    """Reads mineru.json + segments.json and yields DocumentElements
    keyed by box_id. Non-discard kinds only."""

    def __init__(self, data_root: Path, slug: str): ...

    def elements(self) -> list[DocumentElement]:
        # Maps BoxKind → ElementType:
        #   paragraph → paragraph
        #   heading   → heading
        #   list_item → list_item
        #   table     → table  (content = stripped text from html_snippet_raw,
        #                       table_full_content = the raw HTML)
        #   figure    → figure (skipped — synthetic.py returns None for figure)
        #   caption   → paragraph (treat captions as text)
        #   formula   → paragraph (rare)
        #   auxiliary → skipped (page headers/footers, no questions)
        #   discard   → skipped
        ...
```

### Endpoints

```
features/pipelines/local-pdf/src/local_pdf/api/routers/admin/synthesise.py:

POST   /api/admin/docs/<slug>/synthesise            ?box_id=X | ?page=N | (none = full doc)
GET    /api/admin/docs/<slug>/questions             — all questions, grouped by box_id
GET    /api/admin/docs/<slug>/questions/<box_id>    — questions for one box
PATCH  /api/admin/docs/<slug>/questions/<question_id>   — body {text}; A.6 refine
DELETE /api/admin/docs/<slug>/questions/<question_id>   — A.6 deprecate
```

POST modes:
- **box_id present** → sync, returns `{"box_id": ..., "questions": [{id, text}]}`. Single LLM call, fast.
- **page or full** → `StreamingResponse` NDJSON, one event per element:
  ```
  {"event":"started","element_id":"p7-b3"}
  {"event":"question","element_id":"p7-b3","question_id":"...","text":"...","sub_unit":"sentence_2"}
  {"event":"completed","element_id":"p7-b3","accepted":3,"deduped":2}
  {"event":"done","total_elements":12,"total_accepted":31}
  ```

**Cancel**: the NDJSON loop checks `await request.is_disconnected()` between elements. When the frontend aborts the fetch, the loop exits cleanly.

**max_questions_per_element=5** hardcoded in the synthesise call.

The placeholder `/synthesise/test` endpoint is removed.

### Existing contract reused

- Goldset event log for entries (already exists, A.3).
- `synthesise_iter` for the streaming generator (A.5).
- `refine` / `deprecate` operations from A.6.
- `goldens.storage.read_active_entries(slug, source_element=...)` for filtering by box.

## Frontend

### `HtmlPreview.tsx` (new, ~60 LoC)

Read-only iframe-srcdoc that fires `onClickElement(boxId)` on a `data-source-box` click. Same pattern as the existing HtmlEditor's preview mode but standalone — no tabs, no edit. Keeps Synthesise PR orthogonal to PR #36 (in-place editor).

### `Synthesise.tsx` rewrite

Three-pane layout:
- **PDF pane** — same `PdfPage` + `BoxOverlay` as extract.
- **HTML preview** — `HtmlPreview` mounted with current page's html, click highlights box.
- **Questions sidebar** — `QuestionList` component, scoped to the highlighted box.

State machine for generation:
```
idle → running (cancellable) → done | cancelled | error
```

`Generate (1 box)` button:
- Disabled when no box highlighted.
- POST `/synthesise?box_id=X`, await JSON.
- Refetch questions for that box, append to list.

`Generate page` / `Generate file`:
- Shared "Generate" action with NDJSON streaming.
- Progress bar: `{n_completed} / {n_total} elements, {n_accepted} questions`.
- Cancel button dispatches `AbortController.abort()` on the fetch.

`QuestionList`:
- Reads from `useQuestions(slug, boxId)` query.
- Each row: question text (inline `contenteditable` on click), Edit/Save/Cancel state, Delete button.
- Optimistic update via React Query `onMutate`.

### New mutation/query hooks

```ts
// useSynthesise.ts
export function useQuestions(slug: string, boxId?: string)        // GET
export function useGenerateQuestions(slug: string)                 // POST sync (per-box)
export function useGenerateQuestionsStream(slug: string)           // NDJSON stream + cancel
export function useRefineQuestion(slug: string)                    // PATCH
export function useDeprecateQuestion(slug: string)                 // DELETE
```

## Cost / token guardrails

- `max_questions_per_element = 5` baked into the POST handler.
- No `--dry-run` UI for now (admin-only tool, low risk of misuse).
- Existing A.5 token-budget check remains (`max_prompt_tokens=8000`).

## Files touched

**Backend new:**
- `features/core/src/llm_clients/vllm_remote/{__init__.py,client.py,config.py}` — thin re-export.
- `features/pipelines/local-pdf/src/local_pdf/synthetic/elements_loader.py` — `MineruElementsLoader`.

**Backend modified:**
- `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/synthesise.py` — replace placeholder with full endpoint set.
- `features/pipelines/local-pdf/src/local_pdf/api/schemas.py` — `RefineQuestionRequest`, `GenerateQuestionsResponse`.

**Frontend new:**
- `frontend/src/admin/components/HtmlPreview.tsx` — lean read-only iframe + click listener.
- `frontend/src/admin/components/QuestionList.tsx` — sidebar list with inline edit/delete.
- `frontend/src/admin/hooks/useSynthesise.ts` — query + 4 mutation hooks.

**Frontend modified:**
- `frontend/src/admin/routes/Synthesise.tsx` — full rewrite.

**Tests:**
- Backend: `test_synthesise_router.py`, `test_mineru_elements_loader.py`.
- Frontend: vitest for `Synthesise.test.tsx` (basic shell), `QuestionList.test.tsx` (edit/delete contracts).

## Out of scope

- Curator-facing review (Phase D — `signal_einverstanden` / `signal_disqualifiziert`). This PR is admin-only base-creation.
- Bulk-approve UI for questions across the whole doc — admins refine/deprecate one at a time.
- Automatic re-generation when an element's html_snippet changes (manual trigger only, prevents surprise costs).

## Estimate

~2 days (backend ~1 day, frontend ~1 day, tests interleaved).
