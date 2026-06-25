"""Pure file-I/O over OKF knowledge bases. No network, no Azure, no openai —
import-boundary clean. A base is a directory of markdown concept files; the
file path (relative to the base dir) is the concept's identity."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml  # type: ignore[import-untyped]  # types-PyYAML stubs not in pre-commit env

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
    rel = target.relative_to(base_dir.resolve()).as_posix()
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
