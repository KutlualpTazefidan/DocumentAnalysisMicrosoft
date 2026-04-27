"""Tests for ingestion.analyze.analyze_pdf()."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path


def _fake_doc_intel_result() -> MagicMock:
    """Build a MagicMock that pretends to be the result of poller.result()."""
    result = MagicMock()
    result.as_dict.return_value = {
        "apiVersion": "2024-11-30",
        "modelId": "prebuilt-layout",
        "pages": [{"pageNumber": 1}, {"pageNumber": 2}],
        "paragraphs": [
            {"content": "Title", "role": "title"},
            {"content": "Body", "role": None},
        ],
    }
    return result


def test_analyze_pdf_writes_wrapped_json_to_auto_derived_path(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    from ingestion.analyze import analyze_pdf

    pdf = tmp_path / "Some Doc Name.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    fake_poller = MagicMock()
    fake_poller.result.return_value = _fake_doc_intel_result()
    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = fake_poller

    monkeypatch_outputs = tmp_path / "outputs-root"
    with (
        patch("ingestion.analyze.get_doc_intel_client", return_value=mock_client),
        patch(
            "ingestion.analyze._outputs_root",
            return_value=monkeypatch_outputs,
        ),
        patch(
            "ingestion.analyze.now_compact_utc",
            return_value="20260427T143000",
        ),
    ):
        out_path = analyze_pdf(pdf)

    expected_path = monkeypatch_outputs / "some-doc-name" / "analyze" / "20260427T143000.json"
    assert out_path == expected_path
    assert out_path.exists()

    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["_ingestion_metadata"]["source_file"] == "Some Doc Name.pdf"
    assert written["_ingestion_metadata"]["slug"] == "some-doc-name"
    assert written["_ingestion_metadata"]["timestamp_utc"] == "20260427T143000"
    assert written["analyzeResult"]["modelId"] == "prebuilt-layout"


def test_analyze_pdf_uses_explicit_out_path_when_given(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    from ingestion.analyze import analyze_pdf

    pdf = tmp_path / "foo.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    explicit_out = tmp_path / "custom_dir" / "result.json"

    fake_poller = MagicMock()
    fake_poller.result.return_value = _fake_doc_intel_result()
    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = fake_poller

    with patch("ingestion.analyze.get_doc_intel_client", return_value=mock_client):
        out_path = analyze_pdf(pdf, out_path=explicit_out)

    assert out_path == explicit_out
    assert out_path.exists()


def test_analyze_pdf_calls_doc_intel_with_prebuilt_layout(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    from ingestion.analyze import analyze_pdf

    pdf = tmp_path / "foo.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    fake_poller = MagicMock()
    fake_poller.result.return_value = _fake_doc_intel_result()
    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = fake_poller

    with patch("ingestion.analyze.get_doc_intel_client", return_value=mock_client):
        analyze_pdf(pdf, out_path=tmp_path / "out.json")

    mock_client.begin_analyze_document.assert_called_once()
    _, kwargs = mock_client.begin_analyze_document.call_args
    assert kwargs["model_id"] == "prebuilt-layout"
    assert kwargs["content_type"] == "application/pdf"


def test_analyze_pdf_does_not_log_chunk_or_paragraph_content(
    env_vars: dict[str, str], tmp_path: Path, capsys
) -> None:
    """Metadata-only logging discipline: no chunk/paragraph text in stdout/stderr."""
    from ingestion.analyze import analyze_pdf

    pdf = tmp_path / "foo.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    secret = "SECRET-PARAGRAPH-CONTENT"
    fake_result = MagicMock()
    fake_result.as_dict.return_value = {
        "apiVersion": "2024-11-30",
        "modelId": "prebuilt-layout",
        "pages": [{"pageNumber": 1}],
        "paragraphs": [{"content": secret, "role": None}],
    }
    fake_poller = MagicMock()
    fake_poller.result.return_value = fake_result
    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = fake_poller

    with patch("ingestion.analyze.get_doc_intel_client", return_value=mock_client):
        analyze_pdf(pdf, out_path=tmp_path / "out.json")

    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


def test_outputs_root_returns_path_under_repo_root() -> None:
    """_outputs_root should resolve to <repo_root>/outputs via the pyproject.toml walk."""
    from ingestion.analyze import _outputs_root

    root = _outputs_root()
    # The repo root contains both pyproject.toml and features/; outputs lives there.
    assert root.name == "outputs"
    assert (root.parent / "pyproject.toml").is_file()
    assert (root.parent / "features").is_dir()


def test_analyze_pdf_accepts_explicit_cfg(env_vars: dict[str, str], tmp_path: Path) -> None:
    """Passing cfg explicitly skips the from_env() branch."""
    from ingestion.analyze import analyze_pdf
    from ingestion.config import IngestionConfig

    pdf = tmp_path / "foo.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    fake_poller = MagicMock()
    fake_poller.result.return_value = _fake_doc_intel_result()
    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = fake_poller

    cfg = IngestionConfig.from_env()

    with patch("ingestion.analyze.get_doc_intel_client", return_value=mock_client):
        out_path = analyze_pdf(pdf, out_path=tmp_path / "out.json", cfg=cfg)

    assert out_path.exists()
