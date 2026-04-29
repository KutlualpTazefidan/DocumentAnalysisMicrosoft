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
