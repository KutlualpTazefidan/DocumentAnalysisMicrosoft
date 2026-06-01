"""Tests for session create / lookup / revoke / prune."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path  # noqa: TC003

from local_pdf.auth.db import ensure_schema, open_auth_db
from local_pdf.auth.sessions import (
    create_session,
    lookup_session,
    prune_expired,
    revoke_all_sessions_for_user,
    revoke_session,
)
from local_pdf.auth.tenants import create_tenant
from local_pdf.auth.users import create_user


def _setup(tmp_path: Path):
    cm = open_auth_db(tmp_path)
    conn = cm.__enter__()
    ensure_schema(conn)
    tenant = create_tenant(conn, slug="default", name="Default")
    user = create_user(conn, tenant_id=tenant.tenant_id, username="alice", password="pw")
    return cm, conn, user


def test_create_and_lookup_session(tmp_path: Path) -> None:
    cm, conn, user = _setup(tmp_path)
    try:
        s = create_session(conn, user_id=user.user_id)
        assert s.session_id  # opaque, non-empty
        assert len(s.session_id) >= 32  # token_urlsafe(32) is >= 32 chars
        looked_up = lookup_session(conn, s.session_id)
        assert looked_up is not None
        assert looked_up.user_id == user.user_id
        assert looked_up.revoked is False
    finally:
        cm.__exit__(None, None, None)


def test_lookup_empty_returns_none(tmp_path: Path) -> None:
    cm, conn, _ = _setup(tmp_path)
    try:
        assert lookup_session(conn, "") is None
        assert lookup_session(conn, "not-a-real-token") is None
    finally:
        cm.__exit__(None, None, None)


def test_revoke_session(tmp_path: Path) -> None:
    cm, conn, user = _setup(tmp_path)
    try:
        s = create_session(conn, user_id=user.user_id)
        revoke_session(conn, s.session_id)
        assert lookup_session(conn, s.session_id) is None
        # idempotent
        revoke_session(conn, s.session_id)
        revoke_session(conn, "")
    finally:
        cm.__exit__(None, None, None)


def test_revoke_all_sessions_for_user(tmp_path: Path) -> None:
    cm, conn, user = _setup(tmp_path)
    try:
        s1 = create_session(conn, user_id=user.user_id)
        s2 = create_session(conn, user_id=user.user_id)
        revoke_all_sessions_for_user(conn, user.user_id)
        assert lookup_session(conn, s1.session_id) is None
        assert lookup_session(conn, s2.session_id) is None
    finally:
        cm.__exit__(None, None, None)


def test_expired_session_rejected(tmp_path: Path) -> None:
    cm, conn, user = _setup(tmp_path)
    try:
        # 1-second TTL, sleep past it deterministically by writing a
        # past expires_at directly.
        s = create_session(conn, user_id=user.user_id, ttl=timedelta(seconds=1))
        conn.execute(
            "UPDATE sessions SET expires_at = ? WHERE session_id = ?",
            ("2000-01-01T00:00:00+00:00", s.session_id),
        )
        assert lookup_session(conn, s.session_id) is None
    finally:
        cm.__exit__(None, None, None)


def test_prune_expired_removes_only_old_rows(tmp_path: Path) -> None:
    cm, conn, user = _setup(tmp_path)
    try:
        fresh = create_session(conn, user_id=user.user_id)
        stale = create_session(conn, user_id=user.user_id)
        conn.execute(
            "UPDATE sessions SET expires_at = ? WHERE session_id = ?",
            ("2000-01-01T00:00:00+00:00", stale.session_id),
        )
        removed = prune_expired(conn)
        assert removed == 1
        # Fresh session still valid.
        assert lookup_session(conn, fresh.session_id) is not None
        assert lookup_session(conn, stale.session_id) is None
    finally:
        cm.__exit__(None, None, None)
