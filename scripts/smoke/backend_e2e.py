#!/usr/bin/env python3
"""End-to-end backend smoke for Statistik + Voting (PR #51).

Seeds a synthetic doc inside the configured data_root, hits every endpoint
the new feature touches, and asserts the JSON-side contract that the
walkthrough doc verifies visually. Token-auth mode.

Usage::

    export GOLDENS_API_TOKEN="dev-token"
    export LOCAL_PDF_DATA_ROOT="/home/ktazefid/Documents/local-pdf-test/data"
    # backend already running on :8000

    source .venv/bin/activate
    python scripts/smoke/backend_e2e.py
    # → 14 assertions printed, exit 0 on green

The script is **idempotent and isolated**: it seeds under a unique slug
(``smoke-<timestamp>``) and removes the slug dir on exit unless ``--keep``
is passed. Auth DB and other docs are never touched.

Out of scope: visual stripe colors, anti-anchoring visibility (UI-only),
Recharts rendering. Those are in ``frontend/tests/admin/e2e/...``.

Pre-merge note: until PR #51 (``feat/statistics-and-voting``) lands on
main, the .venv's editable ``goldens`` install lacks ``revoked`` as a
valid ``Review.action``. Run the backend with the worktree's goldens
on PYTHONPATH so the projection accepts revoked-events::

    git worktree add /tmp/repo-stats feat/statistics-and-voting
    WT=/tmp/repo-stats
    PYTHONPATH="$WT/features/goldens/src:$WT/features/pipelines/local-pdf/src" \\
    GOLDENS_API_TOKEN=dev-token \\
    LOCAL_PDF_DATA_ROOT=/tmp/smoke-data \\
    .venv/bin/python -m uvicorn local_pdf.api.app:create_app --factory --port 8088
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, NoReturn, cast

import httpx

API_BASE = os.environ.get("LOCAL_PDF_API_BASE", "http://localhost:8000")


def _hdr(token: str) -> dict[str, str]:
    return {"X-Auth-Token": token}


def _ok(check: str) -> None:
    print(f"  ✓ {check}")


def _bad(check: str, detail: str) -> NoReturn:
    print(f"  ✗ {check}\n    {detail}")
    sys.exit(1)


def _info(msg: str) -> None:
    print(f"\n→ {msg}")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── Seeding helpers ─────────────────────────────────────────────────────────


def _seed_doc(data_root: Path, slug: str) -> str:
    """Write a minimal doc tree with one synthesised question.

    Returns the entry_id of the seeded question — vote endpoints address
    it by that ID.
    """
    doc = data_root / slug
    doc.mkdir(parents=True, exist_ok=True)
    (doc / "datasets").mkdir(parents=True, exist_ok=True)

    # Mineru output with a couple diagnostics so DiagnosticBar has data.
    (doc / "mineru-out.json").write_text(
        json.dumps(
            {
                "elements": [{"id": f"e{i}"} for i in range(10)],
                "diagnostics": [
                    {"kind": "split"},
                    {"kind": "no_decomposition"},
                ],
            }
        )
    )

    # Segments with a mix of register and non-register kinds.
    boxes = [
        {"box_id": "b1", "page": 1, "kind": "toc", "bbox": [0, 0, 100, 100], "confidence": 0.9},
        {
            "box_id": "b2",
            "page": 1,
            "kind": "paragraph",
            "bbox": [0, 100, 100, 200],
            "confidence": 0.9,
        },
        {
            "box_id": "b3",
            "page": 1,
            "kind": "list_of_tables",
            "bbox": [0, 200, 100, 300],
            "confidence": 0.9,
        },
        {
            "box_id": "b4",
            "page": 1,
            "kind": "paragraph",
            "bbox": [0, 300, 100, 400],
            "confidence": 0.9,
        },
        {
            "box_id": "b5",
            "page": 1,
            "kind": "paragraph",
            "bbox": [0, 400, 100, 500],
            "confidence": 0.9,
        },
    ]
    (doc / "segments.json").write_text(json.dumps({"slug": slug, "boxes": boxes}))

    # One synthesised retrieval entry — gives the vote endpoint something
    # to address. The entry_id is what becomes the {question_id} URL param.
    entry_id = f"r-smoke-{int(time.time() * 1000)}"
    events_path = doc / "datasets" / "golden_events_v1.jsonl"
    event = {
        "event_id": f"ev-smoke-{int(time.time() * 1000)}",
        "timestamp_utc": _now(),
        "event_type": "created",
        "entry_id": entry_id,
        "schema_version": 1,
        "payload": {
            # task_type sits at the top level of payload (NOT nested under
            # entry_data) — _apply_created in goldens/storage/projection.py
            # gates on this key. Don't move it.
            "task_type": "retrieval",
            "action": "synthesised",
            "actor": {"kind": "human", "pseudonym": "smoke-seed", "level": "other"},
            "entry_data": {
                "query": "Was ist der Registersatz?",
                "expected_chunk_ids": [],
                "chunk_hashes": {},
                "source_element": {
                    "document_id": slug,
                    "page_number": 1,
                    "element_id": "b2",
                    "element_type": "paragraph",
                },
            },
        },
    }
    with events_path.open("a") as f:
        f.write(json.dumps(event) + "\n")

    return entry_id


# ── Endpoint exercises ──────────────────────────────────────────────────────


def _check_health(client: httpx.Client, token: str) -> Path:
    _info("Health check")
    r = client.get(f"{API_BASE}/api/health", headers=_hdr(token))
    if r.status_code != 200:
        _bad("GET /api/health", f"status={r.status_code} body={r.text[:200]}")
    _ok(f"GET /api/health → 200 ({r.json()['data_root']})")
    return Path(r.json()["data_root"])


def _check_extract_stats(client: httpx.Client, token: str, slug: str) -> dict[str, Any]:
    _info("Extract stats endpoint (metric #1+#2)")
    r = client.get(f"{API_BASE}/api/admin/statistics/extract/{slug}", headers=_hdr(token))
    if r.status_code != 200:
        _bad("GET /api/admin/statistics/extract/{slug}", f"status={r.status_code} body={r.text}")
    body = r.json()
    assert body["diagnostics"]["split"] == 1, body
    assert body["diagnostics"]["no_decomposition"] == 1, body
    assert body["diagnostics"]["clean"] == 8, body
    assert body["diagnostics"]["total"] == 10, body
    assert body["register_boxes"] == 2, body
    assert body["total_boxes"] == 5, body
    assert abs(body["register_rate"] - 0.4) < 1e-9, body
    _ok("DiagnosticCounts: split=1 no_decomp=1 clean=8 total=10")
    _ok("Register: 2 / 5 = 0.4")
    return cast("dict[str, Any]", body)


def _check_synthese_stats_pre_vote(client: httpx.Client, token: str, slug: str) -> dict[str, Any]:
    _info("Synthese stats — pre-vote baseline (metric #3+#4)")
    r = client.get(f"{API_BASE}/api/admin/statistics/synthese/{slug}", headers=_hdr(token))
    if r.status_code != 200:
        _bad("GET /api/admin/statistics/synthese/{slug}", f"status={r.status_code}")
    body = r.json()
    assert body["questions_created"] == 1, body
    assert body["questions_deprecated"] == 0, body
    assert body["survival_rate"] == 1.0, body
    assert body["vote_approved"] == 0, body
    assert body["vote_rejected"] == 0, body
    assert body["vote_approval_rate"] is None, body
    assert body["vote_distribution"] == [], body
    _ok("survival_rate=1.0 (1 created, 0 deprecated)")
    _ok("vote_approval_rate=null (no votes yet)")
    return cast("dict[str, Any]", body)


def _check_provenienz_stats_empty(client: httpx.Client, token: str, slug: str) -> None:
    _info("Provenienz stats — empty (no agent session)")
    r = client.get(f"{API_BASE}/api/admin/statistics/provenienz/{slug}", headers=_hdr(token))
    if r.status_code != 200:
        _bad("GET /api/admin/statistics/provenienz/{slug}", f"status={r.status_code}")
    body = r.json()
    assert body["plan_proposals"] == 0, body
    assert body["expert_overrides"] == 0, body
    assert body["correction_rate"] is None, body
    _ok("plan_proposals=0 → correction_rate=null")


def _check_capability_wishes(client: httpx.Client, token: str) -> None:
    _info("Capability-wishes (tenant-wide aggregator)")
    r = client.get(f"{API_BASE}/api/admin/statistics/capability-wishes", headers=_hdr(token))
    if r.status_code != 200:
        _bad("GET /api/admin/statistics/capability-wishes", f"status={r.status_code}")
    body = r.json()
    assert "wishes" in body, body
    assert isinstance(body["wishes"], list), body
    _ok(f"capability-wishes endpoint returns shape (wishes: {len(body['wishes'])})")


def _check_questions_pre_vote(client: httpx.Client, token: str, slug: str, entry_id: str) -> None:
    _info("GET /questions — verify vote_summary defaults")
    r = client.get(f"{API_BASE}/api/admin/docs/{slug}/questions", headers=_hdr(token))
    if r.status_code != 200:
        _bad("GET /api/admin/docs/{slug}/questions", f"status={r.status_code}")
    body = r.json()
    # Response shape: dict[box_id, list[question_dict]]
    found = None
    for _box, qs in body.items():
        for q in qs:
            if q.get("entry_id") == entry_id:
                found = q
                break
    if found is None:
        _bad("seeded entry_id not found in /questions response", f"got box_ids={list(body)}")
    summary = found.get("vote_summary")
    assert summary is not None, "vote_summary missing"
    assert summary["approved_count"] == 0, summary
    assert summary["rejected_count"] == 0, summary
    assert summary["my_vote"] is None, summary
    _ok("vote_summary={approved_count:0, rejected_count:0, my_vote:null} on fresh entry")


def _vote(
    client: httpx.Client, token: str, slug: str, entry_id: str, action: str
) -> dict[str, Any]:
    r = client.post(
        f"{API_BASE}/api/admin/docs/{slug}/questions/{entry_id}/vote",
        headers={**_hdr(token), "Content-Type": "application/json"},
        json={"action": action},
    )
    if r.status_code != 200:
        _bad(f"POST /vote (action={action})", f"status={r.status_code} body={r.text}")
    body = r.json()
    assert body["event_type"] == "reviewed", body
    assert body["payload"]["action"] == action, body
    return cast("dict[str, Any]", body)


def _check_vote_approved(client: httpx.Client, token: str, slug: str, entry_id: str) -> None:
    _info("POST /vote action=approved")
    _vote(client, token, slug, entry_id, "approved")
    _ok("event appended (event_type=reviewed action=approved)")

    r = client.get(f"{API_BASE}/api/admin/docs/{slug}/questions", headers=_hdr(token))
    body = r.json()
    q = next(qs[0] for qs in body.values())
    s = q["vote_summary"]
    assert s["approved_count"] == 1, s
    assert s["rejected_count"] == 0, s
    assert s["my_vote"] == "approved", s
    _ok("GET /questions vote_summary now {approved:1, rejected:0, my_vote:'approved'}")


def _check_synthese_stats_post_vote(client: httpx.Client, token: str, slug: str) -> None:
    _info("Synthese stats — post-vote (metric #4 picks up the vote)")
    r = client.get(f"{API_BASE}/api/admin/statistics/synthese/{slug}", headers=_hdr(token))
    body = r.json()
    assert body["vote_approved"] == 1, body
    assert body["vote_rejected"] == 0, body
    assert body["vote_approval_rate"] == 1.0, body
    assert len(body["vote_distribution"]) == 1, body
    assert body["vote_distribution"][0]["approved"] == 1, body
    _ok("vote_approval_rate=1.0; vote_distribution has 1 row")


def _check_toggle_revoked(client: httpx.Client, token: str, slug: str, entry_id: str) -> None:
    _info("POST /vote action=revoked (toggle-off)")
    _vote(client, token, slug, entry_id, "revoked")
    _ok("revoked event appended")

    r = client.get(f"{API_BASE}/api/admin/docs/{slug}/questions", headers=_hdr(token))
    if r.status_code != 200:
        _bad("GET /questions (post-revoke)", f"status={r.status_code} body={r.text[:300]}")
    body = r.json()
    if not body or not any(body.values()):
        _bad("GET /questions returned empty after revoke", f"body={body}")
    q = next(qs[0] for qs in body.values() if isinstance(qs, list) and qs)
    s = q["vote_summary"]
    assert s["approved_count"] == 0, s
    assert s["rejected_count"] == 0, s
    assert s["my_vote"] is None, s
    _ok("vote_summary back to {0, 0, null} — revoked is excluded from counts")


def _check_events_jsonl(data_root: Path, slug: str) -> None:
    _info("events.jsonl — direct file read, last-3 lines")
    path = data_root / slug / "datasets" / "golden_events_v1.jsonl"
    lines = path.read_text().splitlines()
    assert len(lines) >= 3, f"expected ≥3 lines, got {len(lines)}"
    last_three = [json.loads(line) for line in lines[-3:]]
    actions = [ev["payload"].get("action") for ev in last_three]
    types = [ev["event_type"] for ev in last_three]
    assert types == ["created", "reviewed", "reviewed"], types
    assert actions == ["synthesised", "approved", "revoked"], actions
    _ok(f"event types: {types}")
    _ok(f"actions:     {actions}")


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--keep",
        action="store_true",
        help="skip cleanup of the seeded slug dir (useful for triage)",
    )
    args = parser.parse_args()

    token = os.environ.get("GOLDENS_API_TOKEN")
    if not token:
        print("FATAL: GOLDENS_API_TOKEN env var not set", file=sys.stderr)
        return 2

    slug = f"smoke-{int(time.time())}"
    print(f"Seeding smoke doc with slug={slug}\n")

    with httpx.Client(timeout=15.0) as client:
        data_root = _check_health(client, token)

        entry_id = _seed_doc(data_root, slug)
        print(f"  ✓ seeded {slug} with entry_id={entry_id}")

        try:
            _check_extract_stats(client, token, slug)
            _check_synthese_stats_pre_vote(client, token, slug)
            _check_provenienz_stats_empty(client, token, slug)
            _check_capability_wishes(client, token)
            _check_questions_pre_vote(client, token, slug, entry_id)
            _check_vote_approved(client, token, slug, entry_id)
            _check_synthese_stats_post_vote(client, token, slug)
            _check_toggle_revoked(client, token, slug, entry_id)
            _check_events_jsonl(data_root, slug)
        finally:
            if args.keep:
                print(f"\n  ⤳ keeping {data_root / slug} for triage")
            else:
                shutil.rmtree(data_root / slug, ignore_errors=True)
                print(f"\n  ⤳ cleaned up {slug}")

    print("\n✓ All backend smoke assertions passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
