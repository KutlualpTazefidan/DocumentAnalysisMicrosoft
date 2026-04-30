"""DocumentElement dataclass + ElementsLoader Protocol — the boundary
between curate / synthetic generation and the underlying element source."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from goldens.schemas import ElementType


@dataclass(frozen=True)
class DocumentElement:
    """One structural element extracted from a source document.

    `element_id` format is `p{page}-{8-hex-of-sha256(content)}`,
    content-stable across re-runs of the document parser.
    """

    element_id: str
    page_number: int
    element_type: ElementType
    content: str
    table_dims: tuple[int, int] | None = None
    caption: str | None = None


@runtime_checkable
class ElementsLoader(Protocol):
    """Anything that can produce an ordered list of DocumentElements."""

    def elements(self) -> list[DocumentElement]: ...  # pragma: no cover
