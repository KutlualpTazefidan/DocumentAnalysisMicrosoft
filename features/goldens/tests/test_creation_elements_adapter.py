"""Tests for goldens.creation.elements.adapter."""

from __future__ import annotations

import dataclasses

import pytest
from goldens.creation.elements.adapter import DocumentElement, ElementsLoader


def test_document_element_basic_construction() -> None:
    el = DocumentElement(
        element_id="p3-a1b2c3d4",
        page_number=3,
        element_type="paragraph",
        content="Hello world",
    )
    assert el.element_id == "p3-a1b2c3d4"
    assert el.page_number == 3
    assert el.element_type == "paragraph"
    assert el.content == "Hello world"
    assert el.table_dims is None
    assert el.caption is None


def test_document_element_is_frozen() -> None:
    el = DocumentElement(
        element_id="p1-deadbeef", page_number=1, element_type="paragraph", content="x"
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        el.element_id = "other"  # type: ignore[misc]


def test_elements_loader_protocol_runtime_checkable() -> None:
    class _Stub:
        def elements(self) -> list[DocumentElement]:
            return []

    assert isinstance(_Stub(), ElementsLoader)
