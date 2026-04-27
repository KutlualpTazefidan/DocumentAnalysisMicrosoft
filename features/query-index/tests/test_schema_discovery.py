"""Tests for query_index.schema_discovery.print_index_schema()."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    import pytest


def test_print_index_schema_calls_get_index_with_name(
    env_vars: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    from query_index.config import Config
    from query_index.schema_discovery import print_index_schema

    mock_index_client = MagicMock()
    mock_field = MagicMock()
    mock_field.name = "chunk_id"
    mock_field.type = "Edm.String"
    mock_field.searchable = False
    mock_field.filterable = False
    mock_field.retrievable = True
    mock_index_client.get_index.return_value = MagicMock(fields=[mock_field])

    cfg = Config.from_env()
    with patch(
        "query_index.schema_discovery.get_search_index_client",
        return_value=mock_index_client,
    ):
        print_index_schema("test-index", cfg)

    mock_index_client.get_index.assert_called_once_with("test-index")
    out = capsys.readouterr().out
    assert "chunk_id" in out
    assert "Edm.String" in out


def test_print_index_schema_handles_multiple_fields(
    env_vars: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    from query_index.config import Config
    from query_index.schema_discovery import print_index_schema

    mock_index_client = MagicMock()
    fields = []
    for name, ftype in [("chunk_id", "Edm.String"), ("text_vector", "Collection(Edm.Single)")]:
        f = MagicMock()
        f.name = name
        f.type = ftype
        f.searchable = False
        f.filterable = False
        f.retrievable = True
        fields.append(f)
    mock_index_client.get_index.return_value = MagicMock(fields=fields)

    cfg = Config.from_env()
    with patch(
        "query_index.schema_discovery.get_search_index_client",
        return_value=mock_index_client,
    ):
        print_index_schema("test-index", cfg)

    out = capsys.readouterr().out
    assert "chunk_id" in out
    assert "text_vector" in out
    assert "Collection(Edm.Single)" in out
