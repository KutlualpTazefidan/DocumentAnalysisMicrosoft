"""Structural OKF gate: every concept has a `type`; every outgoing link
resolves; warn on concepts with no inbound links. This is the STRUCTURAL
gate — faithfulness to the source is a separate human review."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from local_pdf.knowledge.reader import list_concepts, read_concept

if TYPE_CHECKING:
    from pathlib import Path


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
                issues.append(Issue(s.path, "broken_link", f"-> {link.path} ({link.text})"))
    for s in summaries:
        if s.path == "index.md":
            continue
        if s.path not in inbound:
            issues.append(Issue(s.path, "orphan", "no inbound links"))
    return issues
