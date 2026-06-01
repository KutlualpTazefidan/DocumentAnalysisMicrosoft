"""Storage tests for the approach library."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from local_pdf.provenienz.approaches import (
    delete_approach,
    disable_approach,
    get_approach,
    read_approaches,
    upsert_approach,
)


def test_upsert_creates_v1(tmp_path: Path):
    a = upsert_approach(
        tmp_path,
        name="thorough",
        step_kinds=["extract_claims"],
        extra_system="Sei gründlich.",
    )
    assert a.version == 1
    assert a.enabled is True
    assert a.approach_id


def test_upsert_bumps_version_for_same_name(tmp_path: Path):
    upsert_approach(
        tmp_path, name="thorough", step_kinds=["extract_claims"], extra_system="v1 text"
    )
    a2 = upsert_approach(
        tmp_path, name="thorough", step_kinds=["extract_claims"], extra_system="v2 text"
    )
    assert a2.version == 2
    out = read_approaches(tmp_path)
    assert len(out) == 1  # latest only
    assert out[0].extra_system == "v2 text"


def test_read_filters_by_step_kind(tmp_path: Path):
    upsert_approach(tmp_path, name="x", step_kinds=["extract_claims"], extra_system="ec")
    upsert_approach(tmp_path, name="y", step_kinds=["evaluate"], extra_system="ev")
    ec = read_approaches(tmp_path, step_kind="extract_claims")
    ev = read_approaches(tmp_path, step_kind="evaluate")
    assert {a.name for a in ec} == {"x"}
    assert {a.name for a in ev} == {"y"}


def test_disable_drops_from_default_read(tmp_path: Path):
    a = upsert_approach(tmp_path, name="z", step_kinds=["extract_claims"], extra_system="hi")
    disable_approach(tmp_path, a.approach_id)
    assert read_approaches(tmp_path) == []
    out_all = read_approaches(tmp_path, enabled_only=False)
    assert len(out_all) == 1
    assert out_all[0].enabled is False


def test_delete_removes_from_read(tmp_path: Path):
    a = upsert_approach(tmp_path, name="z", step_kinds=["extract_claims"], extra_system="hi")
    assert delete_approach(tmp_path, a.approach_id) is True
    assert read_approaches(tmp_path) == []
    assert read_approaches(tmp_path, enabled_only=False) == []


def test_get_by_id(tmp_path: Path):
    a = upsert_approach(tmp_path, name="g", step_kinds=["extract_claims"], extra_system="hi")
    got = get_approach(tmp_path, a.approach_id)
    assert got is not None
    assert got.name == "g"
    assert get_approach(tmp_path, "missing-id") is None
