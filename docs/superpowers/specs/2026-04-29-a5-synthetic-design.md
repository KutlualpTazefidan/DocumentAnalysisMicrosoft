# Phase A.5 — `goldens/creation/synthetic.py` Design Spec

**Status:** Draft for review
**Date:** 2026-04-29
**Parent spec:** `docs/superpowers/specs/2026-04-28-goldens-restructure-design.md` (§7 Phase A — A.5 entry)
**Depends on:** A.1 (`llm_clients`), A.2 (`goldens/schemas/`), A.3 (`goldens/storage/`), A.4 (`goldens/creation/elements/` — element loader, in-flight)

This fragment concretises the parent spec's Phase A.5 entry. It does
not supersede the parent — it adds the LLM-driven generator, its
prompt-template storage convention, the sub-unit decomposition step
(pysbd), and the dedup-by-embedding pass needed to land the synthetic
goldset producer.

---

## 1. Scope

Build `goldens/creation/synthetic.py` — the **LLM-driven synthetic
goldset generator**. For every active `DocumentElement` from a
configured slug, it produces zero-or-more retrieval entries by:

1. Decomposing the element into testable **sub-units** (sentences for
   paragraphs, rows for tables, items for lists).
2. Asking an LLM to generate one question per sub-unit in a single
   JSON-mode call (with a per-sub-unit-call fallback when the prompt
   is too large).
3. Deduplicating against existing questions for the **same**
   `source_element` via cosine similarity over OpenAI embeddings.
4. Persisting each accepted question as a `created` event with
   `action="synthesised"` + `LLMActor`, written through
   `goldens.storage.append_event`.

Plus the supporting pieces:

- `goldens/creation/prompts/` — JSON prompt-template store with
  filename-suffix versioning and a schema-validating loader.
- `goldens/creation/synthetic_decomposition.py` — pysbd-backed
  sub-unit splitter (paragraph / table-row / list-item).
- `goldens/creation/synthetic_dedup.py` — embedding-based dedup with
  in-memory session cache and graceful disable when no embedding
  config is reachable.
- A new `query-eval synthesise` subparser registered in
  `query_index_eval.cli` that delegates to
  `goldens.creation.synthetic.cmd_synthesise`.

## 2. Goals & Non-Goals

### Goals

- One Python entry point — `synthesise(...)` — that takes a slug, an
  `ElementsLoader` (Q4), an `LLMClient`, and a config, and writes
  events. CLI is a thin argparse wrapper around it.
- Prompt templates live as **JSON files** with a stable on-disk
  layout (Q2) — versioned, schema-validated, no `.txt` blobs.
- Token-cost surprises are bounded: a `--dry-run` mode estimates
  prompt tokens via tiktoken without spending API budget; a default
  `--max-questions-per-element 20` cap prevents runaway generation
  (Q5).
- Dedup is **bounded** to questions with the same `source_element`
  (Q3-B) — O(n_per_element) embeddings, not O(N) global, and
  embedding cost is per-session, not per-call (cache).
- Resumable: `--resume` reads
  `goldens.storage.iter_active_retrieval_entries(path)` and skips
  elements that already have any active synthesised entry (Q5-Q).
- 70 %+ coverage per `docs/evaluation/coverage-thresholds.md`. The
  remaining 30 % is the combinatorial LLM-output space, exercised
  manually during validation, not in CI.
- Test the LLM call shape with **`respx`**, not by mocking
  `OpenAIDirectClient` — verifies the actual HTTP payload (model,
  temperature, response_format, messages structure) the way A.1's
  tests do.

### Non-Goals

- Running synthesised entries through Phase B/C consistency checks.
  This fragment writes raw `synthesised` events; the user-signal
  layer (Phase D) and functional-check layer (Phase B) consume them
  later.
- Persistent embedding cache. Q3-I locks the cache to in-memory per
  session — re-running a synthesise pass re-embeds. Persistence is
  YAGNI given the session length and the embedding cost ceiling
  (~0.13 €/M tokens for `text-embedding-3-large`).
- Re-implementing the element loader. A.4 owns
  `goldens/creation/elements/`; this fragment imports from it (Q4-B).
  Until A.4 merges, a **Protocol-stub** sits at the import site (§3)
  and the swap is a single-line edit.
- A `json-repair` integration. JSON-parse failures retry once, then
  skip the element with a warning (Q6 Safety-Net 1). No fuzzy
  recovery.
- Pricing math. `--dry-run` reports prompt-token counts only; no
  per-model € estimate (Q5-I).
- A second prompt-template version (`v2`). v1 is the only template
  shipped; the loader's filename-suffix scheme makes v2 a drop-in
  add when the calibration says so.
- Heading or figure questions. v1 generates 0 questions for those
  element types (Q6.2). A future phase may add caption-aware figure
  prompts.
- Wiring `synthesise` into `goldens/operations/`. Operations is the
  semantic-CRUD layer for *human-driven* edits (refine, deprecate);
  bulk synthesis writes one `created` event per question directly
  through `append_event` and skips the read-validate-write dance
  intentionally.
- Removing the `--llm-api-key` CLI flag is **enforced**, not
  optional: API keys come from `LLM_API_KEY` env only (Q5-B,
  security).

## 3. Package Layout

```
features/goldens/
├── pyproject.toml                                ← + pysbd, tiktoken, respx (test)
└── src/goldens/creation/
    ├── __init__.py                               ← re-exports synthesise + cmd_synthesise
    ├── synthetic.py                              ← main: synthesise() + cmd_synthesise()
    ├── synthetic_decomposition.py                ← decompose_to_sub_units()
    ├── synthetic_dedup.py                        ← QuestionDedup helper
    ├── elements/                                 ← OWNED BY A.4 (do not author here)
    └── prompts/
        ├── __init__.py                           ← load_prompt(element_type, version="v1")
        ├── paragraph_v1.json
        ├── table_row_v1.json
        └── list_item_v1.json
```

`features/evaluators/chunk_match/src/query_index_eval/cli.py`
gets one new subparser (`synthesise`) that imports
`goldens.creation.synthetic.cmd_synthesise`. No new console_script —
the existing `query-eval` entry point is reused.

`pysbd` and `tiktoken` are runtime deps; `respx` is a test-only dep.
All three live in `features/goldens/pyproject.toml` (the package that
imports them), not in chunk_match's pyproject.

```toml
# features/goldens/pyproject.toml additions
dependencies = [
    "pysbd>=0.3,<0.4",
    "tiktoken>=0.7",
]

[project.optional-dependencies]
test = ["pytest", "pytest-cov", "respx>=0.21"]
```

The LLM client itself lives in the existing `features/core/src/llm_clients/`
package and is imported by reference; A.5 does not re-declare it as a dep
(both packages are workspace-installed editable, same as today's
`from goldens import ...` in chunk_match).

## 4. API

### 4.1 Prompt-template loader — `prompts/__init__.py`

```python
def load_prompt(element_type: ElementType, version: str = "v1") -> str:
    """Return the prompt template string for `element_type` at `version`.

    Resolves `prompts/<element_type>_<version>.json`, validates the
    JSON against the prompt-template schema, asserts that the file's
    `element_type` and `version` fields match the filename, and
    returns `template`.

    Raises `PromptNotFoundError` if the file does not exist or
    `PromptSchemaError` on schema / filename mismatch.
    """
```

JSON schema (per Q2):

```json
{
  "version": "v1",
  "element_type": "paragraph",
  "description": "Generate one factual question per sentence ...",
  "template": "You are a domain expert ...\n\nElement type: paragraph\n\nText:\n{content}\n\n..."
}
```

The `template` field is the raw prompt. It is read verbatim — `\n`
escape sequences in the JSON file produce real newlines after
`json.loads`, so the on-disk file is editable in any editor without
manual line wrapping (rationale: `feedback_decouple_storage_from_edit_ux.md`).

`{content}` (and, for tables, `{row_text}`) are the only placeholders.
The template renderer is a stdlib `str.format`; missing placeholders
raise on render, not on load.

### 4.2 Sub-unit decomposition — `synthetic_decomposition.py`

```python
def decompose_to_sub_units(element: DocumentElement) -> tuple[str, ...]:
    """Decompose `element` into testable sub-units.

    Per element_type:
    - "paragraph"  → pysbd.split_into_sentences(content), de-stripped, drop empties
    - "table"      → one sub-unit per row (header + that row), preserving column
                     boundaries with " | " separator. Single-row tables → single
                     sub-unit; row-less tables → ().
    - "list_item"  → split content on "\n" and bullet/numbering patterns
                     (regex: ^\s*([-*•]|\d+\.)\s+); empty groups dropped
    - "heading"    → ()  # v1 skips (Q6.2)
    - "figure"     → ()  # v1 skips (Q6.2)

    pysbd is configured with `language="de"` per the corpus
    (German-language target documents); a `--language` CLI override
    plumbs through for non-German corpora.

    Returns a tuple (frozen) so the caller cannot mutate it and the
    dedup helper can hash it cheaply.
    """
```

The pysbd splitter is a module-level singleton (lazily constructed)
to avoid re-building the rule trie on every element.

### 4.3 LLM call shape — `synthetic.py`

A single function drives the per-element LLM call(s):

```python
def generate_questions_for_element(
    element: DocumentElement,
    sub_units: tuple[str, ...],
    *,
    client: LLMClient,
    model: str,
    prompt_template: str,
    temperature: float,
    max_prompt_tokens: int,
    tokenizer: tiktoken.Encoding,
) -> list[GeneratedQuestion]:
    """Return a list of `(sub_unit, question)` pairs.

    Strategy (Q6 + Safety-Net):
    1. Build the bundled prompt: serialize `[(idx, sub_unit), ...]`
       into the template's `{content}` slot.
    2. Estimate tokens with `tokenizer.encode(prompt)`.
       If > max_prompt_tokens → fall back to per-sub-unit calls (one
       LLM round-trip per sub_unit).
    3. Otherwise: 1 call with `response_format=json_object`.
    4. JSON-parse the response. On failure, retry exactly once
       (re-issue the same call). Second failure → log a warning,
       return [].
    5. Validate the parsed shape: `[{sub_unit, question}, ...]`.
       Any element of the list missing either field, or with an empty
       `question` string after `.strip()`, is dropped with a warning;
       the rest are kept. This guarantees the strings reaching
       `build_synthesised_event` (and therefore the persisted event)
       are non-empty.
    """
```

`GeneratedQuestion` is a small frozen dataclass local to
`synthetic.py`:

```python
@dataclass(frozen=True)
class GeneratedQuestion:
    sub_unit: str       # the source text the question is about
    question: str       # the generated question
```

Per Q6.2, the prompt content sent to the LLM is element-type-specific:
- **paragraph** → full element `content` (the paragraph text)
- **table**     → header row + the focus row only (not the full table)
                   embedded into the `table_row_v1.json` template
- **list_item** → full element `content` (the list as a whole)
- **heading / figure** → no call issued (sub_units is empty → skip)

### 4.4 Dedup — `synthetic_dedup.py`

```python
class QuestionDedup:
    """Bounded-scope dedup: questions are compared only against
    other questions for the same source_element.

    Workflow per session:
        dedup = QuestionDedup(client, model, threshold=0.95, log=...)
        for element, generated in ...:
            existing = existing_questions_for(element.source_element)
            kept = dedup.filter(generated, against=existing,
                                source_key=element.source_element.element_id)

    Embedding strategy:
    - Batch every `client.embed(texts, model=embedding_model)` call.
    - Cache by `source_key` for the session: existing questions are
      embedded once per source_element, generated questions are
      embedded once per call to `filter`.
    - Cosine similarity is computed against the union of (cached
      existing) ∪ (already-kept generated for this source_key) so
      runs that produce duplicates within the same call also dedup.

    Disabled mode:
    - If `client is None` (no `OPENAI_API_KEY` reachable, or
      embedding-model env var deliberately unset), `filter` returns
      `generated` unchanged and logs a single WARNING per session
      ("dedup disabled — no embedding client configured").
    """
```

Threshold 0.95 was chosen during brainstorming Q3 as a conservative
near-duplicate bar; it stays a constant in v1 and is not a CLI flag.

The cosine helper is local (numpy not added):

```python
def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0
```

### 4.5 Driver — `synthesise()`

```python
def synthesise(
    *,
    slug: str,
    loader: ElementsLoader,
    client: LLMClient,
    embed_client: LLMClient | None,            # None → dedup disabled
    model: str,
    embedding_model: str | None,
    prompt_template_version: str = "v1",
    temperature: float = 0.0,
    max_questions_per_element: int = 20,
    max_prompt_tokens: int = 8000,
    start_from: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    resume: bool = False,
    events_path: Path | None = None,           # default: outputs/<slug>/datasets/golden_events_v1.jsonl
) -> SynthesiseResult:
    """Walk `loader.elements()`, generate questions, write events.

    Returns a SynthesiseResult summary (see §4.6).

    On dry_run: estimates prompt-token counts via tiktoken for every
    element that would be processed, and returns a result whose
    `dry_run=True` and `events_written=0`. No LLM calls are issued
    (neither completion nor embedding).
    """
```

Internal flow (matches the brief's "LLM-Loop" section):

```
1. Resolve events_path (slug → outputs/<slug>/datasets/golden_events_v1.jsonl).
2. If resume: existing_keys = {e.source_element.element_id
                               for e in iter_active_retrieval_entries(events_path)
                               if e.source_element is not None}
3. Walk loader.elements(); apply --start-from / --limit filters in
   one pass:
     - skip elements until element.element_id == start_from is seen
       (when start_from is None, no skipping)
     - stop after `limit` elements have been yielded post-filter
       (when limit is None, all)
   For each yielded element:
     a. If resume and element.element_id in existing_keys → skip.
     b. sub_units = decompose_to_sub_units(element)
        if not sub_units: skip (element_type is heading/figure or content empty)
     c. if dry_run:
            estimate prompt_tokens via tokenizer.encode(rendered_prompt) and
            accumulate into the SynthesiseResult; do NOT call the LLM
            (neither completion nor embedding) and do NOT load existing
            questions. Continue to the next element.
     d. existing_questions = [e.query for e in active entries with same source_element]
     e. generated = generate_questions_for_element(element, sub_units, ...)
     f. kept = QuestionDedup.filter(generated, existing_questions, source_key=element.element_id)
     g. truncate kept to max_questions_per_element with WARNING if exceeded
     h. for q in kept:
            event = build_synthesised_event(element, q, actor=LLMActor(...))
            append_event(events_path, event)
4. Return SynthesiseResult(events_written=N, elements_skipped=M, ...)
```

`build_synthesised_event` constructs an `Event` whose payload matches
the parent spec's §4.2 `created` shape (see schemas/base.py and the
A.6 spec §6 for the analogous `refine` shape):

```python
Event(
    event_id=new_event_id(),
    timestamp_utc=now_utc_iso(),
    event_type="created",
    entry_id=new_entry_id(),
    schema_version=1,
    payload={
        "task_type": "retrieval",
        "actor": LLMActor(
            model=model,
            model_version=resolved_model_version,
            prompt_template_version=prompt_template_version,
            temperature=temperature,
        ).to_dict(),
        "action": "synthesised",
        "notes": None,
        "entry_data": {
            "query": q.question,
            "expected_chunk_ids": [],     # populated by A.7's chunk-match wiring; empty here
            "chunk_hashes": {},
            "refines": None,
            "source_element": SourceElement(
                document_id=loader.slug,
                page_number=element.page_number,
                # Strip the "p{page}-" prefix so the persisted element_id is
                # the bare 8-char content hash. Matches A.4's
                # loader.to_source_element() mapping (a4-curate spec §5.3) so
                # consumers joining/deduping on source_element.element_id see
                # one format regardless of whether the entry came from curate
                # or synthesise.
                element_id=element.element_id.split("-", 1)[1],
                element_type=element.element_type,
            ).to_dict(),
        },
    },
)
```

`expected_chunk_ids` and `chunk_hashes` are intentionally empty: the
ground-truth anchor for synthesised entries is the `source_element`,
and chunk-IDs are derived per pipeline at eval time
(`project_evaluation_ground_truth.md`). A.7's chunk-match rewire reads
`source_element` directly when these fields are empty.

`SourceElement` is constructed in `synthetic.py` from
`(loader.slug, element.page_number, element.element_id, element.element_type)`
rather than via a `loader.to_source_element(...)` helper. This keeps
the locked `ElementsLoader` Protocol minimal (`slug` + `elements()`,
matching the brief's contract) and avoids the synthetic generator
acquiring a dependency that A.4's loader-shape decisions would have
to honour.

`resolved_model_version` is sourced from the LLM response's `model`
field where available (OpenAI returns the dated alias); when absent
(Ollama, mocked tests) the configured `model` arg is reused as a
synonym to satisfy `LLMActor`'s non-empty constraint.

### 4.6 Result type

```python
@dataclass(frozen=True)
class SynthesiseResult:
    slug: str
    events_path: Path
    elements_seen: int
    elements_skipped: int               # heading/figure/empty/resume-hit
    elements_with_questions: int
    questions_generated: int            # before dedup
    questions_kept: int                 # after dedup + max-cap
    questions_dropped_dedup: int
    questions_dropped_cap: int
    events_written: int                 # = questions_kept on real run, 0 on dry_run
    prompt_tokens_estimated: int        # tiktoken sum across all calls (real or dry-run)
    dry_run: bool
```

Used by both the CLI's exit summary print and the test assertions.

### 4.7 CLI — `cmd_synthesise`

```python
def cmd_synthesise(args: argparse.Namespace) -> int:
    """Argparse handler. Builds the LLMClient/embed_client from env +
    flags, instantiates AnalyzeJsonLoader(slug=args.doc), and calls
    synthesise(...). Prints a SynthesiseResult summary. Returns 0 on
    success, 2 on missing inputs (events log path, slug), 1 on
    unhandled exception (logged via logging)."""
```

Subparser registration in `query_index_eval/cli.py:main()`:

```python
from goldens.creation.synthetic import cmd_synthesise   # NEW

p_synth = sub.add_parser("synthesise", help="Generate synthetic golden entries via LLM")
p_synth.add_argument("--doc", required=True)
p_synth.add_argument("--start-from", default=None)
p_synth.add_argument("--limit", type=int, default=None)
p_synth.add_argument("--llm-base-url", default=None)
p_synth.add_argument("--llm-model", default=None)
p_synth.add_argument("--embedding-model", default=None)
p_synth.add_argument("--prompt-template-version", default="v1")
p_synth.add_argument("--max-questions-per-element", type=int, default=20)
p_synth.add_argument("--temperature", type=float, default=0.0)
p_synth.add_argument("--max-prompt-tokens", type=int, default=8000)
p_synth.add_argument("--dry-run", action="store_true")
p_synth.add_argument("--resume", action="store_true")
p_synth.add_argument("--language", default="de")
p_synth.set_defaults(func=cmd_synthesise)
```

**Flag rationale (Q5):**
- B: no `--llm-api-key`. API key is read from `LLM_API_KEY` env only.
  Documented in the CLI's `--help`. Rejected during brainstorming as
  a security footgun (keys leak via shell history).
- I: `--dry-run` plans only — token counts via tiktoken, no LLM
  calls, no event writes.
- β: `--max-questions-per-element 20` is the default cap.
  Footgun-protection: a 50-sentence paragraph at 5 questions each
  would otherwise produce 50 events.
- Q: `--resume` auto-detects already-processed elements via
  `iter_active_retrieval_entries(events_path)` filtering on
  `source_element.element_id`. No state file.

**Env contract:**

| Env var | Purpose | Fallback if missing |
|---|---|---|
| `LLM_API_KEY` | Bearer for LLM endpoint | Hard error: `LLMConfigError` |
| `LLM_BASE_URL` | LLM endpoint base URL | `--llm-base-url` flag → `OpenAIDirectConfig` default `https://api.openai.com/v1` |
| `LLM_MODEL` | Default completion model | Hard error if `--llm-model` also unset |
| `LLM_EMBEDDING_MODEL` | Default embedding model | `text-embedding-3-large` if `OPENAI_API_KEY` set; otherwise dedup disabled with warning (Q3-α) |
| `OPENAI_API_KEY` | Existing key for `OpenAIDirectClient` (used by `embed_client`) | If set: dedup uses it. If unset: dedup disabled with warning. |

The completion client and the embed client are constructed
independently — `OpenAIDirectClient` for both, but with potentially
different `OpenAIDirectConfig.api_key` (rare; in v1 they share
`OPENAI_API_KEY` unless `LLM_API_KEY` is set separately for a
proxy/non-OpenAI completion endpoint).

## 5. Decision-history (Q1–Q6, locked)

| # | Topic | Decision | Why this fragment uses it |
|---|---|---|---|
| Q1 | Sub-unit splitter | `pysbd` (B) | Pure-Python, German support, handles DIN/M6/kN technical patterns. New runtime dep on `goldens`. |
| Q2 | Prompt-template storage | JSON files, filename-suffix versioning (D + i) | `prompts/<element_type>_<version>.json` schema-validated by `load_prompt`. Editing UX punted to a future helper UI; storage stays project-consistent (`feedback_decouple_storage_from_edit_ux.md`). |
| Q3 | Dedup | Same-source-element scope, OpenAI embeddings, in-memory cache, threshold 0.95 (B + α + I) | `QuestionDedup` is bounded by `source_element.element_id`, no global O(N) compares. No persistence. |
| Q4 | Element loader | Shared `goldens/creation/elements/`, owned by A.4 (B) | This fragment imports `DocumentElement` / `ElementsLoader` / `AnalyzeJsonLoader` / `ElementType`. Stub during overlap (§6). |
| Q5 | CLI flags | No `--llm-api-key`, separate `--embedding-model`, `--dry-run` plans only, default cap 20, `--resume` auto-detects (B + confirm + I + β + Q) | See §4.7. |
| Q6 | LLM call shape | One JSON-mode call per element with retry-once + per-sub-unit fallback; temperature 0.0; element-type-specific content (B + Safety-Net + I + Q6.2 confirm) | See §4.3. |

## 6. Loader-Stub hand-off (A.4 dependency)

A.4 (`a4-curate`) owns `goldens/creation/elements/` and is implementing
it in parallel. Until A.4 merges, `synthetic.py` imports a local
**Protocol stub** that mirrors the locked contract:

```python
# features/goldens/src/goldens/creation/_elements_stub.py
# DELETE-WHEN: a4-curate merges; replace import in synthetic.py with
#   from goldens.creation.elements import (
#       DocumentElement, ElementsLoader, AnalyzeJsonLoader, ElementType,
#   )
from dataclasses import dataclass
from typing import Literal, Protocol

ElementType = Literal["paragraph", "heading", "table", "figure", "list_item"]

@dataclass(frozen=True)
class DocumentElement:
    element_id: str
    page_number: int
    element_type: ElementType
    content: str
    table_dims: tuple[int, int] | None = None
    caption: str | None = None

class ElementsLoader(Protocol):
    slug: str
    def elements(self) -> list[DocumentElement]: ...
```

`AnalyzeJsonLoader` is **not** stubbed — the CLI handler is the only
consumer and we mark its construction `pragma: no cover` until A.4
lands. Tests inject a fake `ElementsLoader` directly into
`synthesise(...)`, never going through the loader factory.

The hand-off is a single PR after A.4 merges:
1. Delete `_elements_stub.py`.
2. Replace the import in `synthetic.py` (one line).
3. Replace the import in `synthetic_decomposition.py` (one line).
4. Run the goldens test suite — must pass unchanged.

## 7. Validation strategy

Four places where validation happens:

1. **Prompt loader (§4.1)** — `PromptSchemaError` on filename↔fields
   mismatch, missing required JSON keys, or unknown placeholders.
   Failing fast at import time would be wrong (the loader is called
   per-element). Failing fast at first call is right.

2. **LLM JSON parsing (§4.3)** — `JSONDecodeError` is caught,
   retried once, then suppressed-with-warn. The element is skipped,
   the next element proceeds. Additionally, individual generated
   items missing `sub_unit`/`question` or with an empty `question`
   string are dropped with a warning (§4.3 step 5), so the only
   strings that reach `build_synthesised_event` are non-empty
   `q.question` values.

3. **Event construction** — `build_synthesised_event` instantiates
   `LLMActor(...)` and `SourceElement(...)` before assembling the
   payload. Both dataclasses raise in `__post_init__` on empty
   required fields (see `schemas/base.py:LLMActor.__post_init__` and
   `schemas/base.py:SourceElement.__post_init__`). The outer `Event`
   then validates `event_id`, `entry_id`, `event_type`, `schema_version`,
   and `timestamp_utc` in its own `__post_init__`. Note: `Event` does
   **not** validate the payload contents — those validations are
   provided by the actor / source-element dataclasses above, and by
   the §4.3 step-5 question-string filter.

4. **Storage** — `goldens.storage.append_event` is the boundary.
   Synthetic does not call `append_events`; one event at a time is
   atomic enough for the per-question semantics (no two events
   describe the same logical action — contrast `refine` in A.6).

## 8. Race window

Synthetic does **not** read-then-write in the operations sense — it
only appends. Two concurrent `query-eval synthesise --doc <slug>`
processes against the same events log:

- Each process's `--resume` skip-set is a snapshot at start. Both
  may decide to (re-)synthesise the same `source_element` if neither
  has flushed yet. Result: duplicate `source_element` references with
  different `entry_id` and likely-similar but not byte-identical
  questions.
- `append_event`'s idempotency on `event_id` does not help here —
  the IDs differ.
- Dedup helps **within** a process, not across. Cross-process
  near-dup detection would require a load-state-then-decide-then-write
  primitive (the same primitive A.6 §7 declined to add).

This is documented as a known limitation, not closed. Operationally
the synthesis pass runs as a single batch job by a single user; the
collision window does not exist in practice. If two passes do
overlap, the resulting near-duplicates are caught in Phase D's
review (the human level filter rejects redundant questions and
`refine`/`deprecate` clean up).

## 9. Test plan

`features/goldens/tests/` gets four new test files:

| Test                                                                 | What it proves                                                                                          |
|----------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------|
| `test_creation_prompts::load_prompt_returns_template`                | Happy path: file exists, schema valid, returns the `template` field                                     |
| `test_creation_prompts::load_prompt_raises_on_unknown_element_type`  | `PromptNotFoundError` for `element_type="figure", version="v1"` (file does not exist by design)         |
| `test_creation_prompts::load_prompt_raises_on_filename_mismatch`     | Tampered file (filename says `paragraph_v1`, JSON says `element_type=table`) → `PromptSchemaError`      |
| `test_creation_prompts::load_prompt_raises_on_missing_keys`          | JSON missing `template` → `PromptSchemaError`                                                           |
| `test_creation_prompts::all_v1_files_load`                           | Smoke: every shipped `*_v1.json` file loads without error                                               |
| `test_creation_decomposition::paragraph_splits_into_sentences`       | German paragraph with `Dr.` / `M6` / `kN` → splits at sentence ends, not abbreviations                  |
| `test_creation_decomposition::table_splits_into_rows`                | 3-row table → 3 sub-units, each prefixed with header                                                    |
| `test_creation_decomposition::list_item_splits_on_bullets`           | Hyphen / bullet / numbered patterns                                                                     |
| `test_creation_decomposition::heading_and_figure_return_empty`       | `()` for both                                                                                           |
| `test_creation_dedup::filter_drops_above_threshold`                  | Two near-identical questions → one kept                                                                 |
| `test_creation_dedup::filter_keeps_dissimilar`                       | Two unrelated questions → both kept                                                                     |
| `test_creation_dedup::filter_dedups_within_call`                     | A single `filter([q1, q1_paraphrase], existing=[])` keeps one                                           |
| `test_creation_dedup::disabled_when_client_is_none`                  | `client=None` → returns input unchanged, single warning logged                                          |
| `test_creation_dedup::caches_existing_embeddings_per_session`        | Same `source_key` over two calls → embed_client.embed called once for `existing`                        |
| `test_creation_synthetic_respx::happy_path_writes_one_event_per_kept_question` | respx-mock OpenAI completion + embed; one paragraph → one event in the JSONL                  |
| `test_creation_synthetic_respx::json_parse_failure_retries_once_then_skips` | First response malformed, second OK → element processed; both malformed → skipped with warning   |
| `test_creation_synthetic_respx::oversize_prompt_falls_back_to_per_subunit` | tiktoken estimate > max_prompt_tokens → N calls instead of 1                                       |
| `test_creation_synthetic_respx::respects_max_questions_cap`          | LLM returns 30 questions, cap=5 → 5 events written, dropped count reported                              |
| `test_creation_synthetic_respx::dry_run_writes_no_events`            | `dry_run=True` → 0 LLM calls (assert via respx route counts), 0 events written, token estimate populated |
| `test_creation_synthetic_respx::resume_skips_already_processed_elements` | Pre-seed 1 active synthesised event for element X → second pass skips X, processes Y                |
| `test_creation_synthetic_respx::source_element_present_on_event`     | Event payload has `entry_data.source_element` with `document_id=loader.slug`, `page_number`/`element_type` from the loader element, and `element_id` equal to the **bare hash** (page prefix stripped, matching A.4's `build_event_source_element_id_strips_page_prefix`) |
| `test_creation_synthetic_respx::actor_is_llm_with_correct_metadata`  | Event's actor is `LLMActor` with `model`, `model_version`, `prompt_template_version="v1"`, `temperature=0.0` |
| `test_creation_cli::synthesise_subparser_wires_correctly`            | `query-eval synthesise --doc X --dry-run` returns 0; cmd_synthesise is invoked                          |

**Coverage target: 70 %** (per `docs/evaluation/coverage-thresholds.md`,
`creation/`-tier). The package-wide `--cov-fail-under=100` in
`features/goldens/pyproject.toml` is **lowered** for this PR — the
coverage block is changed to:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=goldens --cov-fail-under=70 --cov-branch --cov-report=term-missing"

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "class .*\\(Protocol\\):",
    "if TYPE_CHECKING:",
]
```

This is the per-tier minimum from `coverage-thresholds.md`. Schemas,
storage, and operations are still covered by their existing tests at
their respective tiers — the package-wide drop reflects the
intentionally thin coverage of `creation/`.

**Why `respx`, not a mocked `OpenAIDirectClient`:** A.1's tests mock
the HTTP layer, not the SDK call. Doing the same here verifies that:
- `response_format={"type": "json_object"}` is actually sent.
- `temperature=0.0` is actually sent.
- The retry-once branch issues exactly two HTTP requests, not one.
- The per-sub-unit fallback issues N requests, not 1.

Mocking the client object would let bugs in the `complete()` kwargs
slip through. respx is one extra dev dep; the coverage clarity is
worth it.

## 10. Commit / Plan granularity

The implementation lands as **four distinct commits** on the A.5
branch, in order. Each compiles and tests on its own:

1. **`feat(goldens/creation): add prompt-template store and loader (Phase A.5.1)`**
   — `prompts/__init__.py`, the three v1 JSON files, and
   `tests/test_creation_prompts.py`. Pure-Python, no LLM, no pysbd.
2. **`feat(goldens/creation): add sub-unit decomposition (Phase A.5.2)`**
   — `synthetic_decomposition.py`, the loader stub
   (`_elements_stub.py`), and `tests/test_creation_decomposition.py`.
   Adds `pysbd` to `pyproject.toml`.
3. **`feat(goldens/creation): add embedding-based question dedup (Phase A.5.3)`**
   — `synthetic_dedup.py` and `tests/test_creation_dedup.py`. Uses
   `respx` for the embed call; adds `respx` to test deps.
4. **`feat(goldens/creation): add synthesise driver + query-eval subparser (Phase A.5.4)`**
   — `synthetic.py`, the CLI subparser registration, the
   `_elements_stub.py` → real-loader hand-off plan, and
   `tests/test_creation_synthetic_respx.py` + `tests/test_creation_cli.py`.
   Adds `tiktoken` to `pyproject.toml` and lowers
   `--cov-fail-under` to 70.

PR description names all four, with explicit pointers so the reviewer
knows why `pyproject.toml`'s coverage threshold drops in commit 4.

## 11. Open questions

None for the design itself — Q1–Q6 are settled (§5) and not
relitigable.

Two open *coordination* items, both tracked outside this fragment:

1. **A.4 merge timing.** Until A.4 lands, `synthetic.py` imports
   from `_elements_stub.py`. The hand-off PR (§6) is a one-line
   import swap and a stub deletion. If A.4 merges first, the stub
   never lands on `main` — A.5's PR rebases onto the real loader
   directly.
2. **Coverage-threshold change in `pyproject.toml`.** Lowering
   `--cov-fail-under` from 100 to 70 for the goldens package is the
   one cross-cutting `pyproject.toml` edit. Flagged in the commit-4
   message; reviewer should explicitly approve before merge.

## 12. Out of scope

- Phase B/C functional checks on synthesised entries — Phase B reads
  `source_element` and runs CONTAINED-classification independently.
- A persistent embedding cache — see §2 Non-Goals.
- A second prompt-template version (`v2`) — future calibration phase.
- Integrating `synthesise` into `goldens/operations/` — operations is
  for human-driven CRUD; synthesis writes one `created` event per
  question through `append_event` directly.
- A `goldens-eval` standalone console_script — `query-eval synthesise`
  reuses the existing entry point. A future split (when the eval CLI
  outgrows chunk_match) is a separate refactor.
- Removing `--llm-api-key` from the *Lead's* internal scripts — out
  of scope; the security argument is "no API keys in CLI history,"
  and that applies to the user-facing CLI, not internal tooling.
