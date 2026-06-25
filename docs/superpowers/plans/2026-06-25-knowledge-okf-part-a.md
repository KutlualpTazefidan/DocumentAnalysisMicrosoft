# Knowledge Tab + OKF (Part A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the LM interview into a browsable Open Knowledge Format (OKF) concept graph under `data/knowledge/bauartpruefung-lm/`, viewable in a new global **Wissen** admin tab — additively, without touching the Azure retrieval or existing Agent paths.

**Architecture:** A one-off agent-assisted pass (durable `OKF_EXTRACTION` prompt + minimal runner) authors the OKF files; a pure-file-I/O reader + validator expose them; a read-only `/api/admin/knowledge/*` JSON endpoint serves them; a React three-pane viewer (`Wissen` rail entry) browses base → concept → outgoing-link graph.

**Tech Stack:** Python 3.12 (FastAPI, pyyaml, python-docx, deepagents/langchain-openai lazy), React + Vite + TanStack Query + react-router (HashRouter), Tailwind, vitest + msw, pytest + httpx TestClient.

**Spec:** `docs/superpowers/specs/2026-06-25-knowledge-okf-integration-design.md`

## Global Constraints

- **Import boundary** (`scripts/check_import_boundary.sh`): no `openai.*` / `azure.search.*` imports outside `features/pipelines/microsoft/retrieval/` + `features/core/src/llm_clients/`. The knowledge reader/validator/endpoint/docx/config must have **zero** such imports. `langchain_openai` and `deepagents` are NOT flagged, but the authoring runner imports them **lazily inside functions** (mirroring `agent/build.py`) so module import never requires the `agent` extra.
- **Ruff**: line-length = 100, E501 enforced. Files holding long verbatim prompt strings start with `# ruff: noqa: E501` (mirror `agent/verify_prompts.py`).
- **mypy** runs in pre-commit — annotate everything. Use modern hints (`list[str]`, `str | None`).
- **No `uv`** here: the backend uses the **root `.venv`** (plain pip/editable). Run Python via `. .venv/bin/activate && pytest …`.
- **Storage**: OKF bases live under gitignored `data/knowledge/<base>/` (config key `KNOWLEDGE_ROOT`, default `data/knowledge`). Do **not** commit the produced `.md` files.
- **Naming**: never mention AI/assistant tools in commit messages, code, or docs.
- **Additive**: do not edit `agent/build.py`, `agent/tools.py`, `agent/prompts.py`, `agent/verify_prompts.py`, `routers/admin/agent.py`, or anything under `features/pipelines/microsoft/`. Verify with `git diff --stat` at the end.

## File Structure

**Backend (new, in the `local_pdf` package):**
- `features/pipelines/local-pdf/src/local_pdf/knowledge/__init__.py` — re-exports the reader/validator public API.
- `.../local_pdf/knowledge/reader.py` — pure file I/O: dataclasses + `list_bases` / `list_concepts` / `read_concept` / `search_concepts` + frontmatter/link helpers. **One source of truth for link normalization.**
- `.../local_pdf/knowledge/validator.py` — `validate_base` (structural gate).
- `.../local_pdf/knowledge/docx_to_text.py` — `.docx` → text helper.
- `.../local_pdf/knowledge/author.py` — minimal one-off authoring runner (lazy deepagents).
- `.../local_pdf/agent/extract_prompts.py` — `OKF_EXTRACTION` durable prompt (the reusable artifact).
- `.../local_pdf/api/routers/admin/knowledge.py` — read-only JSON endpoint.

**Backend (modified):**
- `.../local_pdf/api/config.py` — add `knowledge_root` field.
- `.../local_pdf/api/app.py` — import + `include_router(knowledge_router)`.

**Backend tests (new):**
- `features/pipelines/local-pdf/tests/test_knowledge_reader.py`
- `features/pipelines/local-pdf/tests/test_knowledge_validator.py`
- `features/pipelines/local-pdf/tests/test_routers_admin_knowledge.py`

**Frontend (new):**
- `frontend/src/admin/api/knowledge.ts` — typed fetch fns + interfaces.
- `frontend/src/admin/routes/Knowledge.tsx` — three-pane viewer.
- `frontend/src/admin/routes/__tests__/Knowledge.test.tsx`

**Frontend (modified):**
- `frontend/src/shared/icons/index.ts` — export `Library`.
- `frontend/src/shell/AdminShell.tsx` — add `Wissen` `ADMIN_NAV` entry + import.
- `frontend/src/App.tsx` — import `Knowledge` + add `<Route path="knowledge" …>`.

**Produced content (gitignored, not committed):**
- `data/knowledge/bauartpruefung-lm/**.md`

---

## Task 1: Author the LM base (the crux — front-loaded)

Produce the OKF concept graph from the interview and gate it on a **human faithfulness review** before any reader/endpoint/UI is built. Deliverable: `data/knowledge/bauartpruefung-lm/` populated + reviewed, plus the durable `OKF_EXTRACTION` prompt, `docx_to_text`, and the minimal `author.py` runner.

**Files:**
- Create: `.../local_pdf/knowledge/docx_to_text.py`
- Create: `.../local_pdf/agent/extract_prompts.py`
- Create: `.../local_pdf/knowledge/author.py`
- Create: `.../local_pdf/knowledge/__init__.py` (start it here; reader exports added in Task 2)
- Test: `features/pipelines/local-pdf/tests/test_knowledge_docx.py`

**Interfaces:**
- Produces: `docx_to_text(docx_path: Path) -> str`; `OKF_EXTRACTION: str`; `author_base(interview_text: str, out_dir: Path, *, model: object | None = None) -> list[str]` (returns base-relative paths written).
- Consumes: `local_pdf.agent.build._build_model` (existing) for the Azure GPT-4.1 model.

- [ ] **Step 1: Savepoint tag before any change**

```bash
cd /home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft
git tag pre-knowledge-okf
git tag --list 'pre-knowledge-okf' 'agent-spike-verifier-v1'
```
Expected: both tags listed.

- [ ] **Step 2: Write the failing test for `docx_to_text`**

```python
# features/pipelines/local-pdf/tests/test_knowledge_docx.py
from __future__ import annotations

from pathlib import Path

from local_pdf.knowledge.docx_to_text import docx_to_text


def _make_docx(path: Path, paragraphs: list[str]) -> None:
    import docx

    d = docx.Document()
    for p in paragraphs:
        d.add_paragraph(p)
    d.save(str(path))


def test_docx_to_text_reads_paragraphs_hermetically(tmp_path: Path) -> None:
    # Hermetic: generate the .docx in the test (the real interview lives under
    # gitignored data/ and is absent in CI / fresh clones).
    docx_path = tmp_path / "demo.docx"
    _make_docx(
        docx_path,
        ["Bauartprüfung erste Zeile.", "Nachweiskonzept zweite Zeile.", "Dritte Zeile."],
    )
    text = docx_to_text(docx_path)
    assert "Bauartprüfung erste Zeile." in text
    assert "Nachweiskonzept zweite Zeile." in text
    # paragraphs separated by newlines, not collapsed into one blob
    assert text.count("\n") >= 2
```

- [ ] **Step 3: Run it to verify it fails**

Run: `. .venv/bin/activate && pytest features/pipelines/local-pdf/tests/test_knowledge_docx.py -v`
Expected: FAIL — `ModuleNotFoundError: local_pdf.knowledge.docx_to_text`.

- [ ] **Step 4: Implement `docx_to_text`**

```python
# features/pipelines/local-pdf/src/local_pdf/knowledge/docx_to_text.py
"""Convert a .docx to plain UTF-8 text, one paragraph per line.

Uses python-docx when importable; otherwise falls back to unzipping the
package and stripping XML (works headless with no extra deps)."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path


def docx_to_text(docx_path: Path) -> str:
    try:
        import docx  # python-docx

        document = docx.Document(str(docx_path))
        paras = [p.text.strip() for p in document.paragraphs]
        return "\n".join(p for p in paras if p)
    except ModuleNotFoundError:
        return _docx_to_text_fallback(docx_path)


def _docx_to_text_fallback(docx_path: Path) -> str:
    with zipfile.ZipFile(docx_path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    # paragraph boundary → newline, then strip all remaining tags
    xml = xml.replace("</w:p>", "\n")
    text = re.sub(r"<[^>]*>", "", xml)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)
```

- [ ] **Step 5: Create the knowledge package `__init__`**

```python
# features/pipelines/local-pdf/src/local_pdf/knowledge/__init__.py
"""OKF knowledge-base I/O (pure file reads) for the Wissen tab."""

from local_pdf.knowledge.docx_to_text import docx_to_text

__all__ = ["docx_to_text"]
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `. .venv/bin/activate && pytest features/pipelines/local-pdf/tests/test_knowledge_docx.py -v`
Expected: PASS.

- [ ] **Step 7: Write the durable `OKF_EXTRACTION` prompt**

```python
# features/pipelines/local-pdf/src/local_pdf/agent/extract_prompts.py
# ruff: noqa: E501 — long prompt prose lines are intentional; do not reflow.
"""Reusable, versioned prompt for authoring an OKF knowledge base from an
interview transcript. This is THE consistency artifact: every future interview
is extracted with the same principles. The runner (knowledge/author.py) only
provides orchestration."""

OKF_EXTRACTION = """Du bist ein Wissens-Kurator. Deine Aufgabe: ein Experten-Interview (Transkript) in eine Wissensbasis im **Open Knowledge Format (OKF)** umwandeln.

# Was OKF ist
- Eine Wissensbasis ist ein **Verzeichnis aus Markdown-Dateien**; **ein Konzept pro Datei**.
- Der **Dateipfad ist die Identität** des Konzepts (z.B. `/regelwerk/r003.md`).
- Jede Datei beginnt mit **YAML-Frontmatter**. **Pflichtfeld: `type`**. Empfohlen: `title`, `description`, `tags` (Liste), `timestamp` (ISO 8601). `resource` (URL) nur wenn eine echte kanonische URL existiert — sonst weglassen, niemals erfinden.
- Konzepte verlinken sich mit **normalen Markdown-Links mit wurzel-relativem Pfad**: `[BAM](/behoerden/bam.md)`. Diese Links bilden den **Graphen**.
- Reservierte Dateien: `index.md` (Überblick/Einstieg je Verzeichnis), `log.md` (Änderungshistorie).

# Typ-Vokabular (erweiterbar)
`Behörde`, `Richtlinie`, `Regelwerk`, `Norm`, `Verfahren`, `Rolle`, `Konzept`, `Prüfthema`, `Dokumentstruktur`, `Artefakt`, `Begriff`.

# Kuratierungs-Prinzipien (verbindlich)
1. **Quellentreu.** Erfinde KEINE Fakten, die nicht im Transkript stehen.
2. **Transkriptionsrauschen normalisieren.** Korrigiere offensichtliche Artefakte zu den richtigen Fachbegriffen: `Bauer Zulassung`→Bauartzulassung, `Bus`→BASE, `Bahn`/`Baum`→BAM, `PDS er`→PDSR, `GGR 0 11`→GGR 011, `besonderer Form`/`Strato aktive`→radioaktive Stoffe in besonderer Form.
3. **Unsicherheit kennzeichnen.** Wo das Transkript mehrdeutig oder vermutlich falsch ist (z.B. BASE als „…nuklearen Erzeugung" statt korrekt „…nuklearen Entsorgung"), schreibe eine Zeile `> [!review] <Hinweis>` in den Body statt still zu raten.
4. **Großzügig verlinken.** Verweise auf JEDES erwähnte andere Konzept per Markdown-Link.

# Vorgehen
1. Lies das Transkript. Identifiziere die Konzepte (Behörden, Regelwerke, Verfahren, Rollen, Konzepte, Prüfthemen, Dokumentstrukturen, Artefakte, Begriffe).
2. Schreibe für jedes Konzept GENAU EINE Datei mit `write_file(pfad, inhalt)`, wobei `pfad` wurzel-relativ ist (z.B. `/behoerden/bam.md`) und `inhalt` mit dem YAML-Frontmatter beginnt, gefolgt vom Markdown-Body mit großzügigen Verweisen.
3. Schreibe `/index.md`: Kurzüberblick der Wissensbasis, Einstiegspunkte (Links zu den wichtigsten Konzepten), und einen **Provenienz-Absatz** (Quelle: dieses Interview; Befragter; Datum).
4. Schreibe `/log.md`: eine Zeile mit Erstellungsdatum und Quelle.
5. Sprache der Inhalte: **Deutsch** (Fachdomäne ist deutsch).

# Beispiel-Konzeptdatei
```
---
type: Verfahren
title: Bauartprüfung
description: Prüfung zulassungspflichtiger Versandstücke für den Transport radioaktiver Stoffe.
tags: [bauartpruefung, versandstueck, zulassung]
timestamp: 2026-06-25T00:00:00Z
---

Die Bauartprüfung wird von [BAM](/behoerden/bam.md) und [BASE](/behoerden/base.md) durchgeführt. Grundlage ist die [R 003](/regelwerk/r003.md); zu beachten ist der [PDSR-Guide](/regelwerk/pdsr-guide.md). Der Nachweis erfolgt nach dem [Nachweiskonzept](/konzepte/nachweiskonzept.md).
```

Beginne jetzt. Schreibe ALLE Konzepte als Dateien. Wenn alle Dateien geschrieben sind, antworte mit einer kurzen Liste der erstellten Pfade."""
```

- [ ] **Step 8: Implement the minimal authoring runner**

```python
# features/pipelines/local-pdf/src/local_pdf/knowledge/author.py
"""One-off agent-assisted authoring: run a flat deepagents pass with the
durable OKF_EXTRACTION prompt over an interview transcript and persist the
emitted OKF files to disk. Deliberately minimal — no CLI, no multi-interview
runner (deferred until interview #2). deepagents/langchain imported lazily so
importing this module never requires the `agent` extra."""

from __future__ import annotations

from pathlib import Path


def author_base(
    interview_text: str,
    out_dir: Path,
    *,
    model: object | None = None,
) -> list[str]:
    from deepagents import create_deep_agent  # lazy
    from deepagents.backends.utils import file_data_to_string  # lazy

    from local_pdf.agent.build import _build_model  # lazy
    from local_pdf.agent.extract_prompts import OKF_EXTRACTION

    agent = create_deep_agent(
        model=model or _build_model(),
        tools=[],
        system_prompt=OKF_EXTRACTION,
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": interview_text}]}
    )
    files: dict = result.get("files", {})  # virtual-FS: path -> file data
    written: list[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for vpath, data in files.items():
        rel = vpath.lstrip("/")
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(file_data_to_string(data), encoding="utf-8")
        written.append(rel)
    return written
```

- [ ] **Step 9: Commit the authoring tooling**

```bash
cd /home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft
git add features/pipelines/local-pdf/src/local_pdf/knowledge/docx_to_text.py \
        features/pipelines/local-pdf/src/local_pdf/knowledge/__init__.py \
        features/pipelines/local-pdf/src/local_pdf/knowledge/author.py \
        features/pipelines/local-pdf/src/local_pdf/agent/extract_prompts.py \
        features/pipelines/local-pdf/tests/test_knowledge_docx.py
git commit -m "feat(knowledge): OKF authoring tooling (docx_to_text, OKF_EXTRACTION prompt, runner)"
```

- [ ] **Step 10: Run the one-off authoring pass to produce the base** _(CONTROLLER runs this, not the task implementer — it is a live Azure call + the crux)_

Run:
```bash
cd /home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft
set -a && . ./.env && set +a   # export Azure env (AI_FOUNDRY_*, CHAT_DEPLOYMENT_NAME) for the run
. .venv/bin/activate
python -c "
from pathlib import Path
from local_pdf.knowledge.docx_to_text import docx_to_text
from local_pdf.knowledge.author import author_base
text = docx_to_text(Path('data/interview/Text-Int-BAM3.3-LM_26.06.23.docx'))
paths = author_base(text, Path('data/knowledge/bauartpruefung-lm'))
print(f'{len(paths)} files written:')
print('\n'.join(sorted(paths)))
"
```
Expected: ~15–30 files written, including `index.md`, `log.md`, and concepts under `behoerden/`, `regelwerk/`, `verfahren/`, `konzepte/`, `pruefthemen/`, `strukturen/`. (Requires Azure GPT-4.1 env: `AI_FOUNDRY_ENDPOINT`, `AI_FOUNDRY_KEY`, `CHAT_DEPLOYMENT_NAME` — sourced from `.env` above. This is a live call.)

- [ ] **Step 11: HUMAN FAITHFULNESS REVIEW — the semantic gate (controller + user)**

This is **not** a subagent self-approval. The implementer surfaces the produced base; the controller and user read **2–3 concepts** (e.g. `verfahren/bauartpruefung.md`, `konzepte/nachweiskonzept.md`, `behoerden/base.md`) and confirm:
- Facts are faithful to the transcript (no inventions).
- Transcription noise is normalized (BAM/BASE/PDSR/GGR correct).
- Uncertain claims carry a `> [!review]` note (e.g. BASE = „…nukleare Entsorgung").
- Concepts cross-link.

If quality is poor, fix `OKF_EXTRACTION` and re-run Step 10; or hand-edit the files. **Do not proceed to Task 2 until this review passes.** (The base is gitignored — nothing to commit here.)

---

## Task 2: Knowledge reader (pure file I/O)

**Files:**
- Create: `.../local_pdf/knowledge/reader.py`
- Modify: `.../local_pdf/knowledge/__init__.py`
- Test: `features/pipelines/local-pdf/tests/test_knowledge_reader.py`

**Interfaces:**
- Produces (consumed by Task 3 validator + Task 4 endpoint):
  - `@dataclass(frozen=True) BaseSummary(name: str, title: str, concept_count: int)`
  - `@dataclass(frozen=True) ConceptSummary(path: str, type: str, title: str, tags: list[str])`
  - `@dataclass(frozen=True) ConceptLink(text: str, path: str, resolved: bool)`
  - `@dataclass(frozen=True) Concept(path: str, type: str, title: str, description: str, timestamp: str, tags: list[str], body: str, links: list[ConceptLink], malformed: bool)`
  - `list_bases(root: Path) -> list[BaseSummary]`
  - `list_concepts(root: Path, base: str) -> list[ConceptSummary]`
  - `read_concept(root: Path, base: str, path: str) -> Concept` (raises `FileNotFoundError` if missing, `ValueError` on path traversal)
  - `search_concepts(root: Path, base: str, query: str) -> list[ConceptSummary]`
- **Link normalization (single source of truth):** a `[text](/a/b.md)` link → `ConceptLink(text, "a/b.md", resolved=(base_dir/"a/b.md").exists())`. The frontend reuses `link.path` verbatim as the `?path=` value.

- [ ] **Step 1: Write the failing tests**

```python
# features/pipelines/local-pdf/tests/test_knowledge_reader.py
from __future__ import annotations

from pathlib import Path

import pytest

from local_pdf.knowledge.reader import (
    list_bases,
    list_concepts,
    read_concept,
    search_concepts,
)


def _make_base(root: Path) -> None:
    b = root / "demo"
    (b / "behoerden").mkdir(parents=True)
    (b / "index.md").write_text(
        "---\ntype: Index\ntitle: Demo\n---\nEinstieg: [BAM](/behoerden/bam.md).\n",
        encoding="utf-8",
    )
    (b / "behoerden" / "bam.md").write_text(
        "---\ntype: Behörde\ntitle: BAM\ntags: [behoerde]\n---\n"
        "Siehe [Fehlt](/behoerden/missing.md) und [Index](/index.md).\n",
        encoding="utf-8",
    )
    (b / "broken.md").write_text("kein frontmatter hier\n", encoding="utf-8")


def test_list_bases_counts_concepts(tmp_path: Path) -> None:
    _make_base(tmp_path)
    bases = list_bases(tmp_path)
    assert len(bases) == 1
    assert bases[0].name == "demo"
    assert bases[0].title == "Demo"
    assert bases[0].concept_count == 3


def test_list_concepts_returns_type_and_title(tmp_path: Path) -> None:
    _make_base(tmp_path)
    concepts = {c.path: c for c in list_concepts(tmp_path, "demo")}
    assert concepts["behoerden/bam.md"].type == "Behörde"
    assert concepts["behoerden/bam.md"].title == "BAM"
    assert concepts["behoerden/bam.md"].tags == ["behoerde"]


def test_read_concept_extracts_links_and_resolution(tmp_path: Path) -> None:
    _make_base(tmp_path)
    c = read_concept(tmp_path, "demo", "behoerden/bam.md")
    assert c.type == "Behörde"
    assert c.malformed is False
    by_path = {ln.path: ln for ln in c.links}
    assert by_path["index.md"].resolved is True
    assert by_path["behoerden/missing.md"].resolved is False


def test_read_concept_flags_malformed(tmp_path: Path) -> None:
    _make_base(tmp_path)
    c = read_concept(tmp_path, "demo", "broken.md")
    assert c.malformed is True
    assert c.type == ""


def test_read_concept_rejects_traversal(tmp_path: Path) -> None:
    _make_base(tmp_path)
    with pytest.raises(ValueError):
        read_concept(tmp_path, "demo", "../../etc/passwd")


def test_read_concept_missing_raises(tmp_path: Path) -> None:
    _make_base(tmp_path)
    with pytest.raises(FileNotFoundError):
        read_concept(tmp_path, "demo", "behoerden/nope.md")


def test_search_concepts_matches_title_and_body(tmp_path: Path) -> None:
    _make_base(tmp_path)
    hits = {c.path for c in search_concepts(tmp_path, "demo", "bam")}
    assert "behoerden/bam.md" in hits
```

- [ ] **Step 2: Run to verify failure**

Run: `. .venv/bin/activate && pytest features/pipelines/local-pdf/tests/test_knowledge_reader.py -v`
Expected: FAIL — `ModuleNotFoundError: local_pdf.knowledge.reader`.

- [ ] **Step 3: Implement `reader.py`**

```python
# features/pipelines/local-pdf/src/local_pdf/knowledge/reader.py
"""Pure file-I/O over OKF knowledge bases. No network, no Azure, no openai —
import-boundary clean. A base is a directory of markdown concept files; the
file path (relative to the base dir) is the concept's identity."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_LINK_RE = re.compile(r"\[([^\]]+)\]\((/[^)]+\.md)\)")


@dataclass(frozen=True)
class BaseSummary:
    name: str
    title: str
    concept_count: int


@dataclass(frozen=True)
class ConceptSummary:
    path: str
    type: str
    title: str
    tags: list[str]


@dataclass(frozen=True)
class ConceptLink:
    text: str
    path: str
    resolved: bool


@dataclass(frozen=True)
class Concept:
    path: str
    type: str
    title: str
    description: str
    timestamp: str
    tags: list[str]
    body: str
    links: list[ConceptLink]
    malformed: bool


def _base_dir(root: Path, base: str) -> Path:
    safe = base.strip("/")
    if "/" in safe or safe in ("", ".", ".."):
        raise ValueError(f"invalid base: {base!r}")
    return root / safe


def _safe_concept_path(base_dir: Path, path: str) -> Path:
    rel = path.lstrip("/")
    target = (base_dir / rel).resolve()
    base_resolved = base_dir.resolve()
    if target != base_resolved and base_resolved not in target.parents:
        raise ValueError(f"path escapes base: {path!r}")
    return target


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return {}, text
    if not isinstance(fm, dict):
        return {}, text
    return fm, parts[2].lstrip("\n")


def _as_tags(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str) and value:
        return [value]
    return []


def _extract_links(base_dir: Path, body: str) -> list[ConceptLink]:
    links: list[ConceptLink] = []
    seen: set[str] = set()
    for text, raw in _LINK_RE.findall(body):
        norm = raw.lstrip("/")
        key = f"{text}|{norm}"
        if key in seen:
            continue
        seen.add(key)
        resolved = (base_dir / norm).is_file()
        links.append(ConceptLink(text=text, path=norm, resolved=resolved))
    return links


def _summary_from_file(base_dir: Path, file: Path) -> ConceptSummary:
    rel = file.relative_to(base_dir).as_posix()
    fm, _ = _parse_frontmatter(file.read_text(encoding="utf-8"))
    return ConceptSummary(
        path=rel,
        type=str(fm.get("type", "")),
        title=str(fm.get("title") or Path(rel).stem),
        tags=_as_tags(fm.get("tags")),
    )


def list_bases(root: Path) -> list[BaseSummary]:
    if not root.is_dir():
        return []
    out: list[BaseSummary] = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        mds = list(d.rglob("*.md"))
        title = d.name
        index = d / "index.md"
        if index.is_file():
            fm, _ = _parse_frontmatter(index.read_text(encoding="utf-8"))
            title = str(fm.get("title") or d.name)
        out.append(BaseSummary(name=d.name, title=title, concept_count=len(mds)))
    return out


def list_concepts(root: Path, base: str) -> list[ConceptSummary]:
    base_dir = _base_dir(root, base)
    if not base_dir.is_dir():
        raise FileNotFoundError(f"unknown base: {base}")
    files = sorted(base_dir.rglob("*.md"), key=lambda p: p.as_posix())
    return [_summary_from_file(base_dir, f) for f in files]


def read_concept(root: Path, base: str, path: str) -> Concept:
    base_dir = _base_dir(root, base)
    target = _safe_concept_path(base_dir, path)
    if not target.is_file():
        raise FileNotFoundError(f"unknown concept: {base}/{path}")
    rel = target.relative_to(base_dir).as_posix()
    fm, body = _parse_frontmatter(target.read_text(encoding="utf-8"))
    malformed = not fm or "type" not in fm
    return Concept(
        path=rel,
        type=str(fm.get("type", "")),
        title=str(fm.get("title") or Path(rel).stem),
        description=str(fm.get("description", "")),
        timestamp=str(fm.get("timestamp", "")),
        tags=_as_tags(fm.get("tags")),
        body=body,
        links=_extract_links(base_dir, body),
        malformed=malformed,
    )


def search_concepts(root: Path, base: str, query: str) -> list[ConceptSummary]:
    base_dir = _base_dir(root, base)
    if not base_dir.is_dir():
        raise FileNotFoundError(f"unknown base: {base}")
    q = query.casefold().strip()
    if not q:
        return list_concepts(root, base)
    out: list[ConceptSummary] = []
    for f in sorted(base_dir.rglob("*.md"), key=lambda p: p.as_posix()):
        text = f.read_text(encoding="utf-8")
        summary = _summary_from_file(base_dir, f)
        haystack = f"{summary.title}\n{' '.join(summary.tags)}\n{text}".casefold()
        if q in haystack:
            out.append(summary)
    return out
```

- [ ] **Step 4: Extend the package `__init__`**

```python
# features/pipelines/local-pdf/src/local_pdf/knowledge/__init__.py
"""OKF knowledge-base I/O (pure file reads) for the Wissen tab."""

from local_pdf.knowledge.docx_to_text import docx_to_text
from local_pdf.knowledge.reader import (
    BaseSummary,
    Concept,
    ConceptLink,
    ConceptSummary,
    list_bases,
    list_concepts,
    read_concept,
    search_concepts,
)

__all__ = [
    "docx_to_text",
    "BaseSummary",
    "Concept",
    "ConceptLink",
    "ConceptSummary",
    "list_bases",
    "list_concepts",
    "read_concept",
    "search_concepts",
]
```

- [ ] **Step 5: Run tests to verify pass**

Run: `. .venv/bin/activate && pytest features/pipelines/local-pdf/tests/test_knowledge_reader.py -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/knowledge/reader.py \
        features/pipelines/local-pdf/src/local_pdf/knowledge/__init__.py \
        features/pipelines/local-pdf/tests/test_knowledge_reader.py
git commit -m "feat(knowledge): pure-file-IO OKF reader (bases, concepts, links, search)"
```

---

## Task 3: OKF validator (structural gate) + validate the real base

**Files:**
- Create: `.../local_pdf/knowledge/validator.py`
- Modify: `.../local_pdf/knowledge/__init__.py` (export `Issue`, `validate_base`)
- Test: `features/pipelines/local-pdf/tests/test_knowledge_validator.py`

**Interfaces:**
- Consumes: `reader.list_concepts`, `reader.read_concept`.
- Produces: `@dataclass(frozen=True) Issue(path: str, kind: str, detail: str)` (kind ∈ `"missing_type"`, `"broken_link"`, `"orphan"`); `validate_base(root: Path, base: str) -> list[Issue]`.

- [ ] **Step 1: Write the failing tests**

```python
# features/pipelines/local-pdf/tests/test_knowledge_validator.py
from __future__ import annotations

from pathlib import Path

from local_pdf.knowledge.validator import validate_base


def _make_base(root: Path) -> None:
    b = root / "demo"
    (b / "x").mkdir(parents=True)
    (b / "index.md").write_text(
        "---\ntype: Index\n---\n[A](/x/a.md)\n", encoding="utf-8"
    )
    (b / "x" / "a.md").write_text(
        "---\ntype: Konzept\n---\nlink [tot](/x/missing.md)\n", encoding="utf-8"
    )
    (b / "x" / "orphan.md").write_text(
        "---\ntype: Begriff\n---\nNiemand verlinkt mich.\n", encoding="utf-8"
    )
    (b / "x" / "untyped.md").write_text("---\ntitle: Kein Typ\n---\nhi\n", encoding="utf-8")


def test_validate_flags_missing_type_broken_link_and_orphan(tmp_path: Path) -> None:
    _make_base(tmp_path)
    issues = validate_base(tmp_path, "demo")
    kinds = {(i.path, i.kind) for i in issues}
    assert ("x/untyped.md", "missing_type") in kinds
    assert ("x/a.md", "broken_link") in kinds
    assert ("x/orphan.md", "orphan") in kinds
    # a.md is linked from index → not an orphan
    assert ("x/a.md", "orphan") not in kinds
```

- [ ] **Step 2: Run to verify failure**

Run: `. .venv/bin/activate && pytest features/pipelines/local-pdf/tests/test_knowledge_validator.py -v`
Expected: FAIL — `ModuleNotFoundError: local_pdf.knowledge.validator`.

- [ ] **Step 3: Implement `validator.py`**

```python
# features/pipelines/local-pdf/src/local_pdf/knowledge/validator.py
"""Structural OKF gate: every concept has a `type`; every outgoing link
resolves; warn on concepts with no inbound links. This is the STRUCTURAL
gate — faithfulness to the source is a separate human review."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from local_pdf.knowledge.reader import list_concepts, read_concept


@dataclass(frozen=True)
class Issue:
    path: str
    kind: str
    detail: str


def validate_base(root: Path, base: str) -> list[Issue]:
    issues: list[Issue] = []
    summaries = list_concepts(root, base)
    inbound: set[str] = set()
    for s in summaries:
        concept = read_concept(root, base, s.path)
        if not concept.type:
            issues.append(Issue(s.path, "missing_type", "frontmatter has no `type`"))
        for link in concept.links:
            inbound.add(link.path)
            if not link.resolved:
                issues.append(
                    Issue(s.path, "broken_link", f"-> {link.path} ({link.text})")
                )
    for s in summaries:
        if s.path == "index.md":
            continue
        if s.path not in inbound:
            issues.append(Issue(s.path, "orphan", "no inbound links"))
    return issues
```

- [ ] **Step 4: Export from `__init__`**

Add to the imports and `__all__` in `.../knowledge/__init__.py`:

```python
from local_pdf.knowledge.validator import Issue, validate_base
```
and append `"Issue"`, `"validate_base"` to `__all__`.

- [ ] **Step 5: Run tests to verify pass**

Run: `. .venv/bin/activate && pytest features/pipelines/local-pdf/tests/test_knowledge_validator.py -v`
Expected: PASS.

- [ ] **Step 6: Run the structural gate on the REAL authored base**

Run:
```bash
. .venv/bin/activate && python -c "
from pathlib import Path
from local_pdf.knowledge.validator import validate_base
issues = validate_base(Path('data/knowledge'), 'bauartpruefung-lm')
for i in issues:
    print(i.kind, i.path, '-', i.detail)
print(f'total issues: {len(issues)}')
"
```
Expected: any `broken_link` / `missing_type` issues are real defects — fix the authored files (hand-edit or re-run Task 1 Step 10) until those two kinds are gone. `orphan` warnings are acceptable (note them; some concepts may be genuinely terminal).

- [ ] **Step 7: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/knowledge/validator.py \
        features/pipelines/local-pdf/src/local_pdf/knowledge/__init__.py \
        features/pipelines/local-pdf/tests/test_knowledge_validator.py
git commit -m "feat(knowledge): OKF structural validator (types, link resolution, orphans)"
```

---

## Task 4: Knowledge admin endpoint + config

**Files:**
- Create: `.../local_pdf/api/routers/admin/knowledge.py`
- Modify: `.../local_pdf/api/config.py` (add `knowledge_root`)
- Modify: `.../local_pdf/api/app.py` (import + include router)
- Test: `features/pipelines/local-pdf/tests/test_routers_admin_knowledge.py`

**Interfaces:**
- Consumes: reader API (Task 2); `request.app.state.config.knowledge_root`.
- Produces (consumed by frontend Task 5):
  - `GET /api/admin/knowledge/bases` → `[{name, title, concept_count}]`
  - `GET /api/admin/knowledge/bases/{base}/concepts` → `[{path, type, title, tags}]`
  - `GET /api/admin/knowledge/bases/{base}/concept?path=<rel>` → `{path, type, title, description, timestamp, tags, body, links: [{text, path, resolved}], malformed}`

- [ ] **Step 1: Write the failing endpoint tests**

```python
# features/pipelines/local-pdf/tests/test_routers_admin_knowledge.py
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOLDENS_API_TOKEN", "ADMIN")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(tmp_path / "raw"))
    kb = tmp_path / "kb"
    monkeypatch.setenv("KNOWLEDGE_ROOT", str(kb))
    base = kb / "bauartpruefung-lm" / "behoerden"
    base.mkdir(parents=True)
    (kb / "bauartpruefung-lm" / "index.md").write_text(
        "---\ntype: Index\ntitle: Bauartprüfung\n---\n[BAM](/behoerden/bam.md)\n",
        encoding="utf-8",
    )
    (base / "bam.md").write_text(
        "---\ntype: Behörde\ntitle: BAM\ntags: [behoerde]\n---\nSiehe [Index](/index.md).\n",
        encoding="utf-8",
    )
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def test_bases_requires_admin_token(client) -> None:
    assert client.get("/api/admin/knowledge/bases").status_code == 401


def test_list_bases(client) -> None:
    r = client.get("/api/admin/knowledge/bases", headers={"X-Auth-Token": "ADMIN"})
    assert r.status_code == 200
    body = r.json()
    assert body[0]["name"] == "bauartpruefung-lm"
    assert body[0]["title"] == "Bauartprüfung"
    assert body[0]["concept_count"] == 2


def test_list_concepts(client) -> None:
    r = client.get(
        "/api/admin/knowledge/bases/bauartpruefung-lm/concepts",
        headers={"X-Auth-Token": "ADMIN"},
    )
    paths = {c["path"]: c for c in r.json()}
    assert paths["behoerden/bam.md"]["type"] == "Behörde"


def test_get_concept_with_links(client) -> None:
    r = client.get(
        "/api/admin/knowledge/bases/bauartpruefung-lm/concept",
        params={"path": "behoerden/bam.md"},
        headers={"X-Auth-Token": "ADMIN"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "Behörde"
    assert body["links"][0]["path"] == "index.md"
    assert body["links"][0]["resolved"] is True


def test_get_concept_missing_is_404(client) -> None:
    r = client.get(
        "/api/admin/knowledge/bases/bauartpruefung-lm/concept",
        params={"path": "behoerden/nope.md"},
        headers={"X-Auth-Token": "ADMIN"},
    )
    assert r.status_code == 404


def test_get_concept_traversal_is_400(client) -> None:
    r = client.get(
        "/api/admin/knowledge/bases/bauartpruefung-lm/concept",
        params={"path": "../../secret"},
        headers={"X-Auth-Token": "ADMIN"},
    )
    assert r.status_code == 400
```

- [ ] **Step 2: Run to verify failure**

Run: `. .venv/bin/activate && pytest features/pipelines/local-pdf/tests/test_routers_admin_knowledge.py -v`
Expected: FAIL — 404s (router not registered) / import error.

- [ ] **Step 3: Add the `knowledge_root` config field**

In `features/pipelines/local-pdf/src/local_pdf/api/config.py`, add a field next to `data_root` (line ~21):

```python
    knowledge_root: Path = Field(
        default=Path("data/knowledge"), validation_alias="KNOWLEDGE_ROOT"
    )
```

- [ ] **Step 4: Implement the router**

```python
# features/pipelines/local-pdf/src/local_pdf/api/routers/admin/knowledge.py
"""Read-only OKF knowledge endpoints. Mounted under /api/admin/ so the ASGI
auth middleware gates them. Pure file reads via local_pdf.knowledge — no Azure,
no openai (import-boundary clean). FileNotFoundError -> 404 and ValueError ->
400 are handled by the app-level exception handlers in app.py."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request

from local_pdf.knowledge import (
    list_bases,
    list_concepts,
    read_concept,
)

router = APIRouter()


@router.get("/api/admin/knowledge/bases")
async def get_bases(request: Request) -> list[dict]:
    root = request.app.state.config.knowledge_root
    return [asdict(b) for b in list_bases(root)]


@router.get("/api/admin/knowledge/bases/{base}/concepts")
async def get_concepts(base: str, request: Request) -> list[dict]:
    root = request.app.state.config.knowledge_root
    return [asdict(c) for c in list_concepts(root, base)]


@router.get("/api/admin/knowledge/bases/{base}/concept")
async def get_concept(base: str, path: str, request: Request) -> dict:
    root = request.app.state.config.knowledge_root
    return asdict(read_concept(root, base, path))
```

- [ ] **Step 5: Register the router in `app.py`**

Add the import alongside the other admin router imports (after the `agent` import, ~line 95):

```python
    from local_pdf.api.routers.admin.knowledge import router as knowledge_router
```

Add the include alongside the others (after `app.include_router(agent_router)`, ~line 126):

```python
    app.include_router(knowledge_router)
```

- [ ] **Step 6: Run tests to verify pass**

Run: `. .venv/bin/activate && pytest features/pipelines/local-pdf/tests/test_routers_admin_knowledge.py -v`
Expected: PASS (6 tests).

- [ ] **Step 7: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/api/routers/admin/knowledge.py \
        features/pipelines/local-pdf/src/local_pdf/api/config.py \
        features/pipelines/local-pdf/src/local_pdf/api/app.py \
        features/pipelines/local-pdf/tests/test_routers_admin_knowledge.py
git commit -m "feat(knowledge): read-only /api/admin/knowledge endpoints + KNOWLEDGE_ROOT config"
```

---

## Task 5: Wissen tab — frontend viewer

**Files:**
- Create: `frontend/src/admin/api/knowledge.ts`
- Create: `frontend/src/admin/routes/Knowledge.tsx`
- Modify: `frontend/src/shared/icons/index.ts` (export `Library`)
- Modify: `frontend/src/shell/AdminShell.tsx` (nav entry + import)
- Modify: `frontend/src/App.tsx` (import + route)
- Test: `frontend/src/admin/routes/__tests__/Knowledge.test.tsx`

**Interfaces:**
- Consumes: endpoint (Task 4); `apiFetch`/`apiBase` (`../api/adminClient`); `useAuth` (`../../auth/useAuth`).
- Produces: `Knowledge` route component (`token?` prop override for tests); `listBases`/`listConcepts`/`getConcept` typed fetchers.

- [ ] **Step 1: Write the typed API module**

```ts
// frontend/src/admin/api/knowledge.ts
import { apiBase, apiFetch } from "./adminClient";

export interface BaseSummary { name: string; title: string; concept_count: number }
export interface ConceptSummary { path: string; type: string; title: string; tags: string[] }
export interface ConceptLink { text: string; path: string; resolved: boolean }
export interface Concept {
  path: string; type: string; title: string; description: string;
  timestamp: string; tags: string[]; body: string;
  links: ConceptLink[]; malformed: boolean;
}

export async function listBases(token: string): Promise<BaseSummary[]> {
  return (await apiFetch(`${apiBase()}/api/admin/knowledge/bases`, token)).json();
}

export async function listConcepts(base: string, token: string): Promise<ConceptSummary[]> {
  const b = encodeURIComponent(base);
  return (await apiFetch(`${apiBase()}/api/admin/knowledge/bases/${b}/concepts`, token)).json();
}

export async function getConcept(base: string, path: string, token: string): Promise<Concept> {
  const b = encodeURIComponent(base);
  const p = encodeURIComponent(path);
  return (await apiFetch(`${apiBase()}/api/admin/knowledge/bases/${b}/concept?path=${p}`, token)).json();
}
```

- [ ] **Step 2: Write the failing component test**

```tsx
// frontend/src/admin/routes/__tests__/Knowledge.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { Knowledge } from "../Knowledge";

vi.mock("../../../auth/useAuth", () => ({ useAuth: () => ({ token: "tok" }) }));

const bam = {
  path: "behoerden/bam.md", type: "Behörde", title: "BAM",
  description: "", timestamp: "", tags: ["behoerde"],
  body: "Die BAM prüft.", malformed: false,
  links: [{ text: "Nachweiskonzept", path: "konzepte/nachweiskonzept.md", resolved: true }],
};
const nachweis = {
  path: "konzepte/nachweiskonzept.md", type: "Konzept", title: "Nachweiskonzept",
  description: "", timestamp: "", tags: [], body: "Basis der Analysen.",
  malformed: false, links: [],
};

const server = setupServer(
  http.get("*/api/admin/knowledge/bases", () =>
    HttpResponse.json([{ name: "bauartpruefung-lm", title: "Bauartprüfung", concept_count: 2 }])
  ),
  http.get("*/api/admin/knowledge/bases/:base/concepts", () =>
    HttpResponse.json([
      { path: bam.path, type: bam.type, title: bam.title, tags: bam.tags },
      { path: nachweis.path, type: nachweis.type, title: nachweis.title, tags: [] },
    ])
  ),
  http.get("*/api/admin/knowledge/bases/:base/concept", ({ request }) => {
    const p = new URL(request.url).searchParams.get("path");
    return HttpResponse.json(p === nachweis.path ? nachweis : bam);
  }),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Knowledge token="tok" />
    </QueryClientProvider>
  );
}

describe("Wissen (Knowledge) tab", () => {
  it("lists concepts and walks an outgoing link", async () => {
    renderPage();
    // concept list renders
    await waitFor(() => expect(screen.getByText("BAM")).toBeInTheDocument());
    // open BAM
    await userEvent.click(screen.getByText("BAM"));
    await waitFor(() => expect(screen.getByText("Die BAM prüft.")).toBeInTheDocument());
    // walk the graph: click the outgoing link → target concept loads
    await userEvent.click(screen.getByRole("button", { name: /Nachweiskonzept/ }));
    await waitFor(() => expect(screen.getByText("Basis der Analysen.")).toBeInTheDocument());
  });
});
```

- [ ] **Step 3: Run to verify failure**

Run: `cd frontend && npx vitest run src/admin/routes/__tests__/Knowledge.test.tsx`
Expected: FAIL — cannot resolve `../Knowledge`.

- [ ] **Step 4: Implement `Knowledge.tsx`**

```tsx
// frontend/src/admin/routes/Knowledge.tsx
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../auth/useAuth";
import { getConcept, listBases, listConcepts } from "../api/knowledge";

interface Props {
  /** Override token for testing; production reads it from useAuth(). */
  token?: string;
}

export function Knowledge({ token: tokenProp }: Props = {}): JSX.Element {
  const { token: authToken } = useAuth();
  const token = tokenProp ?? authToken ?? "";

  const [base, setBase] = useState<string | null>(null);
  const [path, setPath] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const basesQ = useQuery({
    queryKey: ["kb-bases"],
    queryFn: () => listBases(token),
    staleTime: 60_000,
  });
  const conceptsQ = useQuery({
    queryKey: ["kb-concepts", base],
    queryFn: () => listConcepts(base as string, token),
    enabled: !!base,
  });
  const conceptQ = useQuery({
    queryKey: ["kb-concept", base, path],
    queryFn: () => getConcept(base as string, path as string, token),
    enabled: !!base && !!path,
  });

  // auto-select the first base
  useEffect(() => {
    if (!base && basesQ.data && basesQ.data.length > 0) setBase(basesQ.data[0].name);
  }, [base, basesQ.data]);

  if (!token) return <div className="p-8 text-slate-500">Bitte anmelden.</div>;

  const concepts = (conceptsQ.data ?? []).filter((c) => {
    const q = filter.trim().toLowerCase();
    if (!q) return true;
    return (
      c.title.toLowerCase().includes(q) ||
      c.type.toLowerCase().includes(q) ||
      c.tags.some((t) => t.toLowerCase().includes(q))
    );
  });

  const grouped = new Map<string, typeof concepts>();
  for (const c of concepts) {
    const key = c.type || "(ohne Typ)";
    (grouped.get(key) ?? grouped.set(key, []).get(key)!).push(c);
  }

  const c = conceptQ.data;

  return (
    <div className="h-full flex">
      {/* Left: base selector + concept list */}
      <aside className="w-80 shrink-0 border-r border-slate-200 overflow-y-auto p-4">
        <select
          className="w-full mb-3 rounded border border-slate-300 px-2 py-1 text-sm"
          value={base ?? ""}
          onChange={(e) => { setBase(e.target.value); setPath(null); }}
        >
          {(basesQ.data ?? []).map((b) => (
            <option key={b.name} value={b.name}>{b.title} ({b.concept_count})</option>
          ))}
        </select>
        <input
          className="w-full mb-3 rounded border border-slate-300 px-2 py-1 text-sm"
          placeholder="Filtern…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        {[...grouped.entries()].map(([type, items]) => (
          <div key={type} className="mb-3">
            <div className="text-xs font-semibold uppercase text-slate-400 mb-1">{type}</div>
            <ul>
              {items.map((it) => (
                <li key={it.path}>
                  <button
                    className={`block w-full text-left px-2 py-1 rounded text-sm hover:bg-slate-100 ${
                      it.path === path ? "bg-cyan-50 text-bam-cyan" : ""
                    }`}
                    onClick={() => setPath(it.path)}
                  >
                    {it.title}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </aside>

      {/* Right: concept view */}
      <main className="flex-1 overflow-y-auto p-6">
        {!c && <div className="text-slate-400">Konzept auswählen.</div>}
        {c && (
          <article className="max-w-3xl">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs px-2 py-0.5 rounded bg-cyan-50 text-bam-cyan border border-bam-cyan">
                {c.type || "(ohne Typ)"}
              </span>
              {c.malformed && (
                <span className="text-xs px-2 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-300">
                  Frontmatter fehlerhaft
                </span>
              )}
              {c.tags.map((t) => (
                <span key={t} className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-500">{t}</span>
              ))}
            </div>
            <h1 className="text-2xl font-semibold mb-1">{c.title}</h1>
            {c.description && <p className="text-slate-500 mb-4">{c.description}</p>}
            <pre className="whitespace-pre-wrap text-sm text-slate-800 mb-6 font-sans">{c.body}</pre>
            {c.links.length > 0 && (
              <section>
                <h2 className="text-sm font-semibold text-slate-400 uppercase mb-2">Verweise</h2>
                <ul className="space-y-1">
                  {c.links.map((ln) => (
                    <li key={`${ln.text}|${ln.path}`}>
                      <button
                        disabled={!ln.resolved}
                        className={`text-sm ${
                          ln.resolved
                            ? "text-bam-cyan hover:underline"
                            : "text-slate-400 line-through cursor-not-allowed"
                        }`}
                        onClick={() => ln.resolved && setPath(ln.path)}
                      >
                        {ln.text}
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </article>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 5: Export the `Library` icon**

In `frontend/src/shared/icons/index.ts`, add `Library` to the `lucide-react` export list (e.g. on the `FileSearch, Sparkles, Workflow,` line):

```ts
  FileSearch, Sparkles, Workflow, Library,
```

- [ ] **Step 6: Add the `Wissen` nav entry**

In `frontend/src/shell/AdminShell.tsx`:
- Extend the icon import (line 8): add `Library`:
  ```ts
  import { Inbox, Users, Cpu, BarChart3, Building2, Library } from "../shared/icons";
  ```
- Add a `RailItem` to `ADMIN_NAV` (after the `dashboard`/Übersicht entry):
  ```ts
  { to: "/admin/knowledge", match: "/admin/knowledge", label: "Wissen", icon: Library },
  ```

- [ ] **Step 7: Register the route**

In `frontend/src/App.tsx`:
- Add the import near the other route imports (after `Agent`):
  ```ts
  import { Knowledge } from "./admin/routes/Knowledge";
  ```
- Add the route next to the other global routes (after `<Route path="dashboard" … />`):
  ```tsx
  <Route path="knowledge" element={<Knowledge />} />
  ```

- [ ] **Step 8: Run the component test to verify pass**

Run: `cd frontend && npx vitest run src/admin/routes/__tests__/Knowledge.test.tsx`
Expected: PASS — concept list renders, BAM opens, clicking the "Nachweiskonzept" Verweis loads the target.

- [ ] **Step 9: Typecheck + lint the frontend**

Run: `cd frontend && npx tsc --noEmit && npx eslint src/admin/routes/Knowledge.tsx src/admin/api/knowledge.ts`
Expected: no errors. (If `tsc`/`eslint` scripts differ, use the repo's `npm run` equivalents.)

- [ ] **Step 10: Commit**

```bash
git add frontend/src/admin/api/knowledge.ts \
        frontend/src/admin/routes/Knowledge.tsx \
        frontend/src/admin/routes/__tests__/Knowledge.test.tsx \
        frontend/src/shared/icons/index.ts \
        frontend/src/shell/AdminShell.tsx \
        frontend/src/App.tsx
git commit -m "feat(knowledge): Wissen tab — three-pane OKF viewer with graph navigation"
```

---

## Task 6: Verify non-invasiveness, savepoint, final review

**Files:** none (verification only).

- [ ] **Step 1: Confirm protected paths are untouched**

Run:
```bash
cd /home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft
git diff --stat pre-knowledge-okf -- \
  features/pipelines/local-pdf/src/local_pdf/agent/build.py \
  features/pipelines/local-pdf/src/local_pdf/agent/tools.py \
  features/pipelines/local-pdf/src/local_pdf/agent/prompts.py \
  features/pipelines/local-pdf/src/local_pdf/agent/verify_prompts.py \
  features/pipelines/local-pdf/src/local_pdf/api/routers/admin/agent.py \
  features/pipelines/microsoft/
```
Expected: **no output** (zero changes to protected paths).

- [ ] **Step 2: Full backend knowledge test sweep**

Run: `. .venv/bin/activate && pytest features/pipelines/local-pdf/tests/test_knowledge_reader.py features/pipelines/local-pdf/tests/test_knowledge_validator.py features/pipelines/local-pdf/tests/test_routers_admin_knowledge.py features/pipelines/local-pdf/tests/test_knowledge_docx.py -v`
Expected: all PASS.

- [ ] **Step 3: Confirm the produced base is gitignored (not staged)**

Run: `git status --porcelain data/knowledge/ ; git check-ignore data/knowledge/bauartpruefung-lm/index.md`
Expected: no `data/knowledge` entries in status; `check-ignore` prints the path (confirming ignored).

- [ ] **Step 4: Savepoint tag**

```bash
git tag knowledge-okf-view-v1
git tag --list 'knowledge-okf-*' 'pre-knowledge-okf'
```
Expected: `pre-knowledge-okf` and `knowledge-okf-view-v1` listed.

- [ ] **Step 5: Final whole-feature code review**

Dispatch the final code reviewer over the diff `pre-knowledge-okf..HEAD` (per subagent-driven-development). Confirm: import-boundary clean, no protected-path edits, tests cover reader/validator/endpoint/viewer + the click-through graph walk.

---

## Self-Review (filled by plan author)

**Spec coverage:** A1 storage → Task 4 config + Task 1 base dir. A2 schema → `OKF_EXTRACTION` (Task 1). A3 docx_to_text → Task 1. A4 authoring (one-off) + A4-review semantic gate → Task 1. A5 reader (+ link normalization) → Task 2. A6 validator → Task 3. A7 endpoint → Task 4. A8 Wissen tab (global rail, three-pane, click-through) → Task 5. Non-invasive guarantees + savepoints → Tasks 1/6. Testing strategy → tests in Tasks 2–5. Out-of-scope items not built. Part B not in this plan (deferred by design).

**Placeholder scan:** none — every code step has complete code; the only `<…>` is the explanatory faithfulness-review note in Task 1 Step 11 (a human action, not code).

**Type consistency:** `Concept`/`ConceptSummary`/`ConceptLink`/`BaseSummary` field names match across reader → validator → endpoint (`asdict`) → frontend interfaces → msw fixtures. Link contract: reader emits `link.path` (base-relative, no leading slash) → endpoint passes through → frontend uses it verbatim as `?path=` and as the next `getConcept` arg. `knowledge_root` config alias `KNOWLEDGE_ROOT` matches the endpoint read and the test fixture env.
