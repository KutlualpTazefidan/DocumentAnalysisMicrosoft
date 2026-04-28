"""Tests for ingestion.upload.upload_chunks()."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path


def _write_embedded_jsonl(path, source_file: str = "x.pdf", n: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for i in range(n):
            f.write(
                json.dumps(
                    {
                        "chunk_id": f"slug-{i + 1:03d}",
                        "title": "T",
                        "section_heading": f"Section {i + 1}",
                        "chunk": f"body {i + 1}",
                        "source_file": source_file,
                        "vector": [0.0] * 3072,
                    }
                )
                + "\n"
            )


def _index_missing_response() -> Exception:
    """Build the kind of exception SearchIndexClient raises on missing index."""
    from azure.core.exceptions import ResourceNotFoundError

    return ResourceNotFoundError("not found")


def test_upload_chunks_creates_index_when_missing(env_vars: dict[str, str], tmp_path: Path) -> None:
    from ingestion.upload import upload_chunks

    in_path = tmp_path / "embedded.jsonl"
    _write_embedded_jsonl(in_path)

    mock_index_client = MagicMock()
    mock_index_client.get_index.side_effect = _index_missing_response()
    mock_search_client = MagicMock()
    mock_search_client.search.return_value = []
    mock_search_client.upload_documents.return_value = []

    with (
        patch("ingestion.upload.get_search_index_client", return_value=mock_index_client),
        patch("ingestion.upload.get_search_client", return_value=mock_search_client),
    ):
        upload_chunks(in_path)

    mock_index_client.create_index.assert_called_once()


def test_upload_chunks_deletes_existing_chunks_for_same_source_file(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    from ingestion.upload import upload_chunks

    in_path = tmp_path / "embedded.jsonl"
    _write_embedded_jsonl(in_path, source_file="my-file.pdf")

    mock_index_client = MagicMock()
    mock_index_client.get_index.return_value = MagicMock()  # index exists
    mock_search_client = MagicMock()
    mock_search_client.search.return_value = [
        {"id": "old-1"},
        {"id": "old-2"},
    ]
    mock_search_client.upload_documents.return_value = []

    with (
        patch("ingestion.upload.get_search_index_client", return_value=mock_index_client),
        patch("ingestion.upload.get_search_client", return_value=mock_search_client),
    ):
        upload_chunks(in_path)

    # Search query must filter on source_file
    search_kwargs = mock_search_client.search.call_args.kwargs
    assert "source_file eq 'my-file.pdf'" in search_kwargs["filter"]

    # delete_documents called with the IDs from the search
    mock_search_client.delete_documents.assert_called_once()
    deleted_arg = (
        mock_search_client.delete_documents.call_args.kwargs.get("documents")
        or mock_search_client.delete_documents.call_args.args[0]
    )
    assert deleted_arg == [{"id": "old-1"}, {"id": "old-2"}]


def test_upload_chunks_does_not_delete_when_no_existing_chunks(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    from ingestion.upload import upload_chunks

    in_path = tmp_path / "embedded.jsonl"
    _write_embedded_jsonl(in_path)

    mock_index_client = MagicMock()
    mock_search_client = MagicMock()
    mock_search_client.search.return_value = []
    mock_search_client.upload_documents.return_value = []

    with (
        patch("ingestion.upload.get_search_index_client", return_value=mock_index_client),
        patch("ingestion.upload.get_search_client", return_value=mock_search_client),
    ):
        upload_chunks(in_path)

    mock_search_client.delete_documents.assert_not_called()


def test_upload_chunks_uploads_each_chunk_as_a_document(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    from ingestion.upload import upload_chunks

    in_path = tmp_path / "embedded.jsonl"
    _write_embedded_jsonl(in_path, n=5)

    mock_index_client = MagicMock()
    mock_search_client = MagicMock()
    mock_search_client.search.return_value = []
    mock_search_client.upload_documents.return_value = []

    with (
        patch("ingestion.upload.get_search_index_client", return_value=mock_index_client),
        patch("ingestion.upload.get_search_client", return_value=mock_search_client),
    ):
        n_uploaded = upload_chunks(in_path)

    assert n_uploaded == 5
    docs = (
        mock_search_client.upload_documents.call_args.kwargs.get("documents")
        or mock_search_client.upload_documents.call_args.args[0]
    )
    assert len(docs) == 5
    for doc in docs:
        assert "id" in doc
        assert "chunk" in doc
        assert "chunkVector" in doc
        assert "source_file" in doc


def test_upload_chunks_force_recreate_drops_index(env_vars: dict[str, str], tmp_path: Path) -> None:
    from ingestion.upload import upload_chunks

    in_path = tmp_path / "embedded.jsonl"
    _write_embedded_jsonl(in_path)

    mock_index_client = MagicMock()
    mock_search_client = MagicMock()
    mock_search_client.search.return_value = []
    mock_search_client.upload_documents.return_value = []

    with (
        patch("ingestion.upload.get_search_index_client", return_value=mock_index_client),
        patch("ingestion.upload.get_search_client", return_value=mock_search_client),
    ):
        upload_chunks(in_path, force_recreate=True)

    mock_index_client.delete_index.assert_called_once()
    mock_index_client.create_index.assert_called_once()
    mock_search_client.delete_documents.assert_not_called()


def test_upload_chunks_escapes_single_quotes_in_source_file(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    """Filenames with single quotes (e.g. O'Brien.pdf) must be OData-escaped."""
    from ingestion.upload import upload_chunks

    in_path = tmp_path / "embedded.jsonl"
    _write_embedded_jsonl(in_path, source_file="O'Brien.pdf")

    mock_index_client = MagicMock()
    mock_search_client = MagicMock()
    mock_search_client.search.return_value = []
    mock_search_client.upload_documents.return_value = []

    with (
        patch("ingestion.upload.get_search_index_client", return_value=mock_index_client),
        patch("ingestion.upload.get_search_client", return_value=mock_search_client),
    ):
        upload_chunks(in_path)

    filter_arg = mock_search_client.search.call_args.kwargs["filter"]
    assert "O''Brien.pdf" in filter_arg


def test_upload_chunks_returns_zero_when_input_empty(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    """Upload with an empty file returns 0; no uploads attempted."""
    from ingestion.upload import upload_chunks

    in_path = tmp_path / "empty.jsonl"
    in_path.write_text("")

    mock_index_client = MagicMock()
    mock_search_client = MagicMock()

    with (
        patch("ingestion.upload.get_search_index_client", return_value=mock_index_client),
        patch("ingestion.upload.get_search_client", return_value=mock_search_client),
    ):
        n = upload_chunks(in_path)

    assert n == 0
    mock_search_client.upload_documents.assert_not_called()
