"""Tests for user CRUD + authenticate + lockout backoff."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path  # noqa: TC003

import pytest
from local_pdf.auth.db import ensure_schema, open_auth_db
from local_pdf.auth.tenants import create_tenant
from local_pdf.auth.users import (
    InactiveUserError,
    LoginLockedError,
    UnknownUserError,
    WrongPasswordError,
    authenticate,
    change_password,
    create_user,
    deactivate_user,
    get_user_by_id,
    list_users_for_tenant,
)


def _setup(tmp_path: Path):
    """Spin up an empty DB with one tenant."""
    cm = open_auth_db(tmp_path)
    conn = cm.__enter__()
    ensure_schema(conn)
    tenant = create_tenant(conn, slug="default", name="Default")
    return cm, conn, tenant


def test_create_user_auto_pseudonym(tmp_path: Path) -> None:
    cm, conn, tenant = _setup(tmp_path)
    try:
        u = create_user(conn, tenant_id=tenant.tenant_id, username="alice", password="pw")
        assert u.username == "alice"
        assert u.user_id.startswith("u-")
        assert u.pseudonym  # auto-generated, non-empty
        assert " " in u.pseudonym  # 'Adjective Animal' shape
        assert u.role == "curator"
        assert u.active is True
        assert u.last_login_at is None
    finally:
        cm.__exit__(None, None, None)


def test_create_user_with_custom_pseudonym(tmp_path: Path) -> None:
    cm, conn, tenant = _setup(tmp_path)
    try:
        u = create_user(
            conn,
            tenant_id=tenant.tenant_id,
            username="bob",
            password="pw",
            pseudonym="Neugieriger Hirsch",
        )
        assert u.pseudonym == "Neugieriger Hirsch"
    finally:
        cm.__exit__(None, None, None)


def test_create_user_rejects_email_pseudonym(tmp_path: Path) -> None:
    cm, conn, tenant = _setup(tmp_path)
    try:
        with pytest.raises(ValueError, match="E-Mail"):
            create_user(
                conn,
                tenant_id=tenant.tenant_id,
                username="bob",
                password="pw",
                pseudonym="hans@example.com",
            )
    finally:
        cm.__exit__(None, None, None)


def test_username_unique_within_tenant(tmp_path: Path) -> None:
    cm, conn, tenant = _setup(tmp_path)
    try:
        create_user(conn, tenant_id=tenant.tenant_id, username="alice", password="pw")
        with pytest.raises(ValueError, match="already taken"):
            create_user(conn, tenant_id=tenant.tenant_id, username="alice", password="pw2")
    finally:
        cm.__exit__(None, None, None)


def test_username_can_repeat_across_tenants(tmp_path: Path) -> None:
    cm, conn, tenant = _setup(tmp_path)
    try:
        other = create_tenant(conn, slug="other", name="Other")
        create_user(conn, tenant_id=tenant.tenant_id, username="alice", password="pw")
        # No raise: alice in tenant 'other' is a separate row.
        u2 = create_user(conn, tenant_id=other.tenant_id, username="alice", password="pw")
        assert u2.tenant_id != tenant.tenant_id
    finally:
        cm.__exit__(None, None, None)


def test_authenticate_success(tmp_path: Path) -> None:
    cm, conn, tenant = _setup(tmp_path)
    try:
        u = create_user(conn, tenant_id=tenant.tenant_id, username="alice", password="secret")
        authed = authenticate(conn, tenant_slug=tenant.slug, username="alice", password="secret")
        assert authed.user_id == u.user_id
        # last_login_at is updated.
        reread = get_user_by_id(conn, u.user_id)
        assert reread is not None
        assert reread.last_login_at is not None
    finally:
        cm.__exit__(None, None, None)


def test_authenticate_wrong_password(tmp_path: Path) -> None:
    cm, conn, tenant = _setup(tmp_path)
    try:
        create_user(conn, tenant_id=tenant.tenant_id, username="alice", password="secret")
        with pytest.raises(WrongPasswordError):
            authenticate(conn, tenant_slug=tenant.slug, username="alice", password="wrong")
    finally:
        cm.__exit__(None, None, None)


def test_authenticate_unknown_user(tmp_path: Path) -> None:
    cm, conn, tenant = _setup(tmp_path)
    try:
        with pytest.raises(UnknownUserError):
            authenticate(conn, tenant_slug=tenant.slug, username="ghost", password="x")
    finally:
        cm.__exit__(None, None, None)


def test_authenticate_unknown_tenant(tmp_path: Path) -> None:
    cm, conn, _tenant = _setup(tmp_path)
    try:
        with pytest.raises(UnknownUserError):
            authenticate(conn, tenant_slug="missing", username="alice", password="x")
    finally:
        cm.__exit__(None, None, None)


def test_authenticate_inactive_user(tmp_path: Path) -> None:
    cm, conn, tenant = _setup(tmp_path)
    try:
        u = create_user(conn, tenant_id=tenant.tenant_id, username="alice", password="pw")
        deactivate_user(conn, u.user_id)
        with pytest.raises(InactiveUserError):
            authenticate(conn, tenant_slug=tenant.slug, username="alice", password="pw")
    finally:
        cm.__exit__(None, None, None)


def test_lockout_after_five_wrong_attempts(tmp_path: Path) -> None:
    cm, conn, tenant = _setup(tmp_path)
    try:
        create_user(conn, tenant_id=tenant.tenant_id, username="alice", password="pw")
        for _ in range(5):
            with pytest.raises(WrongPasswordError):
                authenticate(conn, tenant_slug=tenant.slug, username="alice", password="bad")
        # Correct password also locked out now.
        with pytest.raises(LoginLockedError) as excinfo:
            authenticate(conn, tenant_slug=tenant.slug, username="alice", password="pw")
        # locked_until is parseable ISO string in the future.
        locked_until = datetime.fromisoformat(excinfo.value.locked_until)
        assert locked_until > datetime.now(locked_until.tzinfo)
    finally:
        cm.__exit__(None, None, None)


def test_lockout_window_resets(tmp_path: Path) -> None:
    """Outside the 5-min window the attempt counter starts over."""
    cm, conn, tenant = _setup(tmp_path)
    try:
        create_user(conn, tenant_id=tenant.tenant_id, username="alice", password="pw")
        # Simulate an old failed attempt by writing the row directly.
        # Must be tz-aware so datetime.fromisoformat round-trip matches
        # the production code's datetime.now(UTC).
        old = (datetime.now(UTC) - timedelta(hours=2)).isoformat(timespec="seconds")
        conn.execute(
            """
            INSERT INTO failed_logins (tenant_id, username, attempts, last_attempt)
            VALUES (?, ?, 4, ?)
            """,
            (tenant.tenant_id, "alice", old),
        )
        with pytest.raises(WrongPasswordError):
            authenticate(conn, tenant_slug=tenant.slug, username="alice", password="bad")
        row = conn.execute(
            "SELECT attempts FROM failed_logins WHERE tenant_id = ? AND username = ?",
            (tenant.tenant_id, "alice"),
        ).fetchone()
        # Window expired, counter restarted at 1.
        assert int(row["attempts"]) == 1
    finally:
        cm.__exit__(None, None, None)


def test_change_password_resets_credentials(tmp_path: Path) -> None:
    cm, conn, tenant = _setup(tmp_path)
    try:
        u = create_user(conn, tenant_id=tenant.tenant_id, username="alice", password="old")
        change_password(conn, user_id=u.user_id, new_password="new")
        with pytest.raises(WrongPasswordError):
            authenticate(conn, tenant_slug=tenant.slug, username="alice", password="old")
        authenticate(conn, tenant_slug=tenant.slug, username="alice", password="new")
    finally:
        cm.__exit__(None, None, None)


def test_list_users_for_tenant(tmp_path: Path) -> None:
    cm, conn, tenant = _setup(tmp_path)
    try:
        create_user(conn, tenant_id=tenant.tenant_id, username="alice", password="pw")
        create_user(conn, tenant_id=tenant.tenant_id, username="bob", password="pw")
        users = list_users_for_tenant(conn, tenant.tenant_id)
        assert {u.username for u in users} == {"alice", "bob"}
    finally:
        cm.__exit__(None, None, None)
