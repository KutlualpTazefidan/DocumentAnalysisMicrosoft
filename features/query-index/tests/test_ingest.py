"""Tests for query_index.ingest.populate_index()."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path


def test_populate_index_reads_files_and_uploads(env_vars: dict[str, str], tmp_path: Path) -> None:
    from query_index.config import Config
    from query_index.ingest import populate_index

    (tmp_path / "doc1.txt").write_text("First chunk body.")
    (tmp_path / "doc2.txt").write_text("Second chunk body.")

    mock_search_client = MagicMock()
    cfg = Config.from_env()
    with (
        patch("query_index.ingest.get_search_client", return_value=mock_search_client),
        patch("query_index.ingest.get_embedding", return_value=[0.0] * 3072),
    ):
        populate_index(tmp_path, cfg)

    mock_search_client.upload_documents.assert_called_once()
    uploaded = (
        mock_search_client.upload_documents.call_args.kwargs.get("documents")
        or mock_search_client.upload_documents.call_args.args[0]
    )
    assert len(uploaded) == 2
    chunk_ids = {d["chunk_id"] for d in uploaded}
    assert chunk_ids == {"doc1", "doc2"}


def test_populate_index_does_not_log_chunk_text(
    env_vars: dict[str, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from query_index.config import Config
    from query_index.ingest import populate_index

    secret = "SECRET-CHUNK-PAYLOAD-DO-NOT-LOG"
    (tmp_path / "doc1.txt").write_text(secret)

    mock_search_client = MagicMock()
    cfg = Config.from_env()
    with (
        patch("query_index.ingest.get_search_client", return_value=mock_search_client),
        patch("query_index.ingest.get_embedding", return_value=[0.0] * 3072),
    ):
        populate_index(tmp_path, cfg)

    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


def test_populate_index_raises_when_source_missing(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    from query_index.config import Config
    from query_index.ingest import populate_index

    cfg = Config.from_env()
    missing = tmp_path / "does-not-exist"
    with patch("query_index.ingest.get_search_client") as mock_get_search:
        with pytest.raises(FileNotFoundError):
            populate_index(missing, cfg)
        mock_get_search.assert_not_called()
