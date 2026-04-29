"""Tests for goldens.creation.prompts — JSON-file prompt-template
store with filename-suffix versioning and schema-validating loader.

Spec: docs/superpowers/specs/2026-04-29-a5-synthetic-design.md §4.1, §9.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from goldens.creation.prompts import (
    PromptNotFoundError,
    PromptSchemaError,
    load_prompt,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_load_prompt_returns_template():
    """Happy path: paragraph_v1 file exists, schema valid, returns the
    `template` field as a string with real newlines."""
    template = load_prompt("paragraph", "v1")
    assert isinstance(template, str)
    assert template  # non-empty
    # The on-disk JSON encodes newlines as `\n`; json.loads turns them
    # into real newlines, so the returned string contains them.
    assert "\n" in template
    # Must contain the {content} placeholder used by the renderer.
    assert "{content}" in template


def test_load_prompt_default_version_is_v1():
    """Calling load_prompt without `version` resolves to v1."""
    assert load_prompt("paragraph") == load_prompt("paragraph", "v1")


def test_load_prompt_raises_on_unknown_element_type(tmp_path: Path):
    """`element_type='figure'` has no v1 prompt by design — load must
    raise PromptNotFoundError, not fall back silently."""
    with pytest.raises(PromptNotFoundError):
        load_prompt("figure", "v1")


def test_load_prompt_raises_on_filename_field_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A tampered file (filename `paragraph_v1.json` but JSON says
    element_type='table') must raise PromptSchemaError. We test this
    by swapping the prompts dir to a tmp_path with a tampered file."""
    fake_dir = tmp_path / "prompts"
    fake_dir.mkdir()
    tampered = fake_dir / "paragraph_v1.json"
    tampered.write_text(
        json.dumps(
            {
                "version": "v1",
                "element_type": "table",  # wrong! filename says "paragraph"
                "description": "tampered",
                "template": "x {content}",
            }
        ),
        encoding="utf-8",
    )

    import goldens.creation.prompts as mod

    monkeypatch.setattr(mod, "_PROMPTS_DIR", fake_dir)
    with pytest.raises(PromptSchemaError):
        load_prompt("paragraph", "v1")


def test_load_prompt_raises_on_missing_required_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """JSON missing `template` must raise PromptSchemaError."""
    fake_dir = tmp_path / "prompts"
    fake_dir.mkdir()
    bad = fake_dir / "paragraph_v1.json"
    bad.write_text(
        json.dumps(
            {
                "version": "v1",
                "element_type": "paragraph",
                "description": "missing template",
                # no `template` key
            }
        ),
        encoding="utf-8",
    )

    import goldens.creation.prompts as mod

    monkeypatch.setattr(mod, "_PROMPTS_DIR", fake_dir)
    with pytest.raises(PromptSchemaError):
        load_prompt("paragraph", "v1")


def test_load_prompt_raises_on_version_field_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Filename says v1 but JSON says version='v9' — PromptSchemaError."""
    fake_dir = tmp_path / "prompts"
    fake_dir.mkdir()
    p = fake_dir / "paragraph_v1.json"
    p.write_text(
        json.dumps(
            {
                "version": "v9",  # filename suffix is _v1, mismatch
                "element_type": "paragraph",
                "description": "wrong version",
                "template": "{content}",
            }
        ),
        encoding="utf-8",
    )

    import goldens.creation.prompts as mod

    monkeypatch.setattr(mod, "_PROMPTS_DIR", fake_dir)
    with pytest.raises(PromptSchemaError):
        load_prompt("paragraph", "v1")


def test_all_v1_files_load_without_error():
    """Smoke: every shipped *_v1.json file in the real prompts dir
    loads without raising. Catches typos in shipped templates early."""
    for et in ("paragraph", "table_row", "list_item"):
        s = load_prompt(et, "v1")
        assert isinstance(s, str)
        assert s


def test_load_prompt_raises_on_invalid_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """File exists but contents are not valid JSON — PromptSchemaError."""
    fake_dir = tmp_path / "prompts"
    fake_dir.mkdir()
    (fake_dir / "paragraph_v1.json").write_text("{not json", encoding="utf-8")

    import goldens.creation.prompts as mod

    monkeypatch.setattr(mod, "_PROMPTS_DIR", fake_dir)
    with pytest.raises(PromptSchemaError):
        load_prompt("paragraph", "v1")


def test_load_prompt_raises_on_empty_template(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """`template` present but empty string — PromptSchemaError."""
    fake_dir = tmp_path / "prompts"
    fake_dir.mkdir()
    (fake_dir / "paragraph_v1.json").write_text(
        json.dumps(
            {
                "version": "v1",
                "element_type": "paragraph",
                "description": "empty template",
                "template": "",
            }
        ),
        encoding="utf-8",
    )

    import goldens.creation.prompts as mod

    monkeypatch.setattr(mod, "_PROMPTS_DIR", fake_dir)
    with pytest.raises(PromptSchemaError):
        load_prompt("paragraph", "v1")
