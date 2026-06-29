from __future__ import annotations

from typing import TYPE_CHECKING

from local_pdf.knowledge.validator import validate_base

if TYPE_CHECKING:
    from pathlib import Path


def _make_base(root: Path) -> None:
    b = root / "demo"
    (b / "x").mkdir(parents=True)
    (b / "index.md").write_text("---\ntype: Index\n---\n[A](/x/a.md)\n", encoding="utf-8")
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
