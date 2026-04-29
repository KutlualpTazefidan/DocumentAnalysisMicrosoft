# Phase A.2 — `goldens/schemas/` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** Build `features/goldens/` with the `schemas/` subpackage —
five frozen dataclasses (`Event`, `Review`, `HumanActor`, `LLMActor`,
`RetrievalEntry`) plus `to_dict`/`from_dict` helpers and the
`Actor` union dispatcher.

**Architecture:** Pure stdlib `dataclasses`. Two source files
(`schemas/base.py`, `schemas/retrieval.py`) plus a thin
`schemas/__init__.py` re-export. Test files mirror them. 100 %
coverage target.

**Tech Stack:** Python 3.11+, stdlib only for runtime, pytest +
pytest-cov for tests.

**Spec:** `docs/superpowers/specs/2026-04-28-a2-goldens-schemas-design.md`

---

## File Structure

```
features/goldens/
├── pyproject.toml
├── README.md
├── src/
│   └── goldens/
│       ├── __init__.py
│       └── schemas/
│           ├── __init__.py
│           ├── base.py
│           └── retrieval.py
└── tests/
    ├── conftest.py
    ├── test_base.py
    └── test_retrieval.py
```

Repo-level changes:

- `bootstrap.sh` — add `pip install -e features/goldens`

---

## Task 0: Pre-flight

- [ ] **Step 1: Confirm clean tree on main**

```bash
git status
git rev-parse --abbrev-ref HEAD
```

Expected: `On branch main`, only `test.ipynb` untracked.

- [ ] **Step 2: Create work branch**

```bash
git checkout -b feat/a2-goldens-schemas
```

- [ ] **Step 3: Capture baseline**

```bash
.venv/bin/pytest features/ -q 2>&1 | tail -3
```

Expected: 233 tests pass (baseline carried over from A.1 merge).

---

## Task 1: Package skeleton + `schemas/base.py`

**Files:**
- Create: `features/goldens/pyproject.toml`
- Create: `features/goldens/README.md`
- Create: `features/goldens/src/goldens/__init__.py` (placeholder)
- Create: `features/goldens/src/goldens/schemas/__init__.py`
- Create: `features/goldens/src/goldens/schemas/base.py`
- Create: `features/goldens/tests/conftest.py`
- Create: `features/goldens/tests/test_base.py`

### Step 1: Create directory skeleton

```bash
mkdir -p features/goldens/src/goldens/schemas
mkdir -p features/goldens/tests
```

### Step 2: Write `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "goldens"
version = "0.1.0"
description = "Event-sourced golden-set storage for evaluation."
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
test = ["pytest", "pytest-cov"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=goldens --cov-fail-under=100 --cov-branch --cov-report=term-missing"

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "class .*\\(Protocol\\):",
    "if TYPE_CHECKING:",
]
```

`--cov-fail-under=100` enforces the 100 % threshold from the spec.

### Step 3: Write `README.md`

```markdown
# goldens

Event-sourced golden-set storage for retrieval-quality evaluation.

Phase A.2 ships only the schema types (`schemas/base.py`,
`schemas/retrieval.py`). Storage and projection layers come in
Phase A.3; creation/operations in A.4-A.6.

See spec:
`../../docs/superpowers/specs/2026-04-28-goldens-restructure-design.md`
and
`../../docs/superpowers/specs/2026-04-28-a2-goldens-schemas-design.md`.
```

### Step 4: Write `src/goldens/__init__.py` placeholder

```python
"""Event-sourced golden-set storage. Public re-exports added as
sub-packages land."""
```

### Step 5: Write `src/goldens/schemas/__init__.py`

```python
from goldens.schemas.base import (
    Actor,
    Event,
    HumanActor,
    LLMActor,
    Review,
    actor_from_dict,
)

__all__ = [
    "Actor",
    "Event",
    "HumanActor",
    "LLMActor",
    "Review",
    "actor_from_dict",
]
```

### Step 6: Write `src/goldens/schemas/base.py`

```python
"""Core schema dataclasses: Event, Review, HumanActor, LLMActor.

All dataclasses are `frozen=True`. `__post_init__` does light
sanity-check validation only — no external resource access. The
`Actor` union (HumanActor | LLMActor) is dispatched via the `kind`
discriminator field at deserialization time.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal


def _validate_iso_utc(value: str) -> None:
    """Raise ValueError if value is not a parseable ISO-8601 UTC timestamp."""
    if not value:
        raise ValueError("timestamp_utc must be non-empty")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"timestamp_utc not ISO-8601: {value!r}") from e


@dataclass(frozen=True)
class HumanActor:
    pseudonym: str
    level: Literal["expert", "phd", "masters", "bachelors", "other"]
    kind: Literal["human"] = "human"

    def __post_init__(self) -> None:
        if not self.pseudonym:
            raise ValueError("pseudonym must be non-empty")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> HumanActor:
        return cls(
            pseudonym=d["pseudonym"],
            level=d["level"],
            kind=d.get("kind", "human"),
        )


@dataclass(frozen=True)
class LLMActor:
    model: str
    model_version: str
    prompt_template_version: str
    temperature: float
    kind: Literal["llm"] = "llm"

    def __post_init__(self) -> None:
        for f_name in ("model", "model_version", "prompt_template_version"):
            if not getattr(self, f_name):
                raise ValueError(f"{f_name} must be non-empty")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> LLMActor:
        return cls(
            model=d["model"],
            model_version=d["model_version"],
            prompt_template_version=d["prompt_template_version"],
            temperature=d["temperature"],
            kind=d.get("kind", "llm"),
        )


Actor = HumanActor | LLMActor


def actor_from_dict(d: dict) -> Actor:
    """Dispatch on the 'kind' discriminator."""
    kind = d.get("kind")
    if kind == "human":
        return HumanActor.from_dict(d)
    if kind == "llm":
        return LLMActor.from_dict(d)
    raise ValueError(f"unknown actor kind: {kind!r}")


_REVIEW_ACTIONS = (
    "created_from_scratch",
    "synthesised",
    "imported_from_faq",
    "accepted_unchanged",
    "approved",
    "rejected",
    "deprecated",
)


@dataclass(frozen=True)
class Review:
    timestamp_utc: str
    action: Literal[
        "created_from_scratch", "synthesised", "imported_from_faq",
        "accepted_unchanged", "approved", "rejected", "deprecated",
    ]
    actor: Actor
    notes: str | None = None

    def __post_init__(self) -> None:
        _validate_iso_utc(self.timestamp_utc)
        if self.action not in _REVIEW_ACTIONS:
            raise ValueError(f"unknown review action: {self.action!r}")

    def to_dict(self) -> dict:
        # asdict() recurses into the actor dataclass, but we want the
        # discriminated form preserved exactly as the union helper expects.
        return {
            "timestamp_utc": self.timestamp_utc,
            "action": self.action,
            "actor": self.actor.to_dict(),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Review:
        return cls(
            timestamp_utc=d["timestamp_utc"],
            action=d["action"],
            actor=actor_from_dict(d["actor"]),
            notes=d.get("notes"),
        )


_EVENT_TYPES = ("created", "reviewed", "deprecated")


@dataclass(frozen=True)
class Event:
    event_id: str
    timestamp_utc: str
    event_type: Literal["created", "reviewed", "deprecated"]
    entry_id: str
    schema_version: int
    payload: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id must be non-empty")
        if not self.entry_id:
            raise ValueError("entry_id must be non-empty")
        if self.schema_version < 1:
            raise ValueError("schema_version must be >= 1")
        if self.event_type not in _EVENT_TYPES:
            raise ValueError(f"unknown event_type: {self.event_type!r}")
        _validate_iso_utc(self.timestamp_utc)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "timestamp_utc": self.timestamp_utc,
            "event_type": self.event_type,
            "entry_id": self.entry_id,
            "schema_version": self.schema_version,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Event:
        return cls(
            event_id=d["event_id"],
            timestamp_utc=d["timestamp_utc"],
            event_type=d["event_type"],
            entry_id=d["entry_id"],
            schema_version=d["schema_version"],
            payload=d.get("payload", {}),
        )
```

### Step 7: Write `tests/conftest.py`

```python
"""Shared fixtures for goldens schema tests."""
```

### Step 8: Write `tests/test_base.py`

```python
"""Tests for goldens.schemas.base — full coverage of dataclasses,
validators, and serialization round-trips."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from goldens.schemas.base import (
    Event,
    HumanActor,
    LLMActor,
    Review,
    actor_from_dict,
)


# --- HumanActor ---------------------------------------------------


def test_human_actor_defaults_kind():
    a = HumanActor(pseudonym="alice", level="phd")
    assert a.kind == "human"


def test_human_actor_is_frozen():
    a = HumanActor(pseudonym="alice", level="phd")
    with pytest.raises(FrozenInstanceError):
        a.pseudonym = "bob"  # type: ignore[misc]


def test_human_actor_rejects_empty_pseudonym():
    with pytest.raises(ValueError, match="pseudonym"):
        HumanActor(pseudonym="", level="phd")


def test_human_actor_round_trip():
    a = HumanActor(pseudonym="alice", level="expert")
    assert HumanActor.from_dict(a.to_dict()) == a


def test_human_actor_from_dict_defaults_kind():
    a = HumanActor.from_dict({"pseudonym": "alice", "level": "phd"})
    assert a.kind == "human"


# --- LLMActor -----------------------------------------------------


def test_llm_actor_defaults_kind():
    a = LLMActor(
        model="gpt-4o",
        model_version="2024-08-06",
        prompt_template_version="v1",
        temperature=0.0,
    )
    assert a.kind == "llm"


def test_llm_actor_rejects_empty_model():
    with pytest.raises(ValueError, match="model must be"):
        LLMActor(
            model="",
            model_version="v1",
            prompt_template_version="v1",
            temperature=0.0,
        )


def test_llm_actor_rejects_empty_model_version():
    with pytest.raises(ValueError, match="model_version"):
        LLMActor(
            model="gpt-4o",
            model_version="",
            prompt_template_version="v1",
            temperature=0.0,
        )


def test_llm_actor_rejects_empty_prompt_template_version():
    with pytest.raises(ValueError, match="prompt_template_version"):
        LLMActor(
            model="gpt-4o",
            model_version="v1",
            prompt_template_version="",
            temperature=0.0,
        )


def test_llm_actor_round_trip():
    a = LLMActor(
        model="gpt-4o",
        model_version="2024-08-06",
        prompt_template_version="synth-v1",
        temperature=0.3,
    )
    assert LLMActor.from_dict(a.to_dict()) == a


# --- actor_from_dict ---------------------------------------------


def test_actor_from_dict_dispatches_human():
    d = {"kind": "human", "pseudonym": "alice", "level": "phd"}
    a = actor_from_dict(d)
    assert isinstance(a, HumanActor)


def test_actor_from_dict_dispatches_llm():
    d = {
        "kind": "llm",
        "model": "gpt-4o",
        "model_version": "2024-08-06",
        "prompt_template_version": "v1",
        "temperature": 0.0,
    }
    a = actor_from_dict(d)
    assert isinstance(a, LLMActor)


def test_actor_from_dict_rejects_unknown_kind():
    with pytest.raises(ValueError, match="unknown actor kind"):
        actor_from_dict({"kind": "alien"})


# --- Review -------------------------------------------------------


def test_review_round_trip_with_human_actor():
    r = Review(
        timestamp_utc="2026-04-28T10:00:00Z",
        action="approved",
        actor=HumanActor(pseudonym="alice", level="expert"),
        notes="LGTM",
    )
    restored = Review.from_dict(r.to_dict())
    assert restored == r
    assert isinstance(restored.actor, HumanActor)


def test_review_round_trip_with_llm_actor():
    r = Review(
        timestamp_utc="2026-04-28T10:00:00Z",
        action="synthesised",
        actor=LLMActor(
            model="gpt-4o",
            model_version="2024-08-06",
            prompt_template_version="synth-v1",
            temperature=0.0,
        ),
        notes=None,
    )
    restored = Review.from_dict(r.to_dict())
    assert restored == r
    assert isinstance(restored.actor, LLMActor)


def test_review_rejects_unknown_action():
    with pytest.raises(ValueError, match="unknown review action"):
        Review(
            timestamp_utc="2026-04-28T10:00:00Z",
            action="weird",  # type: ignore[arg-type]
            actor=HumanActor(pseudonym="alice", level="phd"),
            notes=None,
        )


def test_review_rejects_bad_timestamp():
    with pytest.raises(ValueError, match="not ISO-8601"):
        Review(
            timestamp_utc="yesterday",
            action="approved",
            actor=HumanActor(pseudonym="alice", level="phd"),
            notes=None,
        )


def test_review_rejects_empty_timestamp():
    with pytest.raises(ValueError, match="timestamp_utc must be non-empty"):
        Review(
            timestamp_utc="",
            action="approved",
            actor=HumanActor(pseudonym="alice", level="phd"),
            notes=None,
        )


def test_review_notes_default_none():
    r = Review(
        timestamp_utc="2026-04-28T10:00:00Z",
        action="approved",
        actor=HumanActor(pseudonym="alice", level="phd"),
    )
    assert r.notes is None


# --- Event --------------------------------------------------------


def test_event_round_trip_minimal():
    e = Event(
        event_id="e1",
        timestamp_utc="2026-04-28T10:00:00Z",
        event_type="created",
        entry_id="r1",
        schema_version=1,
    )
    restored = Event.from_dict(e.to_dict())
    assert restored == e


def test_event_round_trip_with_payload():
    e = Event(
        event_id="e2",
        timestamp_utc="2026-04-28T10:00:00Z",
        event_type="reviewed",
        entry_id="r1",
        schema_version=1,
        payload={"action": "approved", "actor_pseudonym": "alice"},
    )
    restored = Event.from_dict(e.to_dict())
    assert restored == e
    assert restored.payload["actor_pseudonym"] == "alice"


def test_event_payload_defaults_empty():
    e = Event(
        event_id="e3",
        timestamp_utc="2026-04-28T10:00:00Z",
        event_type="deprecated",
        entry_id="r1",
        schema_version=1,
    )
    assert e.payload == {}


def test_event_rejects_empty_event_id():
    with pytest.raises(ValueError, match="event_id"):
        Event(
            event_id="",
            timestamp_utc="2026-04-28T10:00:00Z",
            event_type="created",
            entry_id="r1",
            schema_version=1,
        )


def test_event_rejects_empty_entry_id():
    with pytest.raises(ValueError, match="entry_id"):
        Event(
            event_id="e1",
            timestamp_utc="2026-04-28T10:00:00Z",
            event_type="created",
            entry_id="",
            schema_version=1,
        )


def test_event_rejects_schema_version_zero():
    with pytest.raises(ValueError, match="schema_version"):
        Event(
            event_id="e1",
            timestamp_utc="2026-04-28T10:00:00Z",
            event_type="created",
            entry_id="r1",
            schema_version=0,
        )


def test_event_rejects_unknown_event_type():
    with pytest.raises(ValueError, match="unknown event_type"):
        Event(
            event_id="e1",
            timestamp_utc="2026-04-28T10:00:00Z",
            event_type="archived",  # type: ignore[arg-type]
            entry_id="r1",
            schema_version=1,
        )


def test_event_from_dict_ignores_unknown_keys():
    d = {
        "event_id": "e1",
        "timestamp_utc": "2026-04-28T10:00:00Z",
        "event_type": "created",
        "entry_id": "r1",
        "schema_version": 1,
        "payload": {},
        "future_field": "ignored silently",
    }
    e = Event.from_dict(d)
    assert e.event_id == "e1"
```

### Step 9: Install the package and run tests

```bash
.venv/bin/pip install -e features/goldens
.venv/bin/pytest features/goldens/tests -q
```

Expected: ~25 tests pass; coverage on `base.py` = 100 %.

If `--cov-fail-under=100` trips, identify the missing branch and add
a test for it before continuing.

### Step 10: Commit

```bash
git add features/goldens
git commit -m "feat(goldens): add schemas/base.py with Event, Review, HumanActor, LLMActor"
```

---

## Task 2: `schemas/retrieval.py`

**Files:**
- Create: `features/goldens/src/goldens/schemas/retrieval.py`
- Modify: `features/goldens/src/goldens/schemas/__init__.py` (add re-exports)
- Create: `features/goldens/tests/test_retrieval.py`

### Step 1: Write `src/goldens/schemas/retrieval.py`

```python
"""RetrievalEntry — the first concrete entry type in the goldens
event-sourced model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from goldens.schemas.base import HumanActor, Review

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
    human_levels = {
        r.actor.level for r in review_chain if isinstance(r.actor, HumanActor)
    }
    if not human_levels:
        return "synthetic"
    for tier in _HUMAN_LEVEL_ORDER:
        if tier in human_levels:
            return tier  # type: ignore[return-value]
    # Unreachable: HumanActor.level is constrained to the same Literal.
    raise ValueError(f"no recognised level in {human_levels}")  # pragma: no cover


@dataclass(frozen=True)
class RetrievalEntry:
    entry_id: str
    query: str
    expected_chunk_ids: tuple[str, ...]
    chunk_hashes: dict[str, str]
    review_chain: tuple[Review, ...]
    deprecated: bool
    refines: str | None = None
    task_type: Literal["retrieval"] = "retrieval"

    def __post_init__(self) -> None:
        if not self.entry_id:
            raise ValueError("entry_id must be non-empty")
        if not self.query:
            raise ValueError("query must be non-empty")

    @property
    def level(
        self,
    ) -> Literal["expert", "phd", "masters", "bachelors", "other", "synthetic"]:
        return _highest_level(self.review_chain)

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "query": self.query,
            "expected_chunk_ids": list(self.expected_chunk_ids),
            "chunk_hashes": dict(self.chunk_hashes),
            "review_chain": [r.to_dict() for r in self.review_chain],
            "deprecated": self.deprecated,
            "refines": self.refines,
            "task_type": self.task_type,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RetrievalEntry:
        return cls(
            entry_id=d["entry_id"],
            query=d["query"],
            expected_chunk_ids=tuple(d["expected_chunk_ids"]),
            chunk_hashes=dict(d["chunk_hashes"]),
            review_chain=tuple(Review.from_dict(r) for r in d["review_chain"]),
            deprecated=d["deprecated"],
            refines=d.get("refines"),
            task_type=d.get("task_type", "retrieval"),
        )
```

### Step 2: Update `src/goldens/schemas/__init__.py`

```python
from goldens.schemas.base import (
    Actor,
    Event,
    HumanActor,
    LLMActor,
    Review,
    actor_from_dict,
)
from goldens.schemas.retrieval import RetrievalEntry

__all__ = [
    "Actor",
    "Event",
    "HumanActor",
    "LLMActor",
    "RetrievalEntry",
    "Review",
    "actor_from_dict",
]
```

### Step 3: Write `tests/test_retrieval.py`

```python
"""Tests for goldens.schemas.retrieval — RetrievalEntry,
serialization, and the level derivation."""

from __future__ import annotations

import pytest

from goldens.schemas.base import HumanActor, LLMActor, Review
from goldens.schemas.retrieval import RetrievalEntry


def _human_review(level: str, ts: str = "2026-04-28T10:00:00Z") -> Review:
    return Review(
        timestamp_utc=ts,
        action="approved",
        actor=HumanActor(pseudonym=f"alice-{level}", level=level),  # type: ignore[arg-type]
        notes=None,
    )


def _llm_review(ts: str = "2026-04-28T10:00:00Z") -> Review:
    return Review(
        timestamp_utc=ts,
        action="synthesised",
        actor=LLMActor(
            model="gpt-4o",
            model_version="2024-08-06",
            prompt_template_version="v1",
            temperature=0.0,
        ),
        notes=None,
    )


def _entry(
    *,
    entry_id: str = "r1",
    review_chain: tuple[Review, ...] = (),
    deprecated: bool = False,
    refines: str | None = None,
) -> RetrievalEntry:
    return RetrievalEntry(
        entry_id=entry_id,
        query="What is X?",
        expected_chunk_ids=("c1", "c2"),
        chunk_hashes={"c1": "sha256:aaa", "c2": "sha256:bbb"},
        review_chain=review_chain,
        deprecated=deprecated,
        refines=refines,
    )


# --- Construction & validation -----------------------------------


def test_default_task_type_is_retrieval():
    e = _entry()
    assert e.task_type == "retrieval"


def test_default_refines_is_none():
    e = _entry()
    assert e.refines is None


def test_rejects_empty_entry_id():
    with pytest.raises(ValueError, match="entry_id"):
        RetrievalEntry(
            entry_id="",
            query="q",
            expected_chunk_ids=("c1",),
            chunk_hashes={"c1": "sha256:aaa"},
            review_chain=(),
            deprecated=False,
        )


def test_rejects_empty_query():
    with pytest.raises(ValueError, match="query"):
        RetrievalEntry(
            entry_id="r1",
            query="",
            expected_chunk_ids=("c1",),
            chunk_hashes={"c1": "sha256:aaa"},
            review_chain=(),
            deprecated=False,
        )


# --- level property ----------------------------------------------


def test_level_synthetic_when_no_human():
    e = _entry(review_chain=(_llm_review(),))
    assert e.level == "synthetic"


def test_level_synthetic_when_review_chain_empty():
    e = _entry(review_chain=())
    assert e.level == "synthetic"


def test_level_expert_wins_over_lower():
    e = _entry(
        review_chain=(
            _human_review("bachelors"),
            _human_review("expert"),
            _human_review("phd"),
        )
    )
    assert e.level == "expert"


def test_level_phd_when_only_phd_and_below():
    e = _entry(
        review_chain=(
            _human_review("masters"),
            _human_review("phd"),
            _human_review("other"),
        )
    )
    assert e.level == "phd"


def test_level_masters_when_only_masters_and_below():
    e = _entry(review_chain=(_human_review("masters"), _human_review("other")))
    assert e.level == "masters"


def test_level_bachelors_when_only_bachelors_and_other():
    e = _entry(review_chain=(_human_review("bachelors"), _human_review("other")))
    assert e.level == "bachelors"


def test_level_other_when_only_other():
    e = _entry(review_chain=(_human_review("other"),))
    assert e.level == "other"


def test_level_humans_outrank_llm_in_chain():
    e = _entry(review_chain=(_llm_review(), _human_review("phd")))
    assert e.level == "phd"


# --- Serialization round-trips -----------------------------------


def test_round_trip_minimal():
    e = _entry()
    assert RetrievalEntry.from_dict(e.to_dict()) == e


def test_round_trip_with_review_chain():
    e = _entry(
        review_chain=(_human_review("expert"), _llm_review()),
        deprecated=True,
        refines="r0",
    )
    restored = RetrievalEntry.from_dict(e.to_dict())
    assert restored == e
    assert restored.review_chain[0].actor.level == "expert"


def test_from_dict_ignores_unknown_keys():
    e = _entry()
    d = e.to_dict()
    d["future_field"] = "ignored"
    restored = RetrievalEntry.from_dict(d)
    assert restored == e


def test_to_dict_returns_lists_for_tuples():
    """Serialised form must use plain JSON types — tuples become lists."""
    e = _entry()
    d = e.to_dict()
    assert isinstance(d["expected_chunk_ids"], list)
    assert isinstance(d["review_chain"], list)
```

### Step 4: Run tests

```bash
.venv/bin/pytest features/goldens/tests -q
```

Expected: 25+ (base) + 16 (retrieval) = 41+ tests pass; coverage 100 %.

### Step 5: Commit

```bash
git add features/goldens/src/goldens/schemas/retrieval.py \
        features/goldens/src/goldens/schemas/__init__.py \
        features/goldens/tests/test_retrieval.py
git commit -m "feat(goldens): add RetrievalEntry schema with level derivation and round-trip"
```

---

## Task 3: Wiring (bootstrap, top-level re-exports)

**Files:**
- Modify: `bootstrap.sh`
- Modify: `features/goldens/src/goldens/__init__.py`

### Step 1: Update `src/goldens/__init__.py`

```python
"""Event-sourced golden-set storage."""

from goldens.schemas import (
    Actor,
    Event,
    HumanActor,
    LLMActor,
    RetrievalEntry,
    Review,
    actor_from_dict,
)

__all__ = [
    "Actor",
    "Event",
    "HumanActor",
    "LLMActor",
    "RetrievalEntry",
    "Review",
    "actor_from_dict",
]
```

### Step 2: Update `bootstrap.sh` — add a `goldens` install block

Insert this after the `core` install block, before the
`pipelines/microsoft/retrieval` block:

```bash
if [ -f features/goldens/pyproject.toml ]; then
    pip install -e features/goldens
fi
```

### Step 3: Reinstall and verify

```bash
.venv/bin/pip uninstall -y goldens || true
bash bootstrap.sh
.venv/bin/python -c "from goldens import RetrievalEntry, HumanActor, LLMActor, Event, Review; print('ok')"
```

Expected: `ok` printed. Bootstrap installs all five packages.

### Step 4: Run full suite

```bash
.venv/bin/pytest features/ -q 2>&1 | tail -3
```

Expected: 233 (Phase 0 + A.1) + 41+ (A.2) = 274+ tests pass.

### Step 5: Lint and pre-commit

```bash
.venv/bin/ruff check features/ scripts/
.venv/bin/mypy features/
.venv/bin/pre-commit run --all-files
```

Expected: all clean.

### Step 6: Commit

```bash
git add features/goldens/src/goldens/__init__.py bootstrap.sh
git commit -m "feat(goldens): expose schema public API; add to bootstrap"
```

---

## Task 4: Final Verification

- [ ] **Step 1: Full suite green**

```bash
.venv/bin/pytest features/ -q 2>&1 | tail -3
```

- [ ] **Step 2: Coverage on goldens**

```bash
.venv/bin/pytest features/goldens/tests --cov=goldens --cov-report=term 2>&1 | tail -15
```

Expected: 100 % coverage on `goldens.schemas.base` and
`goldens.schemas.retrieval`.

- [ ] **Step 3: Lint + pre-commit**

```bash
.venv/bin/ruff check features/ scripts/
.venv/bin/mypy features/
.venv/bin/pre-commit run --all-files
```

- [ ] **Step 4: Inspect commit history**

```bash
git log --oneline main..HEAD
```

Expected: 4 commits (3 feat + 1 wiring).

- [ ] **Step 5: Push and PR (only after explicit user approval)**

```bash
git push -u origin feat/a2-goldens-schemas
gh pr create --title "Phase A.2: goldens/schemas/ — Event, Review, Actors, RetrievalEntry" \
  --body "$(cat <<'EOF'
## Summary

Phase A.2 of the goldens restructure: the `goldens/schemas/` package
per `docs/superpowers/specs/2026-04-28-a2-goldens-schemas-design.md`.

- `HumanActor` / `LLMActor` — discriminated union via `kind` field
- `Review` — projection-time view of an event
- `Event` — the append-only log entry shape
- `RetrievalEntry` — first concrete entry type with derived `level`
  property from `review_chain`
- `to_dict` / `from_dict` round-trip helpers per type
- `actor_from_dict` discriminator dispatcher
- Frozen dataclasses; tuples for hashable container fields
- Light `__post_init__` validation only — no external resource access

## Test plan

- [x] `pytest features/goldens/tests` — coverage 100 %
- [x] `pytest features/` — full suite green (~274 tests)
- [x] `ruff`, `mypy`, `pre-commit` — clean

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Pause here for user instruction before pushing or creating the PR.**

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §3 Package layout | Task 1 (Steps 1-2) |
| §4 Types | Tasks 1, 2 |
| §5 level ordering | Task 2 (`_highest_level`) |
| §6 Serialization contract | Tasks 1, 2 (`to_dict`/`from_dict` + `actor_from_dict`) |
| §7 Schema versioning v1 behaviour | Task 1 (Event from_dict ignores unknown keys; default schema_version usage in tests) |
| §8 Coverage strategy | `--cov-fail-under=100` in pyproject + targeted tests |

**Placeholder scan:** Clean.

**Type-consistency:** `Actor` is `HumanActor | LLMActor` defined in
`base.py` and re-exported from `schemas/__init__.py` and the
top-level `goldens/__init__.py`. Tasks 1-3 use the same name
consistently.

**Scope:** Self-contained — produces installable package with full
public API. Phase A.3 (`goldens/storage/`) is the next plan.
