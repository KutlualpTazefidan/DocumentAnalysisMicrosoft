# Pydantic-v2 Core Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `@dataclass(frozen=True)` schemas in `goldens.schemas.{base,retrieval}` with Pydantic v2 `BaseModel(model_config=ConfigDict(frozen=True))`. Update all 6 callsites to use `model_dump` / `model_validate`. Preserve byte-equivalence of the JSONL event log.

**Architecture:** Big-bang migration in a single PR. The schema files are rewritten, callsites updated, and existing tests adapted in one atomic change. A canonical legacy fixture (generated using the *pre-migration* dataclass code, committed before the migration) anchors a byte-equivalence regression test that protects all existing event logs from accidental serialization drift.

**Tech Stack:** Pydantic v2.5+ · Python 3.11+ · pytest · existing `goldens` package layout.

**Spec:** `docs/superpowers/specs/2026-04-30-pydantic-core-migration-design.md`

---

## File Map

**Modified:**
- `features/goldens/pyproject.toml` — add `pydantic >= 2.5, < 3` dependency
- `features/goldens/src/goldens/schemas/base.py` — full rewrite (Pydantic BaseModels)
- `features/goldens/src/goldens/schemas/retrieval.py` — full rewrite
- `features/goldens/src/goldens/schemas/__init__.py` — re-exports stay; `actor_from_dict` keeps name (now wraps `TypeAdapter`)
- `features/goldens/src/goldens/storage/log.py` — line 41 + 101: `to_dict` → `model_dump(mode="json")`; line 64: `from_dict` → `model_validate`
- `features/goldens/src/goldens/storage/projection.py` — `replace(...)` → `model_copy(update=...)`; `actor_from_dict` keeps working
- `features/goldens/src/goldens/operations/refine.py` — `actor.to_dict()` → `actor.model_dump(mode="json")`
- `features/goldens/src/goldens/operations/deprecate.py` — same
- `features/goldens/src/goldens/creation/curate.py` — same
- `features/goldens/src/goldens/creation/synthetic.py` — same
- `features/goldens/tests/test_base.py` — `to_dict()` → `model_dump(mode="json")`; `from_dict` → `model_validate`; `FrozenInstanceError` → `pydantic.ValidationError`
- `features/goldens/tests/test_retrieval.py` — same
- `features/goldens/tests/test_storage_log.py` — `Event.from_dict` callsites in fixtures (if any)
- `features/goldens/tests/test_storage_log_bulk.py` — same
- `features/goldens/tests/test_storage_projection.py` — same

**Created:**
- `features/goldens/tests/fixtures/canonical_legacy_events.jsonl` — frozen pre-migration JSONL fixture (~10 events covering all type combinations)
- `features/goldens/tests/test_pydantic_byte_equivalence.py` — round-trip regression test that loads the canonical fixture, parses with Pydantic, re-serializes, and asserts byte-equality

---

## Task 1: Add Pydantic dependency

**Files:**
- Modify: `features/goldens/pyproject.toml:8-12`

- [ ] **Step 1: Read the current dependencies block**

Run: `grep -n "dependencies\|pysbd\|pytest-cov\|tiktoken" features/goldens/pyproject.toml`

Expected: shows the current `dependencies = [...]` block with `pysbd`, `pytest-cov`, `tiktoken`.

- [ ] **Step 2: Add `pydantic` to dependencies**

Edit `features/goldens/pyproject.toml`. Replace:

```toml
dependencies = [
    "pysbd>=0.3,<0.4",
    "pytest-cov>=7.1.0",
    "tiktoken>=0.7",
]
```

with:

```toml
dependencies = [
    "pydantic>=2.5,<3",
    "pysbd>=0.3,<0.4",
    "pytest-cov>=7.1.0",
    "tiktoken>=0.7",
]
```

Alphabetical order is preserved (`pydantic` < `pysbd`).

- [ ] **Step 3: Reinstall the package to pick up the new dep**

Run: `source .venv/bin/activate && uv pip install -e features/goldens`

Expected: install succeeds; `pydantic` is fetched.

- [ ] **Step 4: Verify Pydantic v2 is importable**

Run: `source .venv/bin/activate && python -c "import pydantic; print(pydantic.VERSION)"`

Expected: prints a version `2.5.x` or higher.

- [ ] **Step 5: Run existing test suite to confirm no regression from dep change alone**

Run: `source .venv/bin/activate && python -m pytest features/goldens/tests 2>&1 | tail -3`

Expected: `XYZ passed` with current count (likely 232).

- [ ] **Step 6: Commit**

```bash
git add features/goldens/pyproject.toml
PATH="$PWD/.venv/bin:$PATH" git commit -m "deps(goldens): add pydantic>=2.5 for upcoming schema migration"
```

---

## Task 2: Capture canonical legacy fixture (pre-migration)

This task runs the *current* dataclass code to produce a representative JSONL log, then commits it as a frozen fixture. The byte-equivalence test in Task 4 reads this fixture — every line must round-trip exactly through the migrated Pydantic models.

**Files:**
- Create: `features/goldens/tests/fixtures/canonical_legacy_events.jsonl`
- Create (temporary, not committed): `tools/_dump_canonical_events.py`

- [ ] **Step 1: Write the canonical-fixture generator script**

Create `tools/_dump_canonical_events.py` with this content:

```python
"""One-shot generator for tests/fixtures/canonical_legacy_events.jsonl.

Runs the *pre-migration* dataclass code to produce a representative JSONL
log. The file becomes a frozen safety-net for the Pydantic migration:
the migrated Pydantic models must read each line, re-serialize, and
produce byte-identical output.

This script is NOT committed. Delete after running.
"""

from __future__ import annotations

import json
from pathlib import Path

from goldens.schemas.base import Event, HumanActor, LLMActor, Review, SourceElement
from goldens.schemas.retrieval import RetrievalEntry  # noqa: F401  (imported to force consistent module loads)

OUT = Path("features/goldens/tests/fixtures/canonical_legacy_events.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)


def _iso(s: str) -> str:
    return s


def make_human_created_event() -> Event:
    actor = HumanActor(pseudonym="alice", level="phd")
    src = SourceElement(
        document_id="smoke-test-tragkorb",
        page_number=2,
        element_id="8e6e4a52",
        element_type="table",
    )
    payload = {
        "task_type": "retrieval",
        "actor": actor.to_dict(),
        "action": "created_from_scratch",
        "notes": None,
        "entry_data": {
            "query": "Welches Anzugsdrehmoment gilt für M10?",
            "expected_chunk_ids": [],
            "chunk_hashes": {},
            "source_element": src.to_dict(),
        },
    }
    return Event(
        event_id="ev_h_created_001",
        timestamp_utc=_iso("2026-04-30T07:00:00Z"),
        event_type="created",
        entry_id="e_001",
        schema_version=1,
        payload=payload,
    )


def make_llm_created_event() -> Event:
    actor = LLMActor(
        model="gpt-4o-mini",
        model_version="2024-07-18",
        prompt_template_version="v1",
        temperature=0.0,
    )
    src = SourceElement(
        document_id="smoke-test-tragkorb",
        page_number=1,
        element_id="8ac08a1e",
        element_type="paragraph",
    )
    payload = {
        "task_type": "retrieval",
        "actor": actor.to_dict(),
        "action": "synthesised",
        "notes": None,
        "entry_data": {
            "query": "Was ist die maximale Tragkraft des Tragkorbs?",
            "expected_chunk_ids": [],
            "chunk_hashes": {},
            "source_element": src.to_dict(),
        },
    }
    return Event(
        event_id="ev_l_created_001",
        timestamp_utc=_iso("2026-04-30T07:01:00Z"),
        event_type="created",
        entry_id="e_002",
        schema_version=1,
        payload=payload,
    )


def make_reviewed_event() -> Event:
    actor = HumanActor(pseudonym="bob", level="masters")
    payload = {
        "actor": actor.to_dict(),
        "action": "approved",
        "notes": "looks good to me",
    }
    return Event(
        event_id="ev_h_reviewed_001",
        timestamp_utc=_iso("2026-04-30T07:02:00Z"),
        event_type="reviewed",
        entry_id="e_001",
        schema_version=1,
        payload=payload,
    )


def make_deprecated_event() -> Event:
    actor = HumanActor(pseudonym="alice", level="phd")
    payload = {
        "actor": actor.to_dict(),
        "reason": "duplicate question",
    }
    return Event(
        event_id="ev_h_deprecated_001",
        timestamp_utc=_iso("2026-04-30T07:03:00Z"),
        event_type="deprecated",
        entry_id="e_002",
        schema_version=1,
        payload=payload,
    )


def make_event_no_source_element() -> Event:
    """Backward-compat: pre-A.3.1 entries have no source_element."""
    actor = HumanActor(pseudonym="legacy_user", level="bachelors")
    payload = {
        "task_type": "retrieval",
        "actor": actor.to_dict(),
        "action": "created_from_scratch",
        "notes": "imported pre-A.3.1",
        "entry_data": {
            "query": "Pre-A.3.1 entry without source_element",
            "expected_chunk_ids": ["B7-12"],
            "chunk_hashes": {"B7-12": "abc123"},
            "source_element": None,
        },
    }
    return Event(
        event_id="ev_h_legacy_001",
        timestamp_utc=_iso("2026-04-30T07:04:00Z"),
        event_type="created",
        entry_id="e_003",
        schema_version=1,
        payload=payload,
    )


def main() -> None:
    events = [
        make_human_created_event(),
        make_llm_created_event(),
        make_reviewed_event(),
        make_deprecated_event(),
        make_event_no_source_element(),
    ]
    with OUT.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")
    print(f"wrote {len(events)} canonical events to {OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the generator**

Run: `source .venv/bin/activate && python tools/_dump_canonical_events.py`

Expected output: `wrote 5 canonical events to features/goldens/tests/fixtures/canonical_legacy_events.jsonl`

- [ ] **Step 3: Verify the fixture is well-formed JSONL**

Run: `wc -l features/goldens/tests/fixtures/canonical_legacy_events.jsonl && head -1 features/goldens/tests/fixtures/canonical_legacy_events.jsonl | jq -r '"\(.event_type) entry_id=\(.entry_id) ts=\(.timestamp_utc)"'`

Expected: 5 lines; first line printed as `created entry_id=e_001 ts=2026-04-30T07:00:00Z`.

- [ ] **Step 4: Verify the fixture round-trips through the *current* dataclass code**

Run: `source .venv/bin/activate && python -c "
from pathlib import Path
import json
from goldens.schemas.base import Event
fx = Path('features/goldens/tests/fixtures/canonical_legacy_events.jsonl')
for line in fx.read_text(encoding='utf-8').splitlines():
    e = Event.from_dict(json.loads(line))
    redumped = json.dumps(e.to_dict(), ensure_ascii=False)
    assert redumped == line, f'pre-migration round-trip failure: {redumped!r} != {line!r}'
print('PASS — canonical fixture round-trips under current dataclass code')
"`

Expected: `PASS — canonical fixture round-trips under current dataclass code`

If this fails, the fixture is wrong (not the migration target's fault). Fix the generator and rerun.

- [ ] **Step 5: Delete the temporary generator script**

Run: `rm tools/_dump_canonical_events.py && rmdir tools 2>/dev/null || true`

The fixture file is permanent; the generator script was one-shot.

- [ ] **Step 6: Commit the canonical fixture**

```bash
git add features/goldens/tests/fixtures/canonical_legacy_events.jsonl
PATH="$PWD/.venv/bin:$PATH" git commit -m "test(goldens): canonical legacy event fixture for migration safety net"
```

---

## Task 3: Migrate `goldens/schemas/base.py` to Pydantic v2

This is the largest task. It rewrites `base.py` and updates everything downstream that imports from it. All sub-steps land in one commit because `base.py` cannot be half-migrated — its types reference each other and downstream modules import them as a unit.

**Files:**
- Modify: `features/goldens/src/goldens/schemas/base.py` (full rewrite)

- [ ] **Step 1: Read the current base.py end-to-end** (so the next edits are informed)

Run: `wc -l features/goldens/src/goldens/schemas/base.py` and ensure you have it in context. Reference values:
- `SourceElement` fields in declaration order: `document_id`, `page_number`, `element_id`, `element_type`
- `HumanActor` fields: `pseudonym`, `level`, `kind` (default `"human"`)
- `LLMActor` fields: `model`, `model_version`, `prompt_template_version`, `temperature`, `kind` (default `"llm"`)
- `Review` fields: `timestamp_utc`, `action`, `actor`, `notes` (default `None`)
- `Event` fields: `event_id`, `timestamp_utc`, `event_type`, `entry_id`, `schema_version`, `payload` (default `{}` via `field(default_factory=dict)`)

These orderings MUST be preserved verbatim in the Pydantic models for byte-equivalence.

- [ ] **Step 2: Rewrite `features/goldens/src/goldens/schemas/base.py`**

Replace the entire file with:

```python
"""Core schema models: Event, Review, HumanActor, LLMActor, SourceElement.

All models are `frozen=True` (Pydantic v2 ConfigDict). Validation lives
in `@field_validator` (replaces dataclass `__post_init__`). The Actor
union is `Annotated[HumanActor | LLMActor, Field(discriminator="kind")]`.

For backwards compatibility with callers that historically used the
dataclass `to_dict` / `from_dict` API, we keep `actor_from_dict` as a
helper that wraps `TypeAdapter[Actor].validate_python`. New code should
use `model_dump(mode="json")` / `model_validate` directly on the model
classes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator


def _validate_iso_utc(value: str) -> str:
    """Raise ValueError if value is not a parseable ISO-8601 UTC timestamp.

    Mirrors the dataclass `_validate_iso_utc` from the pre-Pydantic
    implementation so the validation surface is identical.
    """
    if not value:
        raise ValueError("timestamp_utc must be non-empty")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"timestamp_utc not ISO-8601: {value!r}") from e
    return value


ElementType = Literal["paragraph", "heading", "table", "figure", "list_item"]


class SourceElement(BaseModel):
    """A pipeline-independent reference to a structural element in a source document."""

    model_config = ConfigDict(frozen=True)

    document_id: str
    page_number: int
    element_id: str
    element_type: ElementType

    @field_validator("document_id", "element_id", mode="after")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("must be non-empty")
        return v

    @field_validator("page_number", mode="after")
    @classmethod
    def _page_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("page_number must be >= 1")
        return v


class HumanActor(BaseModel):
    model_config = ConfigDict(frozen=True)

    pseudonym: str
    level: Literal["expert", "phd", "masters", "bachelors", "other"]
    kind: Literal["human"] = "human"

    @field_validator("pseudonym", mode="after")
    @classmethod
    def _pseudonym_non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("pseudonym must be non-empty")
        return v


class LLMActor(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    model_version: str
    prompt_template_version: str
    temperature: float
    kind: Literal["llm"] = "llm"

    @field_validator("model", "model_version", "prompt_template_version", mode="after")
    @classmethod
    def _str_non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("must be non-empty")
        return v


# Discriminated union — Pydantic v2 dispatches on `kind` automatically.
Actor = Annotated[HumanActor | LLMActor, Field(discriminator="kind")]

# Module-level adapter for the union (TypeAdapter cannot be used inside
# a model; it's a free-standing utility for the projection layer).
_actor_adapter: TypeAdapter[HumanActor | LLMActor] = TypeAdapter(Actor)


def actor_from_dict(d: dict) -> HumanActor | LLMActor:
    """Dispatch on the 'kind' discriminator (backwards-compat helper)."""
    kind = d.get("kind")
    if kind not in ("human", "llm"):
        raise ValueError(f"unknown actor kind: {kind!r}")
    return _actor_adapter.validate_python(d)


CreateAction = Literal["created_from_scratch", "synthesised", "imported_from_faq"]
ReviewAction = Literal["accepted_unchanged", "approved", "rejected"]


_REVIEW_ACTIONS = (
    "created_from_scratch",
    "synthesised",
    "imported_from_faq",
    "accepted_unchanged",
    "approved",
    "rejected",
    "deprecated",
)


class Review(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp_utc: str
    action: Literal[
        "created_from_scratch",
        "synthesised",
        "imported_from_faq",
        "accepted_unchanged",
        "approved",
        "rejected",
        "deprecated",
    ]
    actor: Actor
    notes: str | None = None

    @field_validator("timestamp_utc", mode="after")
    @classmethod
    def _ts_iso(cls, v: str) -> str:
        return _validate_iso_utc(v)


_EVENT_TYPES = ("created", "reviewed", "deprecated")


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    timestamp_utc: str
    event_type: Literal["created", "reviewed", "deprecated"]
    entry_id: str
    schema_version: int
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id", "entry_id", mode="after")
    @classmethod
    def _id_non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("must be non-empty")
        return v

    @field_validator("schema_version", mode="after")
    @classmethod
    def _schema_version_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("schema_version must be >= 1")
        return v

    @field_validator("timestamp_utc", mode="after")
    @classmethod
    def _ts_iso(cls, v: str) -> str:
        return _validate_iso_utc(v)
```

Notes on the rewrite:
- `_ELEMENT_TYPES` (the explicit tuple) is gone — Pydantic checks `element_type` against the `Literal` automatically.
- `_REVIEW_ACTIONS` and `_EVENT_TYPES` tuples are kept (currently unreferenced after migration but harmless; leave for any external consumer).
- The hand-rolled `to_dict` / `from_dict` methods are gone. Callers use `model.model_dump(mode="json")` / `Cls.model_validate(d)` / `Cls.model_validate_json(s)`.
- `actor_from_dict(d)` keeps its name and signature so callers in `storage/projection.py` don't change.

- [ ] **Step 3: Verify base.py imports cleanly**

Run: `source .venv/bin/activate && python -c "from goldens.schemas import base; print(base.SourceElement, base.HumanActor, base.LLMActor, base.Review, base.Event, base.actor_from_dict)"`

Expected: prints class repr for each name; no ImportError, no syntax error.

- [ ] **Step 4: Verify the canonical fixture round-trips through the new Pydantic models**

Run:

```bash
source .venv/bin/activate && python -c "
from pathlib import Path
import json
from goldens.schemas.base import Event
fx = Path('features/goldens/tests/fixtures/canonical_legacy_events.jsonl')
for line in fx.read_text(encoding='utf-8').splitlines():
    e = Event.model_validate_json(line)
    redumped = json.dumps(e.model_dump(mode='json'), ensure_ascii=False)
    assert redumped == line, f'POST-migration round-trip failure: {redumped!r} != {line!r}'
print('PASS — canonical fixture round-trips under Pydantic v2')
"
```

Expected: `PASS — canonical fixture round-trips under Pydantic v2`

If this fails, the schema field-declaration order or default-handling does not match the dataclass version. Diff the failure line carefully — most likely cause is `kind` field reordered to the top. Fix and retry.

- [ ] **Step 5: Do NOT commit yet** — Task 3 continues into the production callsite updates. The full suite is broken right now (storage/operations/creation modules still call `to_dict` / `from_dict` on dataclass-types that no longer exist). This is expected; the next sub-tasks fix it.

---

## Task 4: Migrate `goldens/schemas/retrieval.py`

**Files:**
- Modify: `features/goldens/src/goldens/schemas/retrieval.py` (full rewrite)

- [ ] **Step 1: Rewrite the file**

Replace the entire content of `features/goldens/src/goldens/schemas/retrieval.py` with:

```python
"""RetrievalEntry — the first concrete entry type in the goldens
event-sourced model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from goldens.schemas.base import HumanActor, Review, SourceElement

_HUMAN_LEVEL_ORDER: tuple[str, ...] = (
    "expert",
    "phd",
    "masters",
    "bachelors",
    "other",
)


def _highest_level(
    review_chain: tuple[Review, ...],
) -> Literal["expert", "phd", "masters", "bachelors", "other", "synthetic"]:
    """Return the highest-ranked human level from the review chain;
    'synthetic' if no human has ever touched the entry."""
    human_levels = {r.actor.level for r in review_chain if isinstance(r.actor, HumanActor)}
    if not human_levels:
        return "synthetic"
    for tier in _HUMAN_LEVEL_ORDER:
        if tier in human_levels:
            return tier  # type: ignore[return-value]
    # Unreachable: HumanActor.level is constrained to the same Literal.
    raise ValueError(f"no recognised level in {human_levels}")  # pragma: no cover


class RetrievalEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry_id: str
    query: str
    expected_chunk_ids: tuple[str, ...]
    chunk_hashes: dict[str, str]
    review_chain: tuple[Review, ...]
    deprecated: bool
    refines: str | None = None
    task_type: Literal["retrieval"] = "retrieval"
    # Pipeline-independent ground truth: the source-document element from which
    # this entry's question was curated (Document Intelligence ID, stable across
    # pipelines). Optional for backward-compatibility with pre-A.3.1 entries.
    source_element: SourceElement | None = None

    @field_validator("entry_id", "query", mode="after")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("must be non-empty")
        return v

    @property
    def level(
        self,
    ) -> Literal["expert", "phd", "masters", "bachelors", "other", "synthetic"]:
        """Highest reviewer level in the chain. NOT serialized — derived state."""
        return _highest_level(self.review_chain)
```

Notes:
- `Field` is imported but not used in this file directly — leave for forward compat.
- `level` is a plain `@property`, not a `@computed_field`, so it stays out of `model_dump` output (matching the dataclass behaviour where `level` was not in `to_dict`).
- Field declaration order matches the dataclass exactly: `entry_id`, `query`, `expected_chunk_ids`, `chunk_hashes`, `review_chain`, `deprecated`, `refines`, `task_type`, `source_element`.

- [ ] **Step 2: Verify retrieval.py imports**

Run: `source .venv/bin/activate && python -c "from goldens.schemas.retrieval import RetrievalEntry, _highest_level; print(RetrievalEntry)"`

Expected: prints class repr.

- [ ] **Step 3: Do not commit yet** — production callsites still need updating.

---

## Task 5: Update `storage/log.py`

**Files:**
- Modify: `features/goldens/src/goldens/storage/log.py:41,64,101`

- [ ] **Step 1: Replace the `to_dict` write at line 41**

In `features/goldens/src/goldens/storage/log.py`, replace:

```python
            line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
```

with:

```python
            line = json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n"
```

- [ ] **Step 2: Replace the `from_dict` read at line 64**

In the same file, replace:

```python
                out.append(Event.from_dict(d))
```

with:

```python
                out.append(Event.model_validate(d))
```

- [ ] **Step 3: Replace the `to_dict` write at line 101 (in `append_events`)**

Replace:

```python
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
```

with:

```python
                f.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Verify storage/log.py imports clean**

Run: `source .venv/bin/activate && python -c "from goldens.storage.log import append_event, read_events, append_events; print('ok')"`

Expected: `ok`. (The functions don't run yet, just verify the import.)

- [ ] **Step 5: Do not commit yet** — projection.py is next.

---

## Task 6: Update `storage/projection.py`

`projection.py` uses `dataclasses.replace` (line 104, 122) which doesn't exist for Pydantic models — replaced by `model_copy(update=...)`. It also uses `actor_from_dict` and `SourceElement.from_dict` — the former keeps working, the latter must change.

**Files:**
- Modify: `features/goldens/src/goldens/storage/projection.py:23,76,104,122`

- [ ] **Step 1: Remove the `dataclasses.replace` import**

Replace line 23:

```python
from dataclasses import replace
```

with: (delete the line — `replace` is not needed anymore)

If the import block becomes empty after deletion, also remove blank lines.

- [ ] **Step 2: Replace `SourceElement.from_dict` at line 76**

In `_apply_created`, replace:

```python
    source_element = SourceElement.from_dict(src_raw) if src_raw is not None else None
```

with:

```python
    source_element = SourceElement.model_validate(src_raw) if src_raw is not None else None
```

- [ ] **Step 3: Replace `replace(entry, ...)` at line 104**

In `_apply_reviewed`, replace:

```python
    state[ev.entry_id] = replace(entry, review_chain=(*entry.review_chain, review))
```

with:

```python
    state[ev.entry_id] = entry.model_copy(update={"review_chain": (*entry.review_chain, review)})
```

- [ ] **Step 4: Replace `replace(entry, ...)` at line 122**

In `_apply_deprecated`, replace:

```python
    state[ev.entry_id] = replace(
        entry,
        review_chain=(*entry.review_chain, review),
        deprecated=True,
    )
```

with:

```python
    state[ev.entry_id] = entry.model_copy(
        update={
            "review_chain": (*entry.review_chain, review),
            "deprecated": True,
        }
    )
```

- [ ] **Step 5: Verify projection.py imports clean**

Run: `source .venv/bin/activate && python -c "from goldens.storage.projection import build_state, active_entries, iter_active_retrieval_entries; print('ok')"`

Expected: `ok`.

- [ ] **Step 6: Do not commit yet — operations next.**

---

## Task 7: Update `operations/refine.py` and `operations/deprecate.py`

Both call `actor.to_dict()` to embed in event payload. Mechanical replacement.

**Files:**
- Modify: `features/goldens/src/goldens/operations/refine.py`
- Modify: `features/goldens/src/goldens/operations/deprecate.py`

- [ ] **Step 1: Find every `to_dict` callsite in operations/**

Run: `grep -n "to_dict" features/goldens/src/goldens/operations/*.py`

Expected output (line numbers may differ slightly):

```
features/goldens/src/goldens/operations/deprecate.py:NN:    actor_dict = actor.to_dict()
features/goldens/src/goldens/operations/refine.py:NN:    actor_dict = actor.to_dict()
```

- [ ] **Step 2: Update `refine.py`**

Replace `actor.to_dict()` with `actor.model_dump(mode="json")` in `features/goldens/src/goldens/operations/refine.py`. Use Edit tool with the exact line as `old_string`.

- [ ] **Step 3: Update `deprecate.py`**

Same change in `features/goldens/src/goldens/operations/deprecate.py`.

- [ ] **Step 4: Verify operations import clean**

Run: `source .venv/bin/activate && python -c "from goldens.operations.refine import refine; from goldens.operations.deprecate import deprecate; print('ok')"`

Expected: `ok`.

- [ ] **Step 5: Do not commit yet — creation next.**

---

## Task 8: Update `creation/curate.py` and `creation/synthetic.py`

**Files:**
- Modify: `features/goldens/src/goldens/creation/curate.py`
- Modify: `features/goldens/src/goldens/creation/synthetic.py`

- [ ] **Step 1: Find every `to_dict` and `from_dict` callsite in creation/**

Run: `grep -n "to_dict\|from_dict" features/goldens/src/goldens/creation/*.py`

Expected: a handful of `actor.to_dict()`, `source_element.to_dict()`, possibly `Event.from_dict(...)` calls.

- [ ] **Step 2: For each `to_dict()` call, replace with `model_dump(mode="json")`**

In `creation/curate.py`, replace `actor.to_dict()` → `actor.model_dump(mode="json")`. Same for any other `.to_dict()` invocation on a schema instance.

In `creation/synthetic.py`, same pattern.

Be careful: `to_dict()` may also appear in non-schema places (e.g., `dict.items()` is unrelated). Only replace calls on schema instances.

- [ ] **Step 3: For each `from_dict(...)` call, replace with `model_validate(...)`**

If any exist in creation/, do the same mechanical swap.

- [ ] **Step 4: Verify creation/ imports clean**

Run: `source .venv/bin/activate && python -c "from goldens.creation.curate import cmd_curate; from goldens.creation.synthetic import synthesise; print('ok')"`

Expected: `ok`.

- [ ] **Step 5: Do not commit yet — tests next.**

---

## Task 9: Update `tests/test_base.py`

The existing tests call `obj.to_dict()`, `Cls.from_dict(d)`, and `actor_from_dict(d)`. They also assert `dataclasses.FrozenInstanceError` for immutability. All three patterns need migration.

**Files:**
- Modify: `features/goldens/tests/test_base.py`

- [ ] **Step 1: Update the imports**

Replace:

```python
from dataclasses import FrozenInstanceError
```

with:

```python
from pydantic import ValidationError
```

Keep the existing `from goldens.schemas.base import (...)` block as-is — those imports still work after migration.

- [ ] **Step 2: Replace `obj.to_dict()` → `obj.model_dump(mode="json")` everywhere in the file**

Search-and-replace pattern: `.to_dict()` → `.model_dump(mode="json")`. Be careful with any `Review.to_dict()` etc. — same replacement.

- [ ] **Step 3: Replace `Cls.from_dict(d)` → `Cls.model_validate(d)` everywhere**

Search-and-replace patterns:
- `HumanActor.from_dict(` → `HumanActor.model_validate(`
- `LLMActor.from_dict(` → `LLMActor.model_validate(`
- `SourceElement.from_dict(` → `SourceElement.model_validate(`
- `Review.from_dict(` → `Review.model_validate(`
- `Event.from_dict(` → `Event.model_validate(`

`actor_from_dict(d)` keeps its name — no change needed.

- [ ] **Step 4: Replace `FrozenInstanceError` with `ValidationError`**

Pydantic v2 frozen models raise `ValidationError` (not the dataclass-specific `FrozenInstanceError`) when a field is set on a frozen instance.

Find every `pytest.raises(FrozenInstanceError)` and replace with `pytest.raises(ValidationError)`.

- [ ] **Step 5: Inspect tests that constructed dataclass with kwargs out of order**

Pydantic accepts kwargs in any order. If any tests passed positional arguments relying on dataclass field order (e.g., `HumanActor("alice", "phd")` with positional pseudonym/level), those still work (Pydantic validates positional args from `__init__`). However, `HumanActor("human", "alice", "phd")` (passing `kind` first) would have failed under dataclass too — no real change.

Verify by running the suite (Step 6).

- [ ] **Step 6: Run `test_base.py`**

Run: `source .venv/bin/activate && python -m pytest features/goldens/tests/test_base.py -v 2>&1 | tail -20`

Expected: all tests pass (likely ~20-30 tests).

If a test fails on `pseudonym must be non-empty` or similar, the validator semantics may differ — Pydantic raises `ValidationError`, not `ValueError`. Tests using `pytest.raises(ValueError, match="...")` need to switch to `pytest.raises(ValidationError, match="...")`. Update mechanically.

- [ ] **Step 7: Do not commit yet — test_retrieval.py next.**

---

## Task 10: Update `tests/test_retrieval.py`

**Files:**
- Modify: `features/goldens/tests/test_retrieval.py`

- [ ] **Step 1: Update imports**

If the file imports `FrozenInstanceError`, swap for `ValidationError` from `pydantic` (same as Task 9).

- [ ] **Step 2: Mechanical to_dict / from_dict swap**

Same as Task 9 Steps 2-3:
- `.to_dict()` → `.model_dump(mode="json")`
- `RetrievalEntry.from_dict(` → `RetrievalEntry.model_validate(`
- Other `.from_dict(` invocations on schema instances → `.model_validate(`

- [ ] **Step 3: Validator-error swap**

Same as Task 9 Step 4: any `pytest.raises(FrozenInstanceError)` → `pytest.raises(ValidationError)`.

If tests assert on `ValueError` for "must be non-empty" etc., swap to `ValidationError`.

- [ ] **Step 4: Run test_retrieval.py**

Run: `source .venv/bin/activate && python -m pytest features/goldens/tests/test_retrieval.py -v 2>&1 | tail -20`

Expected: all tests pass.

- [ ] **Step 5: Do not commit yet.**

---

## Task 11: Update other test files affected by the migration

Storage and projection tests construct `Event` and `RetrievalEntry` instances and use `from_dict`. They need the same mechanical updates.

**Files:**
- Modify: `features/goldens/tests/test_storage_log.py`
- Modify: `features/goldens/tests/test_storage_log_bulk.py`
- Modify: `features/goldens/tests/test_storage_projection.py`
- Modify: any other test file that uses `to_dict` / `from_dict` on schema instances

- [ ] **Step 1: Find affected test files**

Run: `grep -rln "to_dict\|from_dict\|FrozenInstanceError" features/goldens/tests/ | grep -v __pycache__`

Expected: list of files. Already-updated `test_base.py` and `test_retrieval.py` will appear with no remaining hits if Tasks 9-10 were complete.

- [ ] **Step 2: For each remaining file, apply the same swaps**

- `.to_dict()` → `.model_dump(mode="json")`
- `Cls.from_dict(d)` → `Cls.model_validate(d)`
- `pytest.raises(FrozenInstanceError)` → `pytest.raises(ValidationError)` (after `from pydantic import ValidationError`)
- `pytest.raises(ValueError, match="<some validator msg>")` → `pytest.raises(ValidationError, match="<msg>")` IF the test was hitting one of the migrated `__post_init__` checks

Note: tests that raise `ValueError` from non-validator code (e.g., `int(s)` parse failures) are unchanged. Only validator-driven errors switch to `ValidationError`.

- [ ] **Step 3: Run the full goldens suite**

Run: `source .venv/bin/activate && python -m pytest features/goldens/tests 2>&1 | tail -5`

Expected: every test passes; coverage stays ≥95%.

If any tests fail with `ValidationError` instead of expected `ValueError`, see if the test should accept either. Update mechanically.

- [ ] **Step 4: Run ruff + format check**

Run: `.venv/bin/ruff check features/goldens && .venv/bin/ruff format --check features/goldens 2>&1 | tail -5`

Expected: `All checks passed!` and `N files already formatted`. If format fails, run `.venv/bin/ruff format features/goldens` and re-verify.

- [ ] **Step 5: Run pre-commit hooks (mypy, etc.)**

Run: `PATH="$PWD/.venv/bin:$PATH" pre-commit run --all-files 2>&1 | tail -10`

Expected: all hooks pass. Mypy may flag a few cases:
- Pydantic models accept kwargs at construction; mypy should accept them
- If mypy flags `_actor_adapter.validate_python` returning `HumanActor | LLMActor`, that's already the type — no fix needed
- If mypy complains about `model_copy(update={...})` typing, that's a Pydantic v2 quirk — add `# type: ignore[arg-type]` only where necessary, with a one-line explanation

- [ ] **Step 6: Big-bang commit**

All changes from Task 3-11 land in one commit. Stage everything:

```bash
git add features/goldens/src/goldens/schemas/base.py \
        features/goldens/src/goldens/schemas/retrieval.py \
        features/goldens/src/goldens/storage/log.py \
        features/goldens/src/goldens/storage/projection.py \
        features/goldens/src/goldens/operations/refine.py \
        features/goldens/src/goldens/operations/deprecate.py \
        features/goldens/src/goldens/creation/curate.py \
        features/goldens/src/goldens/creation/synthetic.py \
        features/goldens/tests/
PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF'
refactor(goldens): migrate schemas to Pydantic v2

Replace @dataclass(frozen=True) with BaseModel(model_config=ConfigDict(
frozen=True)) in goldens.schemas.{base,retrieval}. Validators move from
__post_init__ to @field_validator. Discriminated Actor union uses
Annotated[HumanActor | LLMActor, Field(discriminator="kind")] with a
module-level TypeAdapter exposed as actor_from_dict() for backwards-
compat.

Call-sites updated mechanically: to_dict() → model_dump(mode="json"),
from_dict() → model_validate(), dataclasses.replace → model_copy(
update=...). Tests updated to expect pydantic.ValidationError instead
of dataclasses.FrozenInstanceError where immutability is asserted.

JSONL byte-equivalence preserved via field-declaration-order parity
with the pre-migration dataclass definitions. Field ordering is now
the load-bearing invariant — see canonical fixture
(tests/fixtures/canonical_legacy_events.jsonl) for the regression net.

No behaviour change. Same module APIs, same exception types from the
caller's perspective (ValueError → ValidationError is the only
visible delta, and it surfaces in tests only).
EOF
)"
```

---

## Task 12: Add the byte-equivalence regression test

**Files:**
- Create: `features/goldens/tests/test_pydantic_byte_equivalence.py`

- [ ] **Step 1: Write the regression test**

Create `features/goldens/tests/test_pydantic_byte_equivalence.py` with:

```python
"""Byte-equivalence regression test for the Pydantic v2 migration.

The canonical fixture `tests/fixtures/canonical_legacy_events.jsonl`
was generated from the *pre-migration* dataclass code. Every line in
it must round-trip through the migrated Pydantic models and
re-serialize to byte-identical output.

If this test fails, either:
1. The schema field-declaration order has drifted from the dataclass
   version (most common cause).
2. A field's default-handling differs (e.g., Pydantic emits 'null'
   where the dataclass code omitted the key).
3. A nested model serializes differently (e.g., enum-like literals).

In all three cases, the fix is in the schema definitions, NOT the
fixture. Never edit the fixture to make the test pass — that would
silently invalidate every existing event log on disk.
"""

from __future__ import annotations

import json
from pathlib import Path

from goldens.schemas.base import Event

FIXTURE = Path(__file__).parent / "fixtures" / "canonical_legacy_events.jsonl"


def test_canonical_fixture_round_trip_byte_equivalence() -> None:
    """Every line in the canonical fixture round-trips byte-identically."""
    raw = FIXTURE.read_text(encoding="utf-8").splitlines()
    assert len(raw) > 0, "canonical fixture must not be empty"

    for lineno, line in enumerate(raw, start=1):
        event = Event.model_validate_json(line)
        redumped = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
        assert redumped == line, (
            f"byte-equivalence drift at line {lineno}\n"
            f"  original:  {line!r}\n"
            f"  redumped:  {redumped!r}"
        )


def test_canonical_fixture_covers_all_event_types() -> None:
    """The fixture must include at least one of each event type, so the
    round-trip test exercises all serialization paths."""
    seen_types: set[str] = set()
    seen_actor_kinds: set[str] = set()

    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        seen_types.add(d["event_type"])
        actor = d["payload"].get("actor")
        if actor:
            seen_actor_kinds.add(actor["kind"])

    assert seen_types == {"created", "reviewed", "deprecated"}, (
        f"fixture missing event types: {{'created','reviewed','deprecated'}} - {seen_types}"
    )
    assert seen_actor_kinds == {"human", "llm"}, (
        f"fixture missing actor kinds: {{'human','llm'}} - {seen_actor_kinds}"
    )
```

- [ ] **Step 2: Run the new test**

Run: `source .venv/bin/activate && python -m pytest features/goldens/tests/test_pydantic_byte_equivalence.py -v 2>&1 | tail -10`

Expected: 2 tests pass.

If `test_canonical_fixture_round_trip_byte_equivalence` fails, follow the failure message — it prints the original and redumped line. The diff is usually a field-order issue or a default-value mismatch. Fix in `goldens/schemas/base.py` or `retrieval.py`, NOT in the fixture.

- [ ] **Step 3: Run the full suite to confirm coverage**

Run: `source .venv/bin/activate && python -m pytest features/goldens/tests 2>&1 | tail -3`

Expected: previous count + 2 = total passed; coverage ≥95%.

- [ ] **Step 4: Commit**

```bash
git add features/goldens/tests/test_pydantic_byte_equivalence.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "test(goldens): byte-equivalence regression for Pydantic migration"
```

---

## Task 13: End-to-end smoke verification

After everything is migrated, run the same smoke checks the spec demands.

- [ ] **Step 1: Verify the existing Tragkorb event log loads cleanly**

Run:

```bash
source .venv/bin/activate && python -c "
from pathlib import Path
from goldens.storage.log import read_events
from goldens.storage.projection import iter_active_retrieval_entries
events = read_events(Path('outputs/smoke-test-tragkorb/datasets/golden_events_v1.jsonl'))
print(f'read {len(events)} events')
entries = list(iter_active_retrieval_entries(Path('outputs/smoke-test-tragkorb/datasets/golden_events_v1.jsonl')))
print(f'projected {len(entries)} active entries')
"
```

Expected: prints the existing event count and active-entry count. No `ValidationError`, no `KeyError`. (If this fails, the existing event log has fields the migrated schema doesn't accept — investigate; likely the migration missed an optional field.)

- [ ] **Step 2: CLI synthesise dry-run smoke**

Run: `source .venv/bin/activate && env -u LLM_API_KEY -u OPENAI_API_KEY query-eval synthesise --doc smoke-test-tragkorb --dry-run --llm-model gpt-4o-mini 2>&1 | tail -3`

Expected: `slug=smoke-test-tragkorb events_written=0 ... dry_run=True`. Same line as before the migration.

- [ ] **Step 3: CLI eval smoke** (chunk_match against the migrated event log)

Run: `source .venv/bin/activate && python -m pytest features/evaluators/chunk_match/tests 2>&1 | tail -3`

Expected: full chunk_match suite passes. (chunk_match transitively depends on `goldens` and reads via `iter_active_retrieval_entries` — this is the cross-package smoke.)

- [ ] **Step 4: Push the branch**

```bash
git push -u origin refactor/pydantic-core-migration
```

(Branch name assumed; the actual branch was created by the executor at the start of implementation. Adjust accordingly.)

- [ ] **Step 5: Open the PR**

```bash
gh pr create --title "refactor(goldens): migrate schemas to Pydantic v2" --body "$(cat <<'EOF'
## Summary
Prerequisite for A-Plus.1 (HTTP backend). Replaces frozen-dataclass-based \`goldens.schemas\` with Pydantic v2 BaseModels. Mechanical migration of 6 call-sites. Adds byte-equivalence regression test against a canonical fixture generated from the pre-migration dataclass code.

Spec: \`docs/superpowers/specs/2026-04-30-pydantic-core-migration-design.md\`

## What changed
- \`goldens/schemas/{base,retrieval}.py\`: \`@dataclass(frozen=True)\` → \`BaseModel(model_config=ConfigDict(frozen=True))\`. \`__post_init__\` → \`@field_validator\`. Discriminated Actor union via \`Annotated[..., Field(discriminator="kind")]\`.
- \`goldens/storage/{log,projection}.py\`: \`to_dict\` → \`model_dump(mode="json")\`, \`from_dict\` → \`model_validate\`, \`dataclasses.replace\` → \`model_copy(update=...)\`.
- \`goldens/operations/{refine,deprecate}.py\` + \`goldens/creation/{curate,synthetic}.py\`: \`actor.to_dict()\` → \`actor.model_dump(mode="json")\`.
- Tests updated to expect \`pydantic.ValidationError\` instead of \`dataclasses.FrozenInstanceError\` and \`ValueError\` from validator-driven failures.

## Byte-equivalence safety net
\`tests/fixtures/canonical_legacy_events.jsonl\` was generated by the pre-migration dataclass code. New test \`test_pydantic_byte_equivalence.py\` asserts that every line round-trips byte-identically through the migrated Pydantic models. Field-declaration order is now a load-bearing invariant — never reorder fields without updating the fixture (which would invalidate every existing log on disk).

## No behaviour change
- Module APIs unchanged (\`actor_from_dict\` keeps its name; same semantics)
- Same exception classes from the caller's perspective (only tests see \`ValidationError\` vs \`ValueError\` / \`FrozenInstanceError\` deltas)
- Existing event logs read unchanged

## Test plan
- [x] \`pytest features/goldens/tests features/evaluators/chunk_match/tests\` — full suite green, coverage ≥95%
- [x] ruff + format + mypy (pre-commit) — green
- [x] Byte-equivalence test against canonical fixture
- [x] Existing Tragkorb event log loads + projects without error
- [x] CLI synthesise dry-run still returns 0 with correct token estimate
EOF
)"
```

---

## Self-Review (executor: skip if running plan; this is a one-time pass for the plan author)

Spec coverage:
- §2 Goals (`pydantic >= 2.5, < 3` dep, schema migration, callsite update, byte-equivalence, no behaviour change) — covered by Tasks 1-13
- §3 Schema-by-Schema Plan (SourceElement / HumanActor / LLMActor / Review / Event / RetrievalEntry) — Tasks 3-4
- §4 Call-Site Migrations (storage/log, storage/projection, operations/refine, operations/deprecate, creation/curate, creation/synthetic) — Tasks 5-8
- §5 JSONL Byte-Compatibility (round-trip test, field ordering, None vs missing) — Tasks 2 + 12
- §6 Dependency-Layer (`pydantic` to `goldens`, not `core`) — Task 1
- §7 Test Migration (test_base, test_retrieval, storage/projection tests) — Tasks 9-11
- §8 Migration Strategy (big-bang, single PR) — Task 11 commit message
- §9 Verification Checklist — Task 13

Placeholder scan: none.

Type consistency:
- `actor_from_dict` keeps its name across base.py and projection.py — checked.
- `Actor` discriminated union typed as `HumanActor | LLMActor` consistently.
- `Event.payload: dict[str, Any]` — same in dataclass and Pydantic version.
- `RetrievalEntry.expected_chunk_ids: tuple[str, ...]` — Pydantic v2 supports tuples; serializes as JSON arrays; same as `to_dict` cast `list(...)` behaviour.

Scope check: this is one PR worth of work. Each task is bite-sized; the big-bang commit (Task 11 Step 6) is unavoidable for an atomic migration but is internally well-decomposed.
