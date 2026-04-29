# A.5 — `goldens/creation/synthetic.py` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the LLM-driven synthetic goldset generator (`goldens/creation/synthetic.py`) plus its prompt-template store, sub-unit decomposition helper, embedding-based dedup, and a `query-eval synthesise` CLI subparser, exactly as specified in `docs/superpowers/specs/2026-04-29-a5-synthetic-design.md`.

**Architecture:** Four atomic commits (one per Task) under `features/goldens/src/goldens/creation/`. Each commit lands a self-contained slice of `synthetic.py`'s dependencies first, then the driver that wires them. Tests use `pytest` everywhere; LLM HTTP calls are mocked at the transport layer with `respx` (the same pattern A.1's tests use). Until A.4 merges, a local `_elements_stub.py` Protocol mirrors the locked loader contract; the swap to A.4's real loader is a one-line import edit.

**Tech Stack:** Python 3.11+, pytest, pytest-cov, respx, pysbd, tiktoken, the existing `llm_clients` package (`OpenAIDirectClient.complete()` / `.embed()`), and the existing `goldens.schemas` + `goldens.storage` packages.

**Spec reference:** `docs/superpowers/specs/2026-04-29-a5-synthetic-design.md` (commits b6f11b1, 5f4ecb3, f95035b on `feat/a5-synthetic`).

---

## Prerequisites

- Worktree: `/home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft-a5-synthetic`
- Branch: `feat/a5-synthetic`
- Activate venv before any python/pytest invocation: `source .venv/bin/activate`
- All `pytest` runs use `cd features/goldens && python -m pytest ...` (the goldens package has its own pyproject and test config).
- All commit messages stay in English and follow the repo's `<type>(scope): subject` convention. No mention of Claude / AI.
- After each Task's final `pytest` run is green and the commit lands, hand-off to the next Task is safe (each commit compiles and tests on its own — see spec §10).

---

## File Structure

Files created by this plan (all under `features/goldens/`):

```
features/goldens/
├── pyproject.toml                                ← MODIFY (Tasks 2, 3, 4)
└── src/goldens/creation/
    ├── __init__.py                               ← Task 1 (empty), Task 4 (re-exports)
    ├── _elements_stub.py                         ← Task 2 (DELETE-WHEN: A.4 merges)
    ├── synthetic_decomposition.py                ← Task 2
    ├── synthetic_dedup.py                        ← Task 3
    ├── synthetic.py                              ← Task 4
    └── prompts/
        ├── __init__.py                           ← Task 1 (load_prompt + errors)
        ├── paragraph_v1.json                     ← Task 1
        ├── table_row_v1.json                     ← Task 1
        └── list_item_v1.json                     ← Task 1
```

Test files (under `features/goldens/tests/`):

```
features/goldens/tests/
├── test_creation_prompts.py                      ← Task 1
├── test_creation_decomposition.py                ← Task 2
├── test_creation_dedup.py                        ← Task 3
├── test_creation_synthetic_respx.py              ← Task 4
└── test_creation_cli.py                          ← Task 4
```

External-package modification (Task 4 only):

```
features/evaluators/chunk_match/src/query_index_eval/cli.py   ← MODIFY: add `synthesise` subparser
```

Each Task ends with **one** commit. The commits are independent and land in order:

| Task | Commit subject |
|---|---|
| 1 | `feat(goldens/creation): add prompt-template store and loader (Phase A.5.1)` |
| 2 | `feat(goldens/creation): add sub-unit decomposition (Phase A.5.2)` |
| 3 | `feat(goldens/creation): add embedding-based question dedup (Phase A.5.3)` |
| 4 | `feat(goldens/creation): add synthesise driver + query-eval subparser (Phase A.5.4)` |

---

## Task 1: Prompt-template store and loader (Phase A.5.1)

Implements spec §4.1 — the JSON-file prompt-template store with filename-suffix versioning and a schema-validating loader. No LLM, no pysbd, no tiktoken.

**Files:**
- Create: `features/goldens/src/goldens/creation/__init__.py` (empty file — placeholder for the package)
- Create: `features/goldens/src/goldens/creation/prompts/__init__.py`
- Create: `features/goldens/src/goldens/creation/prompts/paragraph_v1.json`
- Create: `features/goldens/src/goldens/creation/prompts/table_row_v1.json`
- Create: `features/goldens/src/goldens/creation/prompts/list_item_v1.json`
- Create: `features/goldens/tests/test_creation_prompts.py`

**Spec sections covered:** §4.1 (loader API), §3 (package layout for prompts/), §9 (5 prompt-loader tests).

**Success criteria:**
- `python -m pytest tests/test_creation_prompts.py -v` reports 6 passed (5 spec'd + 1 smoke).
- `python -m pytest` (whole goldens suite) stays green at the existing `--cov-fail-under=100`. Newly added executable lines are 100 % covered.
- One atomic commit using exactly the subject above.

---

- [ ] **Step 1.1: Create the empty `creation` and `creation/prompts` package skeletons**

The `creation` package and the `prompts` subpackage need `__init__.py` files so Python and pytest can import from them. Task 1 only ships the prompts side; `creation/__init__.py` stays empty for now and gets re-exports added in Task 4.

```bash
mkdir -p features/goldens/src/goldens/creation/prompts
```

Create `features/goldens/src/goldens/creation/__init__.py` with this exact content (empty docstring is intentional — keeps the file out of coverage stats):

```python
"""Synthetic goldset generation package (A.5)."""
```

- [ ] **Step 1.2: Write `features/goldens/tests/test_creation_prompts.py` with all six tests**

Drop in the full test file before any implementation. The tests reference symbols (`load_prompt`, `PromptNotFoundError`, `PromptSchemaError`) the loader will export.

```python
"""Tests for goldens.creation.prompts — JSON-file prompt-template
store with filename-suffix versioning and schema-validating loader.

Spec: docs/superpowers/specs/2026-04-29-a5-synthetic-design.md §4.1, §9.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from goldens.creation.prompts import (
    PromptNotFoundError,
    PromptSchemaError,
    load_prompt,
)

if TYPE_CHECKING:
    pass


def test_load_prompt_returns_template():
    """Happy path: paragraph_v1 file exists, schema valid, returns the
    `template` field as a string with real newlines."""
    template = load_prompt("paragraph", "v1")
    assert isinstance(template, str)
    assert template  # non-empty
    # The on-disk JSON encodes newlines as `\n`; json.loads turns them
    # into real newlines, so the returned string contains them.
    assert "\n" in template
    # Must contain the {content} placeholder used by the renderer.
    assert "{content}" in template


def test_load_prompt_default_version_is_v1():
    """Calling load_prompt without `version` resolves to v1."""
    assert load_prompt("paragraph") == load_prompt("paragraph", "v1")


def test_load_prompt_raises_on_unknown_element_type(tmp_path: Path):
    """`element_type='figure'` has no v1 prompt by design — load must
    raise PromptNotFoundError, not fall back silently."""
    with pytest.raises(PromptNotFoundError):
        load_prompt("figure", "v1")


def test_load_prompt_raises_on_filename_field_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A tampered file (filename `paragraph_v1.json` but JSON says
    element_type='table') must raise PromptSchemaError. We test this
    by swapping the prompts dir to a tmp_path with a tampered file."""
    fake_dir = tmp_path / "prompts"
    fake_dir.mkdir()
    tampered = fake_dir / "paragraph_v1.json"
    tampered.write_text(
        json.dumps(
            {
                "version": "v1",
                "element_type": "table",  # wrong! filename says "paragraph"
                "description": "tampered",
                "template": "x {content}",
            }
        ),
        encoding="utf-8",
    )

    import goldens.creation.prompts as mod

    monkeypatch.setattr(mod, "_PROMPTS_DIR", fake_dir)
    with pytest.raises(PromptSchemaError):
        load_prompt("paragraph", "v1")


def test_load_prompt_raises_on_missing_required_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """JSON missing `template` must raise PromptSchemaError."""
    fake_dir = tmp_path / "prompts"
    fake_dir.mkdir()
    bad = fake_dir / "paragraph_v1.json"
    bad.write_text(
        json.dumps(
            {
                "version": "v1",
                "element_type": "paragraph",
                "description": "missing template",
                # no `template` key
            }
        ),
        encoding="utf-8",
    )

    import goldens.creation.prompts as mod

    monkeypatch.setattr(mod, "_PROMPTS_DIR", fake_dir)
    with pytest.raises(PromptSchemaError):
        load_prompt("paragraph", "v1")


def test_load_prompt_raises_on_version_field_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Filename says v1 but JSON says version='v9' — PromptSchemaError."""
    fake_dir = tmp_path / "prompts"
    fake_dir.mkdir()
    p = fake_dir / "paragraph_v1.json"
    p.write_text(
        json.dumps(
            {
                "version": "v9",  # filename suffix is _v1, mismatch
                "element_type": "paragraph",
                "description": "wrong version",
                "template": "{content}",
            }
        ),
        encoding="utf-8",
    )

    import goldens.creation.prompts as mod

    monkeypatch.setattr(mod, "_PROMPTS_DIR", fake_dir)
    with pytest.raises(PromptSchemaError):
        load_prompt("paragraph", "v1")


def test_all_v1_files_load_without_error():
    """Smoke: every shipped *_v1.json file in the real prompts dir
    loads without raising. Catches typos in shipped templates early."""
    for et in ("paragraph", "table_row", "list_item"):
        s = load_prompt(et, "v1")
        assert isinstance(s, str)
        assert s
```

Notes for the engineer:
- `test_load_prompt_default_version_is_v1` is a 6th test (the spec table calls out 5; this one closes the gap that the API definition has a default but no test of the default).
- The tampered-file tests use `monkeypatch.setattr` to redirect the loader's resolve-base-dir constant `_PROMPTS_DIR`. The implementation must therefore expose `_PROMPTS_DIR` as a module-level attribute (a `pathlib.Path`) rather than computing it inline inside `load_prompt`.

- [ ] **Step 1.3: Run the new tests; confirm they fail with import errors**

```bash
source .venv/bin/activate
cd features/goldens && python -m pytest tests/test_creation_prompts.py -v
```

Expected:
```
ImportError while importing test module ... test_creation_prompts.py
... ModuleNotFoundError: No module named 'goldens.creation.prompts'
```

- [ ] **Step 1.4: Create the three v1 JSON files**

The on-disk prompt content is the actual prompt the LLM will see. The `\n` escapes become real newlines after `json.loads`.

`features/goldens/src/goldens/creation/prompts/paragraph_v1.json`:

```json
{
  "version": "v1",
  "element_type": "paragraph",
  "description": "Generate one factual question per sentence in a paragraph. Output JSON: a list of {sub_unit, question} objects, where sub_unit is the source sentence and question is the generated question.",
  "template": "You are a domain expert generating evaluation questions for a retrieval system.\n\nElement type: paragraph\n\nText:\n{content}\n\nFor each sentence in the text above, generate exactly one factual question whose answer is contained in that sentence. Return a JSON object with a top-level key `questions` whose value is a list. Each list element must be an object with exactly two string fields: `sub_unit` (the source sentence, verbatim) and `question` (the generated question).\n\nBe concise. Use the language of the input text. Do not invent facts not present in the source."
}
```

`features/goldens/src/goldens/creation/prompts/table_row_v1.json`:

```json
{
  "version": "v1",
  "element_type": "table_row",
  "description": "Generate one factual question per table row, given the header and the focus row.",
  "template": "You are a domain expert generating evaluation questions for a retrieval system.\n\nElement type: table row (header + one focus row)\n\nTable excerpt:\n{content}\n\nGenerate exactly one factual question whose answer is contained in the focus row. Return a JSON object with a top-level key `questions` whose value is a list with exactly one element: an object with two string fields, `sub_unit` (the focus row, verbatim) and `question` (the generated question).\n\nBe concise. Use the language of the input."
}
```

`features/goldens/src/goldens/creation/prompts/list_item_v1.json`:

```json
{
  "version": "v1",
  "element_type": "list_item",
  "description": "Generate one factual question per list item, given the full list.",
  "template": "You are a domain expert generating evaluation questions for a retrieval system.\n\nElement type: list (full list)\n\nList:\n{content}\n\nFor each list item, generate exactly one factual question whose answer is contained in that item. Return a JSON object with a top-level key `questions` whose value is a list. Each list element must be an object with exactly two string fields: `sub_unit` (the source list item, verbatim) and `question` (the generated question).\n\nBe concise. Use the language of the input."
}
```

Note: the `paragraph` prompts use the `{content}` placeholder; `table_row` uses `{content}` for the rendered "header + focus row" string (the renderer is responsible for assembly — it stays a single placeholder so all three templates render through the same code path).

- [ ] **Step 1.5: Implement `prompts/__init__.py`**

Full content for `features/goldens/src/goldens/creation/prompts/__init__.py`:

```python
"""Prompt-template store + schema-validating loader.

JSON files under this package hold the templates that drive the
synthetic generator (A.5). Filenames carry both the element type and
the version: `<element_type>_<version>.json`. The loader validates the
filename against the in-file `element_type` / `version` fields so a
rename or content edit can never silently desync.

Schema:
    {
        "version": "v1",
        "element_type": "paragraph" | "table_row" | "list_item",
        "description": "<one-line human description>",
        "template": "<prompt body, with `\\n` for newlines>"
    }

Public API:
    - load_prompt(element_type, version="v1") -> str
    - PromptNotFoundError
    - PromptSchemaError
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = [
    "PromptNotFoundError",
    "PromptSchemaError",
    "load_prompt",
]

_PROMPTS_DIR: Path = Path(__file__).parent
_REQUIRED_KEYS: tuple[str, ...] = ("version", "element_type", "description", "template")


class PromptNotFoundError(FileNotFoundError):
    """Raised when no prompt file matches the requested
    `<element_type>_<version>.json`."""


class PromptSchemaError(ValueError):
    """Raised when a prompt file is structurally invalid: missing
    keys, mismatched filename↔fields, or non-string values."""


def load_prompt(element_type: str, version: str = "v1") -> str:
    """Return the prompt template string for `element_type` at `version`.

    Resolves `<element_type>_<version>.json` under this package's
    directory, validates the JSON against the schema, asserts that the
    file's `element_type` and `version` fields match the filename, and
    returns the `template` field verbatim.

    Raises:
        PromptNotFoundError: file does not exist.
        PromptSchemaError: file exists but its content is invalid.
    """
    path = _PROMPTS_DIR / f"{element_type}_{version}.json"
    if not path.is_file():
        raise PromptNotFoundError(
            f"No prompt template at {path} (element_type={element_type!r}, version={version!r})"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PromptSchemaError(f"{path.name}: invalid JSON ({e.msg})") from e

    missing = [k for k in _REQUIRED_KEYS if k not in data]
    if missing:
        raise PromptSchemaError(f"{path.name}: missing required keys: {missing!r}")

    if data["element_type"] != element_type:
        raise PromptSchemaError(
            f"{path.name}: filename element_type={element_type!r} "
            f"!= JSON element_type={data['element_type']!r}"
        )
    if data["version"] != version:
        raise PromptSchemaError(
            f"{path.name}: filename version={version!r} "
            f"!= JSON version={data['version']!r}"
        )

    template = data["template"]
    if not isinstance(template, str) or not template:
        raise PromptSchemaError(f"{path.name}: `template` must be a non-empty string")
    return template
```

- [ ] **Step 1.6: Run the new tests; confirm all pass**

```bash
cd features/goldens && python -m pytest tests/test_creation_prompts.py -v
```

Expected: `6 passed`.

- [ ] **Step 1.7: Run the full goldens suite; confirm coverage gate still holds**

```bash
cd features/goldens && python -m pytest
```

Expected: every test passes; `--cov-fail-under=100` is satisfied (the new code is fully covered, and prior modules remain at their existing coverage).

- [ ] **Step 1.8: Commit**

```bash
git add features/goldens/src/goldens/creation/__init__.py \
        features/goldens/src/goldens/creation/prompts/__init__.py \
        features/goldens/src/goldens/creation/prompts/paragraph_v1.json \
        features/goldens/src/goldens/creation/prompts/table_row_v1.json \
        features/goldens/src/goldens/creation/prompts/list_item_v1.json \
        features/goldens/tests/test_creation_prompts.py
git commit -m "feat(goldens/creation): add prompt-template store and loader (Phase A.5.1)"
```

Verify with `git log -1 --stat` that the commit lists the six files above and nothing else.

---

## Task 2: Sub-unit decomposition + loader stub (Phase A.5.2)

Implements spec §4.2 — `decompose_to_sub_units(element)` for paragraph/table/list_item/heading/figure. Adds the loader Protocol stub (`_elements_stub.py`) used until A.4 merges. Adds `pysbd` as a runtime dep on `goldens`.

**Files:**
- Create: `features/goldens/src/goldens/creation/_elements_stub.py`
- Create: `features/goldens/src/goldens/creation/synthetic_decomposition.py`
- Create: `features/goldens/tests/test_creation_decomposition.py`
- Modify: `features/goldens/pyproject.toml` (add `pysbd>=0.3,<0.4` to `dependencies`)

**Spec sections covered:** §4.2 (decomposition API), §6 (loader stub contract), §9 (4 decomposition tests).

**Success criteria:**
- `python -m pytest tests/test_creation_decomposition.py -v` → 7 passed (4 spec'd cases + 1 paragraph empty-content edge + 1 header-only-table edge + figure split out from heading).
- `python -m pytest` (whole goldens suite) green at `--cov-fail-under=100`.
- `pysbd` import succeeds in the venv after `pip install -e features/goldens[test]` rerun.
- One atomic commit using the Phase A.5.2 subject.

---

- [ ] **Step 2.1: Add `pysbd` to `features/goldens/pyproject.toml`**

Edit the `dependencies` list. Before:

```toml
[project]
name = "goldens"
version = "0.1.0"
description = "Event-sourced golden-set storage for evaluation."
requires-python = ">=3.11"
dependencies = []
```

After:

```toml
[project]
name = "goldens"
version = "0.1.0"
description = "Event-sourced golden-set storage for evaluation."
requires-python = ">=3.11"
dependencies = [
    "pysbd>=0.3,<0.4",
]
```

- [ ] **Step 2.2: Reinstall the editable goldens package so `pysbd` is available in the venv**

```bash
source .venv/bin/activate
pip install -e features/goldens[test]
```

Expected: pip resolves and installs `pysbd-0.3.x`. If pip is sandboxed-locked, ask the user to run this in `!` mode.

Verify:

```bash
python -c "import pysbd; print(pysbd.__version__)"
```

Expected: a version starting with `0.3`.

- [ ] **Step 2.3: Create the loader Protocol stub `_elements_stub.py`**

Full content for `features/goldens/src/goldens/creation/_elements_stub.py`:

```python
"""DELETE-WHEN: a4-curate merges and ships
`goldens.creation.elements`.

Until then, this module mirrors the locked loader contract from the
A.5 brief and lets `synthetic.py` and `synthetic_decomposition.py`
import `DocumentElement` / `ElementsLoader` / `ElementType` without
depending on A.4's in-flight implementation.

Hand-off (one PR):
    1. Delete this file.
    2. In every importer, replace
           from goldens.creation._elements_stub import ...
       with
           from goldens.creation.elements import ...
    3. `python -m pytest` must stay green unchanged.
"""

from __future__ import annotations

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

Note: the `class ...(Protocol):` line is excluded from coverage by the existing `[tool.coverage.report]` block in `features/goldens/pyproject.toml`, so the Protocol body's `...` does not need a covering test.

- [ ] **Step 2.4: Write `tests/test_creation_decomposition.py`**

Full content for `features/goldens/tests/test_creation_decomposition.py`:

```python
"""Tests for goldens.creation.synthetic_decomposition.

Spec: docs/superpowers/specs/2026-04-29-a5-synthetic-design.md §4.2, §9.
"""

from __future__ import annotations

from goldens.creation._elements_stub import DocumentElement
from goldens.creation.synthetic_decomposition import decompose_to_sub_units


def _para(content: str) -> DocumentElement:
    return DocumentElement(
        element_id="p1-aaaaaaaa",
        page_number=1,
        element_type="paragraph",
        content=content,
    )


def _table(content: str) -> DocumentElement:
    # `content` carries the rendered header + body rows separated by
    # newlines, columns by ` | `. Single-row tables → exactly one
    # sub-unit. The loader is expected to format tables this way.
    return DocumentElement(
        element_id="p1-bbbbbbbb",
        page_number=1,
        element_type="table",
        content=content,
        table_dims=(content.count("\n") + 1, content.split("\n")[0].count(" | ") + 1),
    )


def _list(content: str) -> DocumentElement:
    return DocumentElement(
        element_id="p1-cccccccc",
        page_number=1,
        element_type="list_item",
        content=content,
    )


# --- paragraph ------------------------------------------------------


def test_paragraph_splits_into_sentences_keeping_abbreviations():
    """German paragraph with `Dr.`, `M6`, `kN` must split at sentence
    ends, not at the abbreviation periods."""
    el = _para(
        "Dr. Müller hat eine Schraube M6 verbaut. "
        "Sie hält 12 kN aus. "
        "Die Prüfung erfolgte nach DIN 1234."
    )
    out = decompose_to_sub_units(el)
    assert len(out) == 3
    assert out[0].startswith("Dr. Müller")
    assert "12 kN" in out[1]
    assert "DIN 1234" in out[2]


def test_paragraph_with_empty_content_returns_empty_tuple():
    """Whitespace-only content → no sub-units, not a single empty
    string."""
    assert decompose_to_sub_units(_para("   \n  ")) == ()


# --- table ----------------------------------------------------------


def test_table_splits_into_rows_each_prefixed_with_header():
    """A table with 3 data rows → 3 sub-units, each prefixed with the
    header line (spec §4.2 + §9). The header gives the LLM column
    meaning when asking a question about a single row."""
    table = (
        "Schraube | Last (kN) | Norm\n"
        "M6       | 12        | DIN 1234\n"
        "M8       | 18        | DIN 1234\n"
        "M10      | 25        | DIN 1234"
    )
    out = decompose_to_sub_units(_table(table))
    assert len(out) == 3
    for sub in out:
        # Header + row: the column titles are present in every sub-unit.
        assert "Schraube" in sub
        assert "Last (kN)" in sub
    assert "M6" in out[0]
    assert "M8" in out[1]
    assert "M10" in out[2]


def test_table_with_only_header_returns_empty_tuple():
    """A header-only table (no data rows) → no sub-units."""
    out = decompose_to_sub_units(_table("Schraube | Last (kN) | Norm"))
    assert out == ()


# --- list_item ------------------------------------------------------


def test_list_item_splits_on_bullet_and_numbered_patterns():
    """Hyphen / bullet / numbered patterns each become their own
    sub-unit; leading whitespace is stripped."""
    el = _list("- erste\n- zweite\n3. dritte\n* vierte")
    out = decompose_to_sub_units(el)
    assert tuple(out) == ("erste", "zweite", "dritte", "vierte")


# --- heading / figure -----------------------------------------------


def test_heading_returns_empty_tuple():
    el = DocumentElement(
        element_id="p1-dddddddd",
        page_number=1,
        element_type="heading",
        content="3.2 Befestigungselemente",
    )
    assert decompose_to_sub_units(el) == ()


def test_figure_returns_empty_tuple():
    el = DocumentElement(
        element_id="p1-eeeeeeee",
        page_number=1,
        element_type="figure",
        content="<binary>",
        caption="Figure 4: Befestigung an der Stahlplatte",
    )
    assert decompose_to_sub_units(el) == ()
```

- [ ] **Step 2.5: Run the tests; confirm they fail (module not found)**

```bash
cd features/goldens && python -m pytest tests/test_creation_decomposition.py -v
```

Expected:
```
ModuleNotFoundError: No module named 'goldens.creation.synthetic_decomposition'
```

- [ ] **Step 2.6: Implement `synthetic_decomposition.py`**

Full content for `features/goldens/src/goldens/creation/synthetic_decomposition.py`:

```python
"""Sub-unit decomposition: split a `DocumentElement` into the
testable pieces that the synthetic generator turns into questions.

Per element_type:
    - "paragraph"  → pysbd-split into sentences (German segmentation)
    - "table"      → one sub-unit per data row (header line dropped here;
                     the LLM-loop renderer pairs the header back in)
    - "list_item"  → split on bullet (`-`, `*`, `•`) and numbered
                     (`\\d+\\.`) patterns; whitespace stripped
    - "heading"    → ()  (v1 skips, see spec Q6.2)
    - "figure"     → ()  (v1 skips, see spec Q6.2)

The pysbd `Segmenter` is built lazily and cached at module level — the
rule trie is non-trivial to construct.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pysbd

if TYPE_CHECKING:
    from goldens.creation._elements_stub import DocumentElement

__all__ = ["decompose_to_sub_units"]

_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+\.)\s+")
_segmenter: pysbd.Segmenter | None = None


def _get_segmenter() -> pysbd.Segmenter:
    global _segmenter
    if _segmenter is None:
        _segmenter = pysbd.Segmenter(language="de", clean=False)
    return _segmenter


def decompose_to_sub_units(element: DocumentElement) -> tuple[str, ...]:
    et = element.element_type
    content = element.content

    if et == "paragraph":
        if not content.strip():
            return ()
        seg = _get_segmenter()
        sentences = [s.strip() for s in seg.segment(content)]
        return tuple(s for s in sentences if s)

    if et == "table":
        # Pair the header (first line) with each data row so each
        # sub-unit carries column meaning. Spec §4.2 + §9: "header +
        # that row".
        lines = [ln for ln in content.split("\n") if ln.strip()]
        if len(lines) <= 1:
            # Header-only or empty → no testable rows.
            return ()
        header = lines[0]
        return tuple(f"{header}\n{row}" for row in lines[1:])

    if et == "list_item":
        out: list[str] = []
        for raw in content.split("\n"):
            stripped = _BULLET_RE.sub("", raw).strip()
            if stripped:
                out.append(stripped)
        return tuple(out)

    # heading / figure: skip in v1.
    return ()
```

- [ ] **Step 2.7: Run the tests; confirm all pass**

```bash
cd features/goldens && python -m pytest tests/test_creation_decomposition.py -v
```

Expected: `5 passed`. If the German abbreviation test fails (pysbd splitting on `Dr.`), check the pysbd version (must be `>=0.3,<0.4` — earlier versions had weaker German rules) and confirm `language="de"` is passed.

- [ ] **Step 2.8: Run the full goldens suite**

```bash
cd features/goldens && python -m pytest
```

Expected: green at `--cov-fail-under=100`.

- [ ] **Step 2.9: Commit**

```bash
git add features/goldens/pyproject.toml \
        features/goldens/src/goldens/creation/_elements_stub.py \
        features/goldens/src/goldens/creation/synthetic_decomposition.py \
        features/goldens/tests/test_creation_decomposition.py
git commit -m "feat(goldens/creation): add sub-unit decomposition (Phase A.5.2)"
```

Verify the commit lists exactly those four files plus none other.

---

## Task 3: Embedding-based question dedup (Phase A.5.3)

Implements spec §4.4 — `QuestionDedup` with same-source-element scope, threshold 0.95, in-memory session cache, disabled-mode when `client is None`. Adds `respx` as a `[test]` dep on `goldens` so tests can mock the embeddings endpoint.

**Files:**
- Create: `features/goldens/src/goldens/creation/synthetic_dedup.py`
- Create: `features/goldens/tests/test_creation_dedup.py`
- Modify: `features/goldens/pyproject.toml` (add `respx>=0.21` to `optional-dependencies.test`)

**Spec sections covered:** §4.4 (dedup API), §9 (5 dedup tests).

**Success criteria:**
- `python -m pytest tests/test_creation_dedup.py -v` → 6 passed (5 spec'd + 1 end-to-end OpenAIDirectClient smoke).
- `python -m pytest` (full suite) green at `--cov-fail-under=100`.
- One atomic commit using the Phase A.5.3 subject.

---

- [ ] **Step 3.1: Add `respx` to `features/goldens/pyproject.toml` test extras**

Before:

```toml
[project.optional-dependencies]
test = ["pytest", "pytest-cov"]
```

After:

```toml
[project.optional-dependencies]
test = ["pytest", "pytest-cov", "respx>=0.21"]
```

- [ ] **Step 3.2: Reinstall the editable goldens package's test extras**

```bash
source .venv/bin/activate
pip install -e features/goldens[test]
python -c "import respx; print(respx.__version__)"
```

Expected: a version `>=0.21`.

- [ ] **Step 3.3: Write `tests/test_creation_dedup.py`**

Full content for `features/goldens/tests/test_creation_dedup.py`. The tests use a small in-memory fake `LLMClient` so dedup logic can be exercised without real embeddings; one test doubles back through respx to prove the wiring works against `OpenAIDirectClient` end-to-end.

```python
"""Tests for goldens.creation.synthetic_dedup.QuestionDedup.

Spec: docs/superpowers/specs/2026-04-29-a5-synthetic-design.md §4.4, §9.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import pytest
import respx
from httpx import Response
from llm_clients.openai_direct import OpenAIDirectClient, OpenAIDirectConfig

from goldens.creation.synthetic_dedup import QuestionDedup


@dataclass
class FakeEmbedClient:
    """Minimal LLMClient stand-in: returns deterministic vectors and
    counts how many times `embed` was called with which texts."""

    embeddings: dict[str, list[float]] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        self.calls.append(list(texts))
        out: list[list[float]] = []
        for t in texts:
            if t not in self.embeddings:
                # Default: a unit-length vector keyed off the string
                # so different strings differ but the same string
                # round-trips identically.
                v = [float(ord(c) % 7) for c in t[:5]] or [1.0]
                # Normalise so cosine == 1.0 for identical inputs.
                norm = math.sqrt(sum(x * x for x in v)) or 1.0
                self.embeddings[t] = [x / norm for x in v]
            out.append(self.embeddings[t])
        return out


def test_filter_drops_questions_above_threshold():
    """Two near-identical questions → one kept (the second one is
    dropped because cosine to the first is >= 0.95)."""
    client = FakeEmbedClient()
    # Force identical embeddings for the two near-dups.
    same_vec = [1.0, 0.0, 0.0]
    client.embeddings["Wie groß ist die Last bei M6?"] = same_vec
    client.embeddings["Wie groß ist die Last bei M6 ?"] = same_vec  # paraphrase

    dedup = QuestionDedup(client=client, model="emb", threshold=0.95)
    kept = dedup.filter(
        ["Wie groß ist die Last bei M6?", "Wie groß ist die Last bei M6 ?"],
        against=[],
        source_key="p1-aaaaaaaa",
    )
    assert kept == ["Wie groß ist die Last bei M6?"]


def test_filter_keeps_dissimilar_questions():
    """Two unrelated questions → both kept."""
    client = FakeEmbedClient()
    client.embeddings["Was ist die Norm?"] = [1.0, 0.0, 0.0]
    client.embeddings["Wie schwer ist die Schraube?"] = [0.0, 1.0, 0.0]

    dedup = QuestionDedup(client=client, model="emb", threshold=0.95)
    kept = dedup.filter(
        ["Was ist die Norm?", "Wie schwer ist die Schraube?"],
        against=[],
        source_key="p1-aaaaaaaa",
    )
    assert kept == ["Was ist die Norm?", "Wie schwer ist die Schraube?"]


def test_filter_dedups_within_a_single_call():
    """A single filter([q1, q1_paraphrase], existing=[]) call must
    keep only one — the second is matched against the first that was
    just kept in the same call."""
    client = FakeEmbedClient()
    same_vec = [1.0, 0.0, 0.0]
    client.embeddings["X?"] = same_vec
    client.embeddings["X ?"] = same_vec

    dedup = QuestionDedup(client=client, model="emb", threshold=0.95)
    kept = dedup.filter(["X?", "X ?"], against=[], source_key="p1-aaaaaaaa")
    assert kept == ["X?"]


def test_disabled_when_client_is_none_returns_input_and_warns(caplog):
    """`client=None` → filter returns the generated list unchanged
    and logs a single WARNING for the session."""
    dedup = QuestionDedup(client=None, model="emb", threshold=0.95)
    with caplog.at_level(logging.WARNING):
        kept_a = dedup.filter(["q1", "q2"], against=[], source_key="src1")
        kept_b = dedup.filter(["q3"], against=[], source_key="src2")
    assert kept_a == ["q1", "q2"]
    assert kept_b == ["q3"]
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    # Exactly one warning per session, not one per call.
    assert len(warnings) == 1
    assert "dedup disabled" in warnings[0].getMessage().lower()


def test_caches_existing_embeddings_per_source_key():
    """Two filter calls for the same source_key with the same
    `against` list → embed_client.embed is called for `against` only
    on the first call, not the second."""
    client = FakeEmbedClient()
    dedup = QuestionDedup(client=client, model="emb", threshold=0.95)

    dedup.filter(["new1"], against=["existing1", "existing2"], source_key="src1")
    first_call_count = len(client.calls)
    dedup.filter(["new2"], against=["existing1", "existing2"], source_key="src1")
    second_call_count = len(client.calls)

    # First filter: at most 2 calls (one for `against`, one for
    # `generated`). Second filter: only `generated` is re-embedded —
    # `against` is cached. So the delta is exactly 1.
    assert second_call_count - first_call_count == 1
    # And the cached call must NOT contain "existing1"/"existing2".
    last_payload = client.calls[-1]
    assert "existing1" not in last_payload
    assert "existing2" not in last_payload


@respx.mock
def test_filter_works_end_to_end_with_openai_direct_client():
    """Smoke: QuestionDedup wired against the real OpenAIDirectClient
    + respx-mocked embeddings endpoint. Proves the dedup helper does
    not depend on FakeEmbedClient internals."""
    cfg = OpenAIDirectConfig(api_key="sk-test", base_url="https://api.openai.com/v1")
    client = OpenAIDirectClient(cfg)
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"object": "embedding", "index": 0, "embedding": [1.0, 0.0, 0.0]},
                    {"object": "embedding", "index": 1, "embedding": [1.0, 0.0, 0.0]},
                ],
                "model": "text-embedding-3-large",
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
            },
        )
    )
    dedup = QuestionDedup(client=client, model="text-embedding-3-large", threshold=0.95)
    kept = dedup.filter(["q same", "q same too"], against=[], source_key="p1-z")
    assert len(kept) == 1
```

Note for the engineer: `caplog` is a built-in pytest fixture; no new test deps needed for it.

- [ ] **Step 3.4: Run the tests; confirm they fail (module not found)**

```bash
cd features/goldens && python -m pytest tests/test_creation_dedup.py -v
```

Expected:
```
ModuleNotFoundError: No module named 'goldens.creation.synthetic_dedup'
```

- [ ] **Step 3.5: Implement `synthetic_dedup.py`**

Full content for `features/goldens/src/goldens/creation/synthetic_dedup.py`:

```python
"""Embedding-based question dedup, scoped to a single source_element.

Spec: docs/superpowers/specs/2026-04-29-a5-synthetic-design.md §4.4.

Usage:
    dedup = QuestionDedup(client=embed_client, model=embed_model)
    for element, generated in ...:
        existing = [e.query for e in active_entries_for(element)]
        kept = dedup.filter(
            generated,
            against=existing,
            source_key=element.element_id,
        )

If `client is None`, dedup is disabled — `filter` returns its
`generated` argument unchanged after logging a single per-session
warning.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm_clients.base import LLMClient

__all__ = ["QuestionDedup", "cosine"]

_log = logging.getLogger(__name__)


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two same-length vectors. Returns
    0.0 if either has zero norm."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


class QuestionDedup:
    """Bounded-scope dedup: questions are compared only against
    other questions for the same `source_key`.

    Threshold is `>= threshold`: a similarity equal to the threshold
    counts as a duplicate.
    """

    def __init__(
        self,
        client: LLMClient | None,
        model: str,
        threshold: float = 0.95,
    ) -> None:
        self._client = client
        self._model = model
        self._threshold = threshold
        # Per-source_key cache of `against` embeddings, plus a
        # rolling list of accepted generated embeddings within the
        # session so within-call dedup works.
        self._cache: dict[str, list[list[float]]] = {}
        self._disabled_warned = False

    def filter(
        self,
        generated: list[str],
        *,
        against: list[str],
        source_key: str,
    ) -> list[str]:
        if self._client is None:
            if not self._disabled_warned:
                _log.warning(
                    "dedup disabled — no embedding client configured; "
                    "generated questions will be passed through unchanged"
                )
                self._disabled_warned = True
            return list(generated)

        # Resolve the against-vector list for this source_key, using
        # the cache. If we've never seen this source_key, embed
        # `against` now and seed the cache.
        if source_key not in self._cache:
            against_vecs = self._client.embed(against, self._model) if against else []
            self._cache[source_key] = list(against_vecs)
        baseline = self._cache[source_key]

        if not generated:
            return []

        gen_vecs = self._client.embed(generated, self._model)

        kept: list[str] = []
        kept_vecs: list[list[float]] = []
        for q, v in zip(generated, gen_vecs, strict=True):
            if any(cosine(v, b) >= self._threshold for b in baseline):
                continue
            if any(cosine(v, k) >= self._threshold for k in kept_vecs):
                continue
            kept.append(q)
            kept_vecs.append(v)

        # Within-call accepted vectors are appended to the cache so
        # subsequent calls in this session also dedup against them.
        self._cache[source_key].extend(kept_vecs)
        return kept
```

- [ ] **Step 3.6: Run the tests; confirm all pass**

```bash
cd features/goldens && python -m pytest tests/test_creation_dedup.py -v
```

Expected: `6 passed` (5 spec'd + 1 end-to-end smoke).

- [ ] **Step 3.7: Run the full goldens suite**

```bash
cd features/goldens && python -m pytest
```

Expected: green at `--cov-fail-under=100`.

If the new module has uncovered lines, audit `cosine` (the `if na and nb else 0.0` branch needs a zero-vector test if it's reachable). The spec's intent is that empty `against` short-circuits before `cosine` is called with a zero vector, but the safe-guard branch can be exercised via a unit test if needed — add it before lowering the threshold, never lower the threshold to paper over a coverage gap.

- [ ] **Step 3.8: Commit**

```bash
git add features/goldens/pyproject.toml \
        features/goldens/src/goldens/creation/synthetic_dedup.py \
        features/goldens/tests/test_creation_dedup.py
git commit -m "feat(goldens/creation): add embedding-based question dedup (Phase A.5.3)"
```

---

## Task 4: Synthesise driver + query-eval subparser (Phase A.5.4)

Implements spec §4.3 (LLM call shape), §4.5 (driver), §4.6 (result type), §4.7 (CLI). Wires the `synthesise` subparser into `query_index_eval/cli.py`. Adds `tiktoken` as a runtime dep on `goldens`. Lowers the goldens `--cov-fail-under` from 100 to 70 to match `docs/evaluation/coverage-thresholds.md`'s `creation/` tier (this is the one cross-cutting `pyproject.toml` change called out in spec §11 open-questions).

**Files:**
- Create: `features/goldens/src/goldens/creation/synthetic.py`
- Modify: `features/goldens/src/goldens/creation/__init__.py` (re-export `synthesise`, `cmd_synthesise`)
- Modify: `features/goldens/pyproject.toml` (add `tiktoken>=0.7`; lower `--cov-fail-under` from 100 to 70)
- Modify: `features/evaluators/chunk_match/src/query_index_eval/cli.py` (register `synthesise` subparser)
- Create: `features/goldens/tests/test_creation_synthetic_respx.py`
- Create: `features/goldens/tests/test_creation_cli.py`

**Spec sections covered:** §4.3, §4.5, §4.6, §4.7, §9 (8 synthetic_respx tests + 1 CLI test).

**Success criteria:**
- `python -m pytest tests/test_creation_synthetic_respx.py tests/test_creation_cli.py -v` → 10 passed (8 spec'd synthetic_respx tests + 1 extra "two consecutive failures" coverage test + 1 CLI test).
- `python -m pytest` (full goldens suite) green at the new `--cov-fail-under=70`.
- `query-eval synthesise --help` (run from the chunk_match venv where `query-eval` is installed) prints the new subparser's help text.
- One atomic commit using the Phase A.5.4 subject.

---

- [ ] **Step 4.1: Add `tiktoken` and lower the coverage threshold in `features/goldens/pyproject.toml`**

Two edits in the same file. Before:

```toml
[project]
name = "goldens"
version = "0.1.0"
description = "Event-sourced golden-set storage for evaluation."
requires-python = ">=3.11"
dependencies = [
    "pysbd>=0.3,<0.4",
]
```

After:

```toml
[project]
name = "goldens"
version = "0.1.0"
description = "Event-sourced golden-set storage for evaluation."
requires-python = ">=3.11"
dependencies = [
    "pysbd>=0.3,<0.4",
    "tiktoken>=0.7",
]
```

And:

Before:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=goldens --cov-fail-under=100 --cov-branch --cov-report=term-missing"
```

After:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=goldens --cov-fail-under=70 --cov-branch --cov-report=term-missing"
```

- [ ] **Step 4.2: Reinstall the editable goldens package**

```bash
source .venv/bin/activate
pip install -e features/goldens[test]
python -c "import tiktoken; print(tiktoken.__version__)"
```

Expected: a version starting with `0.7` or higher.

- [ ] **Step 4.3: Write `tests/test_creation_synthetic_respx.py`**

This is the largest test file. Drop in the full content. The tests share helpers via local fixtures.

```python
"""Tests for goldens.creation.synthetic — happy path, retry,
oversize-prompt fallback, max-cap, dry-run, resume, source_element
shape, actor metadata.

HTTP is mocked at the transport layer with respx; the openai SDK
hits httpx underneath, so respx routes intercept actual calls — this
verifies the wire payload (model, temperature, response_format) the
way A.1's tests do.

Spec: docs/superpowers/specs/2026-04-29-a5-synthetic-design.md §4.3, §4.5, §4.6, §9.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
import respx
from httpx import Response
from llm_clients.openai_direct import OpenAIDirectClient, OpenAIDirectConfig

from goldens.creation._elements_stub import DocumentElement
from goldens.creation.synthetic import SynthesiseResult, synthesise
from goldens.storage.log import read_events
from goldens.storage.projection import build_state


# ---------- Fakes ----------------------------------------------------


@dataclass
class FakeLoader:
    slug: str
    _elements: list[DocumentElement]

    def elements(self) -> list[DocumentElement]:
        return list(self._elements)


def _para(eid: str, text: str, page: int = 1) -> DocumentElement:
    return DocumentElement(
        element_id=eid,
        page_number=page,
        element_type="paragraph",
        content=text,
    )


def _completion_response(payload: object) -> Response:
    """Build a 200 chat.completions response whose `content` is
    `json.dumps(payload)`."""
    return Response(
        200,
        json={
            "id": "abc",
            "object": "chat.completion",
            "model": "gpt-4o-2024-08-06",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": json.dumps(payload)},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
            },
        },
    )


def _embed_response(n_vectors: int, vec: list[float] | None = None) -> Response:
    v = vec or [1.0, 0.0, 0.0]
    return Response(
        200,
        json={
            "object": "list",
            "data": [
                {"object": "embedding", "index": i, "embedding": list(v)}
                for i in range(n_vectors)
            ],
            "model": "text-embedding-3-large",
            "usage": {"prompt_tokens": n_vectors, "total_tokens": n_vectors},
        },
    )


@pytest.fixture
def llm_client() -> OpenAIDirectClient:
    return OpenAIDirectClient(
        OpenAIDirectConfig(api_key="sk-test", base_url="https://api.openai.com/v1")
    )


# ---------- Tests ---------------------------------------------------


@respx.mock
def test_happy_path_writes_one_event_per_kept_question(
    tmp_path: Path, llm_client: OpenAIDirectClient
):
    """One paragraph element → one bundled JSON-mode call →
    two questions returned → two events written, both `created`
    with action='synthesised' and source_element pointing at the
    paragraph. Embedding endpoint is hit once for dedup (no
    `against`, two `generated`)."""
    events_path = tmp_path / "golden_events_v1.jsonl"
    completion_route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_completion_response(
            {
                "questions": [
                    {"sub_unit": "Erste.", "question": "Frage 1?"},
                    {"sub_unit": "Zweite.", "question": "Frage 2?"},
                ]
            }
        )
    )
    # Two distinct unit vectors so dedup keeps both.
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"object": "embedding", "index": 0, "embedding": [1.0, 0.0, 0.0]},
                    {"object": "embedding", "index": 1, "embedding": [0.0, 1.0, 0.0]},
                ],
                "model": "text-embedding-3-large",
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
            },
        )
    )

    loader = FakeLoader(
        slug="docX",
        _elements=[_para("p1-aaaaaaaa", "Erste. Zweite.", page=1)],
    )

    result = synthesise(
        slug="docX",
        loader=loader,
        client=llm_client,
        embed_client=llm_client,
        model="gpt-4o",
        embedding_model="text-embedding-3-large",
        events_path=events_path,
    )

    assert isinstance(result, SynthesiseResult)
    assert result.events_written == 2
    assert result.questions_kept == 2
    assert completion_route.call_count == 1

    state = build_state(read_events(events_path))
    assert len(state) == 2
    queries = sorted(e.query for e in state.values())
    assert queries == ["Frage 1?", "Frage 2?"]


@respx.mock
def test_json_parse_failure_retries_once_then_skips(
    tmp_path: Path, llm_client: OpenAIDirectClient
):
    """First completion returns malformed JSON, second returns valid
    JSON → element is processed (one event written)."""
    responses = iter(
        [
            Response(
                200,
                json={
                    "id": "x",
                    "object": "chat.completion",
                    "model": "gpt-4o",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "not json"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            ),
            _completion_response(
                {"questions": [{"sub_unit": "Erste.", "question": "Frage 1?"}]}
            ),
        ]
    )
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        side_effect=lambda request: next(responses)
    )
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=_embed_response(1)
    )
    loader = FakeLoader(slug="docX", _elements=[_para("p1-aaaaaaaa", "Erste.")])

    result = synthesise(
        slug="docX",
        loader=loader,
        client=llm_client,
        embed_client=llm_client,
        model="gpt-4o",
        embedding_model="text-embedding-3-large",
        events_path=tmp_path / "golden_events_v1.jsonl",
    )
    assert result.events_written == 1


@respx.mock
def test_two_consecutive_json_failures_skip_element_with_warning(
    tmp_path: Path, llm_client: OpenAIDirectClient, caplog: pytest.LogCaptureFixture
):
    """Both completion attempts return malformed JSON → element
    skipped, warning logged, no events written."""
    bad = Response(
        200,
        json={
            "id": "x",
            "object": "chat.completion",
            "model": "gpt-4o",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "still not json"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )
    respx.post("https://api.openai.com/v1/chat/completions").mock(return_value=bad)
    loader = FakeLoader(slug="docX", _elements=[_para("p1-aaaaaaaa", "Erste.")])

    import logging

    with caplog.at_level(logging.WARNING):
        result = synthesise(
            slug="docX",
            loader=loader,
            client=llm_client,
            embed_client=None,  # dedup disabled — we don't care about embeddings here
            model="gpt-4o",
            embedding_model=None,
            events_path=tmp_path / "golden_events_v1.jsonl",
        )
    assert result.events_written == 0
    assert any("skipping element" in r.getMessage().lower() for r in caplog.records)


@respx.mock
def test_oversize_prompt_falls_back_to_per_subunit_calls(
    tmp_path: Path, llm_client: OpenAIDirectClient
):
    """When the bundled prompt exceeds max_prompt_tokens, the driver
    issues N per-sub-unit calls instead of 1 bundled call."""
    completion_route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_completion_response(
            {"questions": [{"sub_unit": "S.", "question": "Q?"}]}
        )
    )
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=_embed_response(1)
    )

    # 3 sentences in one paragraph; force the bundled prompt over the cap.
    loader = FakeLoader(
        slug="docX",
        _elements=[_para("p1-aaaaaaaa", "Erste. Zweite. Dritte.")],
    )

    result = synthesise(
        slug="docX",
        loader=loader,
        client=llm_client,
        embed_client=llm_client,
        model="gpt-4o",
        embedding_model="text-embedding-3-large",
        max_prompt_tokens=1,  # forces fallback regardless of real prompt size
        events_path=tmp_path / "golden_events_v1.jsonl",
    )
    # 3 sub-units → 3 completion calls.
    assert completion_route.call_count == 3
    assert result.events_written == 3


@respx.mock
def test_respects_max_questions_cap(
    tmp_path: Path, llm_client: OpenAIDirectClient
):
    """LLM returns 8 questions, cap=3 → 3 events written, 5 reported
    as dropped_cap. Embeddings return distinct vectors so dedup keeps
    everything before the cap is applied."""
    big = {
        "questions": [{"sub_unit": f"S{i}.", "question": f"Q{i}?"} for i in range(8)]
    }
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_completion_response(big)
    )
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=Response(
            200,
            json={
                "object": "list",
                "data": [
                    {
                        "object": "embedding",
                        "index": i,
                        # Each vector is unit-length along its own axis →
                        # cosine across them is 0, no dedup collisions.
                        "embedding": [1.0 if j == i else 0.0 for j in range(8)],
                    }
                    for i in range(8)
                ],
                "model": "text-embedding-3-large",
                "usage": {"prompt_tokens": 8, "total_tokens": 8},
            },
        )
    )
    loader = FakeLoader(slug="docX", _elements=[_para("p1-a", "Erste. Zweite. Dritte.")])

    result = synthesise(
        slug="docX",
        loader=loader,
        client=llm_client,
        embed_client=llm_client,
        model="gpt-4o",
        embedding_model="text-embedding-3-large",
        max_questions_per_element=3,
        events_path=tmp_path / "golden_events_v1.jsonl",
    )
    assert result.events_written == 3
    assert result.questions_dropped_cap == 5


@respx.mock
def test_dry_run_writes_no_events_and_does_not_call_llm(
    tmp_path: Path, llm_client: OpenAIDirectClient
):
    """`dry_run=True` → 0 LLM calls (assert via respx route counts),
    0 events written, prompt_tokens_estimated populated."""
    completion_route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_completion_response({"questions": []})
    )
    embed_route = respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=_embed_response(0)
    )
    loader = FakeLoader(slug="docX", _elements=[_para("p1-a", "Erste. Zweite.")])
    events_path = tmp_path / "golden_events_v1.jsonl"

    result = synthesise(
        slug="docX",
        loader=loader,
        client=llm_client,
        embed_client=llm_client,
        model="gpt-4o",
        embedding_model="text-embedding-3-large",
        dry_run=True,
        events_path=events_path,
    )
    assert result.dry_run is True
    assert result.events_written == 0
    assert result.prompt_tokens_estimated > 0
    assert completion_route.call_count == 0
    assert embed_route.call_count == 0
    assert not events_path.exists()


@respx.mock
def test_resume_skips_already_processed_elements(
    tmp_path: Path, llm_client: OpenAIDirectClient
):
    """Pre-seed an active synthesised event for element X → second
    pass with --resume skips X, processes Y."""
    from goldens.schemas.base import Event, LLMActor
    from goldens.storage.ids import new_entry_id, new_event_id
    from goldens.storage.log import append_event

    events_path = tmp_path / "golden_events_v1.jsonl"
    seed_event = Event(
        event_id=new_event_id(),
        timestamp_utc="2026-04-29T09:00:00Z",
        event_type="created",
        entry_id=new_entry_id(),
        schema_version=1,
        payload={
            "task_type": "retrieval",
            "actor": LLMActor(
                model="gpt-4o",
                model_version="gpt-4o-2024-08-06",
                prompt_template_version="v1",
                temperature=0.0,
            ).to_dict(),
            "action": "synthesised",
            "notes": None,
            "entry_data": {
                "query": "seeded?",
                "expected_chunk_ids": [],
                "chunk_hashes": {},
                "refines": None,
                "source_element": {
                    "document_id": "docX",
                    "page_number": 1,
                    "element_id": "aaaaaaaa",  # bare hash (page prefix stripped)
                    "element_type": "paragraph",
                },
            },
        },
    )
    append_event(events_path, seed_event)

    completion_route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_completion_response(
            {"questions": [{"sub_unit": "Yo.", "question": "Y?"}]}
        )
    )
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=_embed_response(1)
    )

    loader = FakeLoader(
        slug="docX",
        _elements=[
            _para("p1-aaaaaaaa", "Erste."),  # already processed (matches seeded source_element)
            _para("p1-bbbbbbbb", "Yo."),
        ],
    )
    result = synthesise(
        slug="docX",
        loader=loader,
        client=llm_client,
        embed_client=llm_client,
        model="gpt-4o",
        embedding_model="text-embedding-3-large",
        resume=True,
        events_path=events_path,
    )
    # Only element "p1-bbbbbbbb" is processed.
    assert completion_route.call_count == 1
    assert result.events_written == 1
    assert result.elements_skipped >= 1


@respx.mock
def test_source_element_is_persisted_with_stripped_page_prefix(
    tmp_path: Path, llm_client: OpenAIDirectClient
):
    """Event payload must have entry_data.source_element with
    document_id=loader.slug, page_number/element_type from the loader
    element, AND element_id equal to the BARE hash (page prefix
    stripped — matches A.4's build_event_source_element_id_strips_page_prefix)."""
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_completion_response(
            {"questions": [{"sub_unit": "S.", "question": "Q?"}]}
        )
    )
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=_embed_response(1)
    )

    loader = FakeLoader(
        slug="docX", _elements=[_para("p47-a3f8b2c1", "Erste.", page=47)]
    )
    events_path = tmp_path / "golden_events_v1.jsonl"
    synthesise(
        slug="docX",
        loader=loader,
        client=llm_client,
        embed_client=llm_client,
        model="gpt-4o",
        embedding_model="text-embedding-3-large",
        events_path=events_path,
    )
    events = read_events(events_path)
    assert len(events) == 1
    src = events[0].payload["entry_data"]["source_element"]
    assert src["document_id"] == "docX"
    assert src["page_number"] == 47
    assert src["element_type"] == "paragraph"
    # The bare 8-char hash, NOT the full "p47-a3f8b2c1".
    assert src["element_id"] == "a3f8b2c1"


@respx.mock
def test_actor_is_llm_with_correct_metadata(
    tmp_path: Path, llm_client: OpenAIDirectClient
):
    """Event's actor is LLMActor with model, model_version,
    prompt_template_version='v1', temperature=0.0."""
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_completion_response(
            {"questions": [{"sub_unit": "S.", "question": "Q?"}]}
        )
    )
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=_embed_response(1)
    )

    loader = FakeLoader(slug="docX", _elements=[_para("p1-a", "Erste.")])
    events_path = tmp_path / "golden_events_v1.jsonl"
    synthesise(
        slug="docX",
        loader=loader,
        client=llm_client,
        embed_client=llm_client,
        model="gpt-4o",
        embedding_model="text-embedding-3-large",
        events_path=events_path,
    )
    events = read_events(events_path)
    actor = events[0].payload["actor"]
    assert actor["kind"] == "llm"
    assert actor["model"] == "gpt-4o"
    assert actor["model_version"]  # non-empty (taken from the response)
    assert actor["prompt_template_version"] == "v1"
    assert actor["temperature"] == 0.0
```

- [ ] **Step 4.4: Write `tests/test_creation_cli.py`**

Full content for `features/goldens/tests/test_creation_cli.py`:

```python
"""CLI test: `query-eval synthesise --doc X --dry-run` returns 0 and
invokes cmd_synthesise. We import `main` from query_index_eval.cli
and call it with argv directly.

Spec: docs/superpowers/specs/2026-04-29-a5-synthetic-design.md §4.7, §9.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def test_synthesise_subparser_wires_correctly_in_dry_run(
    monkeypatch, tmp_path: "Path"
):
    """`query-eval synthesise --doc X --dry-run` returns 0; the
    cmd_synthesise handler is invoked. We monkeypatch cmd_synthesise
    to record the call without making real LLM requests."""
    from query_index_eval import cli as eval_cli
    from goldens.creation import synthetic as syn_mod

    captured: dict = {}

    def fake_cmd_synthesise(args) -> int:
        captured["doc"] = args.doc
        captured["dry_run"] = args.dry_run
        return 0

    # The CLI imports cmd_synthesise from goldens.creation.synthetic;
    # patch both module slots so whichever is the live binding wins.
    monkeypatch.setattr(syn_mod, "cmd_synthesise", fake_cmd_synthesise, raising=True)
    monkeypatch.setattr(eval_cli, "cmd_synthesise", fake_cmd_synthesise, raising=True)

    rc = eval_cli.main(
        ["synthesise", "--doc", "docX", "--dry-run"]
    )
    assert rc == 0
    assert captured["doc"] == "docX"
    assert captured["dry_run"] is True
```

- [ ] **Step 4.5: Run the new test files; confirm they fail (synthesise / cmd_synthesise not yet defined)**

```bash
cd features/goldens && python -m pytest tests/test_creation_synthetic_respx.py tests/test_creation_cli.py -v
```

Expected: `ImportError` / `ModuleNotFoundError` for `goldens.creation.synthetic`.

- [ ] **Step 4.6: Implement `synthetic.py`**

Full content for `features/goldens/src/goldens/creation/synthetic.py`:

```python
"""LLM-driven synthetic goldset generator.

Spec: docs/superpowers/specs/2026-04-29-a5-synthetic-design.md.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import tiktoken

from goldens.creation._elements_stub import DocumentElement, ElementsLoader
from goldens.creation.prompts import load_prompt
from goldens.creation.synthetic_decomposition import decompose_to_sub_units
from goldens.creation.synthetic_dedup import QuestionDedup
from goldens.operations._time import now_utc_iso
from goldens.schemas.base import Event, LLMActor, SourceElement
from goldens.storage import GOLDEN_EVENTS_V1_FILENAME
from goldens.storage.ids import new_entry_id, new_event_id
from goldens.storage.log import append_event
from goldens.storage.projection import iter_active_retrieval_entries
from llm_clients.base import LLMClient, Message, ResponseFormat

if TYPE_CHECKING:
    pass

__all__ = [
    "GeneratedQuestion",
    "SynthesiseResult",
    "synthesise",
    "cmd_synthesise",
]

_log = logging.getLogger(__name__)


# ---------- Result types --------------------------------------------


@dataclass(frozen=True)
class GeneratedQuestion:
    sub_unit: str
    question: str


@dataclass(frozen=True)
class SynthesiseResult:
    slug: str
    events_path: Path
    elements_seen: int
    elements_skipped: int
    elements_with_questions: int
    questions_generated: int
    questions_kept: int
    questions_dropped_dedup: int
    questions_dropped_cap: int
    events_written: int
    prompt_tokens_estimated: int
    dry_run: bool


# ---------- Internals -----------------------------------------------


def _render_prompt(template: str, sub_units: tuple[str, ...]) -> str:
    """Render the bundled prompt: serialise the indexed sub-units into
    `{content}`."""
    indexed = "\n".join(f"{i}. {s}" for i, s in enumerate(sub_units))
    return template.format(content=indexed)


def _parse_questions(raw: str) -> list[GeneratedQuestion] | None:
    """Parse the LLM JSON response. Returns None on JSONDecodeError or
    on shape that is not `{questions: [...]}`. Otherwise returns the
    list of (validated) GeneratedQuestion objects."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    items = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    out: list[GeneratedQuestion] = []
    for item in items:
        if not isinstance(item, dict):
            _log.warning("dropping non-object item in questions list: %r", item)
            continue
        sub_unit = item.get("sub_unit")
        question = item.get("question")
        if not isinstance(sub_unit, str) or not isinstance(question, str):
            _log.warning("dropping item missing sub_unit/question: %r", item)
            continue
        if not question.strip():
            _log.warning("dropping item with empty question: %r", item)
            continue
        out.append(GeneratedQuestion(sub_unit=sub_unit, question=question))
    return out


def _generate_questions_for_element(
    element: DocumentElement,
    sub_units: tuple[str, ...],
    *,
    client: LLMClient,
    model: str,
    template: str,
    temperature: float,
    max_prompt_tokens: int,
    tokenizer: tiktoken.Encoding,
) -> tuple[list[GeneratedQuestion], str | None, int]:
    """Drive one element through the LLM. Returns
    (questions, resolved_model_version, tokens_estimated).

    Strategy (spec §4.3):
      1. Build the bundled prompt; estimate tokens with tiktoken.
      2. If estimated > max_prompt_tokens → fallback to per-sub-unit calls.
      3. Else: 1 JSON-mode call. On JSONDecodeError, retry once.
         Second failure → log + skip (return [], None, tokens).
    """
    bundled = _render_prompt(template, sub_units)
    bundled_tokens = len(tokenizer.encode(bundled))

    if bundled_tokens > max_prompt_tokens:
        _log.info(
            "element %s: bundled prompt %d tokens > %d; falling back to per-sub-unit calls",
            element.element_id,
            bundled_tokens,
            max_prompt_tokens,
        )
        out: list[GeneratedQuestion] = []
        resolved = None
        total_tokens = 0
        for s in sub_units:
            single = _render_prompt(template, (s,))
            total_tokens += len(tokenizer.encode(single))
            qs, model_version = _one_call(
                client=client,
                model=model,
                prompt=single,
                temperature=temperature,
            )
            if qs is None:
                _log.warning("skipping sub-unit of %s after parse failures", element.element_id)
                continue
            resolved = resolved or model_version
            out.extend(qs)
        return out, resolved, total_tokens

    qs, model_version = _one_call(
        client=client, model=model, prompt=bundled, temperature=temperature
    )
    if qs is None:
        _log.warning("skipping element %s after JSON parse failures", element.element_id)
        return [], None, bundled_tokens
    return qs, model_version, bundled_tokens


def _one_call(
    *,
    client: LLMClient,
    model: str,
    prompt: str,
    temperature: float,
) -> tuple[list[GeneratedQuestion] | None, str | None]:
    """One JSON-mode completion with one retry on parse failure.
    Returns (questions, resolved_model_version) or (None, None) on
    two consecutive parse failures."""
    messages = [Message(role="user", content=prompt)]
    rf = ResponseFormat(type="json_object")
    for attempt in range(2):
        completion = client.complete(
            messages=messages,
            model=model,
            temperature=temperature,
            response_format=rf,
        )
        parsed = _parse_questions(completion.text)
        if parsed is not None:
            return parsed, completion.model
    return None, None


def _build_event(
    *,
    slug: str,
    element: DocumentElement,
    question: str,
    actor: LLMActor,
    timestamp_utc: str,
) -> Event:
    # Strip the "p{page}-" prefix so the persisted element_id is the
    # bare 8-char content hash (matches A.4's loader.to_source_element
    # mapping; spec §4.5).
    bare_element_id = element.element_id.split("-", 1)[1]
    src = SourceElement(
        document_id=slug,
        page_number=element.page_number,
        element_id=bare_element_id,
        element_type=element.element_type,
    )
    return Event(
        event_id=new_event_id(),
        timestamp_utc=timestamp_utc,
        event_type="created",
        entry_id=new_entry_id(),
        schema_version=1,
        payload={
            "task_type": "retrieval",
            "actor": actor.to_dict(),
            "action": "synthesised",
            "notes": None,
            "entry_data": {
                "query": question,
                "expected_chunk_ids": [],
                "chunk_hashes": {},
                "refines": None,
                "source_element": src.to_dict(),
            },
        },
    )


def _resolve_template_for(element: DocumentElement, version: str) -> str | None:
    """Resolve the prompt template for this element's type. Returns
    None for element_types that are skipped in v1 (heading, figure)
    or have no shipped template."""
    et = element.element_type
    if et == "table":
        return load_prompt("table_row", version)
    if et in ("paragraph", "list_item"):
        return load_prompt(et, version)
    return None  # heading / figure


# ---------- Driver --------------------------------------------------


def synthesise(
    *,
    slug: str,
    loader: ElementsLoader,
    client: LLMClient,
    embed_client: LLMClient | None,
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
    events_path: Path | None = None,
) -> SynthesiseResult:
    """Walk loader.elements(), generate questions, write events.
    See spec §4.5 for the full flow."""
    events_path = events_path or (
        Path("outputs") / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME
    )

    existing_keys: set[str] = set()
    if resume and events_path.exists():
        for entry in iter_active_retrieval_entries(events_path):
            if entry.source_element is not None:
                existing_keys.add(entry.source_element.element_id)

    tokenizer = tiktoken.get_encoding("cl100k_base")
    dedup = QuestionDedup(
        client=embed_client,
        model=embedding_model or "",
        threshold=0.95,
    )

    elements_seen = 0
    elements_skipped = 0
    elements_with_questions = 0
    questions_generated = 0
    questions_kept = 0
    questions_dropped_cap = 0
    events_written = 0
    prompt_tokens_estimated = 0

    started = start_from is None
    yielded = 0

    for element in loader.elements():
        if not started:
            if element.element_id == start_from:
                started = True
            else:
                continue
        if limit is not None and yielded >= limit:
            break
        yielded += 1
        elements_seen += 1

        # Resume skip uses the BARE hash (matches what we persist).
        bare_id = element.element_id.split("-", 1)[1]
        if resume and bare_id in existing_keys:
            elements_skipped += 1
            continue

        sub_units = decompose_to_sub_units(element)
        if not sub_units:
            elements_skipped += 1
            continue

        template = _resolve_template_for(element, prompt_template_version)
        if template is None:
            elements_skipped += 1
            continue

        # Dry-run short-circuit BEFORE any LLM call (completion or embedding).
        if dry_run:
            rendered = _render_prompt(template, sub_units)
            prompt_tokens_estimated += len(tokenizer.encode(rendered))
            continue

        existing_questions = [
            e.query
            for e in iter_active_retrieval_entries(events_path)
            if e.source_element is not None and e.source_element.element_id == bare_id
        ] if events_path.exists() else []

        generated, model_version, tokens = _generate_questions_for_element(
            element,
            sub_units,
            client=client,
            model=model,
            template=template,
            temperature=temperature,
            max_prompt_tokens=max_prompt_tokens,
            tokenizer=tokenizer,
        )
        prompt_tokens_estimated += tokens
        questions_generated += len(generated)
        if not generated:
            elements_skipped += 1
            continue

        kept = dedup.filter(
            [g.question for g in generated],
            against=existing_questions,
            source_key=bare_id,
        )
        kept_objs = [g for g in generated if g.question in set(kept)]

        if len(kept_objs) > max_questions_per_element:
            dropped = len(kept_objs) - max_questions_per_element
            questions_dropped_cap += dropped
            _log.warning(
                "element %s: %d kept questions exceeds cap %d; truncating",
                element.element_id,
                len(kept_objs),
                max_questions_per_element,
            )
            kept_objs = kept_objs[:max_questions_per_element]

        if not kept_objs:
            elements_skipped += 1
            continue

        elements_with_questions += 1
        ts = now_utc_iso()
        actor = LLMActor(
            model=model,
            model_version=model_version or model,
            prompt_template_version=prompt_template_version,
            temperature=temperature,
        )
        for g in kept_objs:
            ev = _build_event(
                slug=slug,
                element=element,
                question=g.question,
                actor=actor,
                timestamp_utc=ts,
            )
            append_event(events_path, ev)
            events_written += 1
            questions_kept += 1

    questions_dropped_dedup = (
        questions_generated - questions_kept - questions_dropped_cap
    )
    return SynthesiseResult(
        slug=slug,
        events_path=events_path,
        elements_seen=elements_seen,
        elements_skipped=elements_skipped,
        elements_with_questions=elements_with_questions,
        questions_generated=questions_generated,
        questions_kept=questions_kept,
        questions_dropped_dedup=max(questions_dropped_dedup, 0),
        questions_dropped_cap=questions_dropped_cap,
        events_written=events_written,
        prompt_tokens_estimated=prompt_tokens_estimated,
        dry_run=dry_run,
    )


# ---------- CLI handler ---------------------------------------------


def cmd_synthesise(args: argparse.Namespace) -> int:  # pragma: no cover
    """Argparse handler. Builds the LLMClient + embed_client from env
    + flags, instantiates AnalyzeJsonLoader(slug=args.doc) (after A.4
    merges; until then this CLI handler is unreachable in tests and
    marked pragma: no cover), and calls synthesise(...).

    Returns 0 on success, 2 on missing inputs, 1 on unhandled
    exception (logged via logging).
    """
    from llm_clients.openai_direct import OpenAIDirectClient, OpenAIDirectConfig

    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        print("ERROR: LLM_API_KEY env var is required", flush=True)
        return 2

    base_url = args.llm_base_url or os.environ.get(
        "LLM_BASE_URL", "https://api.openai.com/v1"
    )
    model = args.llm_model or os.environ.get("LLM_MODEL")
    if not model:
        print("ERROR: --llm-model or LLM_MODEL env var is required", flush=True)
        return 2

    completion_client = OpenAIDirectClient(
        OpenAIDirectConfig(api_key=api_key, base_url=base_url)
    )

    embed_client: OpenAIDirectClient | None = None
    embedding_model = args.embedding_model or os.environ.get("LLM_EMBEDDING_MODEL")
    openai_key = os.environ.get("OPENAI_API_KEY")
    if embedding_model and openai_key:
        embed_client = OpenAIDirectClient(
            OpenAIDirectConfig(api_key=openai_key, base_url="https://api.openai.com/v1")
        )
    elif openai_key and not embedding_model:
        embedding_model = "text-embedding-3-large"
        embed_client = OpenAIDirectClient(
            OpenAIDirectConfig(api_key=openai_key, base_url="https://api.openai.com/v1")
        )

    # Loader resolution depends on A.4 — until that lands the CLI
    # handler cannot construct AnalyzeJsonLoader. The synthesise()
    # function is fully usable from Python without going through the
    # CLI; that is what is exercised in tests.
    from goldens.creation.elements import AnalyzeJsonLoader  # type: ignore[import-not-found]

    loader = AnalyzeJsonLoader(slug=args.doc)

    result = synthesise(
        slug=args.doc,
        loader=loader,
        client=completion_client,
        embed_client=embed_client,
        model=model,
        embedding_model=embedding_model,
        prompt_template_version=args.prompt_template_version,
        temperature=args.temperature,
        max_questions_per_element=args.max_questions_per_element,
        max_prompt_tokens=args.max_prompt_tokens,
        start_from=args.start_from,
        limit=args.limit,
        dry_run=args.dry_run,
        resume=args.resume,
    )
    print(
        f"slug={result.slug} events_written={result.events_written} "
        f"kept={result.questions_kept} dropped_dedup={result.questions_dropped_dedup} "
        f"dropped_cap={result.questions_dropped_cap} "
        f"prompt_tokens_estimated={result.prompt_tokens_estimated} "
        f"dry_run={result.dry_run}"
    )
    return 0
```

Note for the engineer: the `cmd_synthesise` body is marked `pragma: no cover` because (a) it depends on A.4's `AnalyzeJsonLoader`, and (b) it constructs real `OpenAIDirectClient` instances against env vars. The test in Task 4.4 monkey-patches the function before invocation, so its body is not exercised in tests.

- [ ] **Step 4.7: Add re-exports to `creation/__init__.py`**

Update `features/goldens/src/goldens/creation/__init__.py` to:

```python
"""Synthetic goldset generation package (A.5)."""

from goldens.creation.synthetic import (
    GeneratedQuestion,
    SynthesiseResult,
    cmd_synthesise,
    synthesise,
)

__all__ = [
    "GeneratedQuestion",
    "SynthesiseResult",
    "cmd_synthesise",
    "synthesise",
]
```

- [ ] **Step 4.8: Wire the `synthesise` subparser into `query_index_eval/cli.py`**

In `features/evaluators/chunk_match/src/query_index_eval/cli.py`, add the import near the existing `from goldens import ...` line and register the subparser inside `main()`. The existing imports look like:

```python
from goldens import GOLDEN_EVENTS_V1_FILENAME, iter_active_retrieval_entries
```

Add directly below it:

```python
from goldens.creation.synthetic import cmd_synthesise
```

Then, inside `def main(...)`, after the existing `p_schema = sub.add_parser("schema-discovery", ...)` block (around line 162), append the new subparser registration:

```python
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

The subparser block must appear **before** the `try: args = parser.parse_args(argv)` call so all subcommands are registered first.

- [ ] **Step 4.9: Run the synthesise + CLI tests; confirm they pass**

```bash
cd features/goldens && python -m pytest tests/test_creation_synthetic_respx.py tests/test_creation_cli.py -v
```

Expected: `9 passed`.

If `test_creation_cli.py` fails with `ModuleNotFoundError: No module named 'query_index_eval'`, the chunk_match package needs to be reinstalled in the venv:

```bash
pip install -e features/evaluators/chunk_match[test]
```

If it still fails, the test can also `monkeypatch` the import at runtime — but the proper fix is the editable install above.

- [ ] **Step 4.10: Run the full goldens suite; confirm coverage gate at 70 %**

```bash
cd features/goldens && python -m pytest
```

Expected: every test passes; `--cov-fail-under=70` is satisfied.

- [ ] **Step 4.11: Smoke-test the CLI subparser registration**

Without running an actual synthesise pass, prove the subparser is wired:

```bash
cd /home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft-a5-synthetic
source .venv/bin/activate
query-eval synthesise --help
```

Expected: argparse prints the subparser's help, including `--doc`, `--dry-run`, `--resume`, etc.

- [ ] **Step 4.12: Commit**

```bash
git add features/goldens/pyproject.toml \
        features/goldens/src/goldens/creation/__init__.py \
        features/goldens/src/goldens/creation/synthetic.py \
        features/goldens/tests/test_creation_synthetic_respx.py \
        features/goldens/tests/test_creation_cli.py \
        features/evaluators/chunk_match/src/query_index_eval/cli.py
git commit -m "feat(goldens/creation): add synthesise driver + query-eval subparser (Phase A.5.4)"
```

Verify with `git log -1 --stat` that the commit lists exactly those six paths.

---

## Post-Plan Hand-off

Once all four commits land on `feat/a5-synthetic`:

1. Open a single PR with the four-commit history (per spec §10).
2. The PR description should reference spec §10 and call out the coverage-threshold change in commit 4.
3. Note in the PR that `_elements_stub.py` is a **bridge** — once A.4 merges, the one-line import swap (§6 of the spec) replaces the stub with `from goldens.creation.elements import ...`.
4. The CLI handler `cmd_synthesise` is `pragma: no cover` until A.4 merges; the integration smoke (a real `query-eval synthesise --doc <slug> --dry-run` against a small fixture) lands in the A.4 hand-off PR, not here.

---

## Self-Review (run after writing the plan)

- **Spec coverage:** §4.1 → Task 1; §4.2 → Task 2; §4.3 + §4.5 + §4.6 + §4.7 → Task 4; §4.4 → Task 3; §6 (loader stub hand-off) → Task 2 (creation) + post-A.4 PR (deletion); §9 test plan → Tasks 1/2/3/4 each contain the spec'd tests; §10 commit plan → Tasks 1–4 commit subjects match exactly; §11 coverage-threshold change → Task 4 Step 4.1.
- **Placeholder scan:** no "TBD" / "TODO" / "implement later" markers; all code blocks contain runnable code; all `pytest` invocations specify the exact path and expected outcome.
- **Type consistency:** `load_prompt(element_type, version="v1")` consistent across §3 layout (Task 1.4 shows it), §4.1 docstring, and the implementation. `decompose_to_sub_units(element) -> tuple[str, ...]` consistent across decl + tests. `QuestionDedup.filter(generated, *, against, source_key)` keyword-args match the test usage. `synthesise(...)` keyword-only, with the same arg names the tests pass. `SourceElement.element_id` is the **bare hash** in both the implementation (Task 4.6 `_build_event`) and the test (Task 4.3 `test_source_element_is_persisted_with_stripped_page_prefix`).

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-29-a5-synthetic.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — Lead dispatches a fresh subagent per Task, reviews between Tasks, fast iteration. Use `superpowers:subagent-driven-development`.

**2. Inline Execution** — Execute Tasks in this session using `superpowers:executing-plans`, batched with checkpoints for review.

**Which approach?** (Lead decides; this plan worker idles `awaiting-execution-mode` after committing the plan doc.)
