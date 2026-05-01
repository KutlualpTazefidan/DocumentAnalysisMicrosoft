"""Shared fixtures for local-pdf tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def data_root(tmp_path):

    root = tmp_path / "raw-pdfs"
    root.mkdir()
    return root
