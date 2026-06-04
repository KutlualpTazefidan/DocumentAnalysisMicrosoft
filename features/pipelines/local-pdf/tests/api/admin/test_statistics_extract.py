"""Tests for /api/admin/statistics/extract/{slug}.

Live-scan C1 endpoint — every request walks ``mineru-out.json`` +
``segments.json`` on disk. See ``docs/superpowers/specs/
2026-06-03-statistics-and-voting-design.md`` for the V2 DuckDB trigger.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from pathlib import Path


def _make_client(tmp_path: Path, monkeypatch) -> TestClient:
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def _box(box_id: str, kind: str, page: int = 1) -> dict:
    """Minimal SegmentBox dict matching the real schema.

    Required: ``box_id`` (non-empty), ``page`` (>=1), ``bbox`` tuple,
    ``kind`` (BoxKind enum value), ``confidence`` in [0, 1].
    """
    return {
        "box_id": box_id,
        "page": page,
        "bbox": [0.0, 0.0, 100.0, 100.0],
        "kind": kind,
        "confidence": 0.9,
    }


def _seed_doc(root: Path, slug: str, mineru: dict, segments: dict) -> None:
    doc = root / slug
    doc.mkdir(parents=True, exist_ok=True)
    (doc / "mineru-out.json").write_text(json.dumps(mineru))
    (doc / "segments.json").write_text(json.dumps(segments))


AUTH = {"X-Auth-Token": "tok"}


def test_extract_stats_counts_diagnostics_and_register(tmp_path: Path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    cfg = client.app.state.config
    _seed_doc(
        cfg.data_root,
        "doc-a",
        mineru={
            "elements": [{"id": f"e{i}"} for i in range(10)],
            "diagnostics": [
                {"kind": "split"},
                {"kind": "no_decomposition"},
            ],
        },
        segments={
            "slug": "doc-a",
            "boxes": [
                _box("b1", "toc"),
                _box("b2", "paragraph"),
                _box("b3", "list_of_tables"),
                _box("b4", "paragraph"),
                _box("b5", "paragraph"),
            ],
        },
    )
    r = client.get("/api/admin/statistics/extract/doc-a", headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slug"] == "doc-a"
    assert body["diagnostics"] == {
        "split": 1,
        "no_decomposition": 1,
        "clean": 8,
        "total": 10,
    }
    assert body["register_boxes"] == 2
    assert body["total_boxes"] == 5
    assert body["register_rate"] == pytest.approx(0.4)


def test_extract_stats_zero_boxes_returns_null_rate(tmp_path: Path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    cfg = client.app.state.config
    _seed_doc(
        cfg.data_root,
        "empty",
        mineru={"elements": [], "diagnostics": []},
        segments={"slug": "empty", "boxes": []},
    )
    r = client.get("/api/admin/statistics/extract/empty", headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["register_rate"] is None


def test_extract_stats_404_when_doc_missing(tmp_path: Path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    r = client.get("/api/admin/statistics/extract/nonexistent", headers=AUTH)
    assert r.status_code == 404
