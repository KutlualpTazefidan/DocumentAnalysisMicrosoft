"""User CRUD with argon2id password hashing + failed-login backoff.

Public surface:
  * :func:`create_user`        — admin-only path; takes plain password,
                                 stores hash + pseudonym.
  * :func:`authenticate`       — verify ``(tenant_slug, username, pwd)``,
                                 return ``User`` or raise.
  * :func:`change_password`    — rehash with current Argon2 params.
  * :func:`deactivate_user`    — flip active=0 instead of deleting so
                                 audit trails keep referencing the
                                 user_id.
  * :func:`list_users_for_tenant`

The argon2-cffi default parameters are intentionally accepted: their
defaults track the OWASP Argon2id recommendation and are bumped on
library upgrade. If you need to lock parameters, instantiate your own
``PasswordHasher(...)`` and inject.

Failed-login backoff: ``record_failed_login`` increments a counter per
``(tenant, username)``. ``check_lockout`` raises ``LoginLockedError``
when the counter is above the threshold within the window. The
exponential backoff is computed in code so tuning doesn't need a
migration.
"""

from __future__ import annotations

import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from local_pdf.auth.pseudonyms import (
    generate_pseudonym,
    validate_user_pseudonym,
)
from local_pdf.auth.tenants import get_tenant_by_slug

Role = Literal["admin", "reviewer", "curator"]


@dataclass(frozen=True)
class User:
    user_id: str
    tenant_id: str
    username: str
    pseudonym: str
    role: Role
    active: bool
    created_at: str
    last_login_at: str | None


class AuthError(Exception):
    """Base for all user-facing auth errors."""


class UnknownUserError(AuthError):
    """Username (or tenant) doesn't exist. Mapped to 401 not 404 so we
    don't leak which usernames are valid."""


class WrongPasswordError(AuthError):
    """Username exists but the password verify failed."""


class InactiveUserError(AuthError):
    """User row exists but ``active = 0``."""


class LoginLockedError(AuthError):
    """Too many failed attempts within the backoff window. Includes
    the timestamp the lockout expires for the UI to render a hint."""

    def __init__(self, locked_until: str) -> None:
        super().__init__(f"login locked until {locked_until}")
        self.locked_until = locked_until


_PWH = PasswordHasher()


# Lockout parameters live here in code so tweaks don't need a schema
# bump. Five wrong tries inside five minutes => locked for five.
_LOCK_THRESHOLD = 5
_LOCK_WINDOW = timedelta(minutes=5)
_LOCK_DURATION = timedelta(minutes=5)


def _now() -> datetime:
    return datetime.now(UTC)


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _new_user_id() -> str:
    return f"u-{secrets.token_hex(4)}"


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        user_id=row["user_id"],
        tenant_id=row["tenant_id"],
        username=row["username"],
        pseudonym=row["pseudonym"],
        role=row["role"],
        active=bool(row["active"]),
        created_at=row["created_at"],
        last_login_at=row["last_login_at"],
    )


def create_user(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    username: str,
    password: str,
    role: Role = "curator",
    pseudonym: str | None = None,
) -> User:
    """Create a user inside an existing tenant.

    ``pseudonym=None`` triggers auto-generation; passing a value runs
    it through :func:`validate_user_pseudonym` first. Raises on
    username clash or pseudonym clash inside the same tenant.
    """
    if not username.strip():
        raise ValueError("Username darf nicht leer sein.")
    if not password:
        raise ValueError("Passwort darf nicht leer sein.")

    # Resolve pseudonym before hashing the password so a validation
    # failure doesn't waste the hash work.
    if pseudonym is None:
        existing = {
            row["pseudonym"]
            for row in conn.execute(
                "SELECT pseudonym FROM users WHERE tenant_id = ?", (tenant_id,)
            ).fetchall()
        }
        pseudonym_resolved = generate_pseudonym(exclude=existing)
    else:
        pseudonym_resolved = validate_user_pseudonym(pseudonym)

    password_hash = _PWH.hash(password)
    user_id = _new_user_id()
    created_at = _now_iso()
    try:
        conn.execute(
            """
            INSERT INTO users
              (user_id, tenant_id, username, password_hash, pseudonym, role, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                user_id,
                tenant_id,
                username.strip(),
                password_hash,
                pseudonym_resolved,
                role,
                created_at,
            ),
        )
    except sqlite3.IntegrityError as exc:
        # UNIQUE (tenant_id, username) or UNIQUE (tenant_id, pseudonym).
        # Surfacing as ValueError lets the router map to 409.
        raise ValueError(f"username or pseudonym already taken in tenant: {exc}") from exc

    return User(
        user_id=user_id,
        tenant_id=tenant_id,
        username=username.strip(),
        pseudonym=pseudonym_resolved,
        role=role,
        active=True,
        created_at=created_at,
        last_login_at=None,
    )


def get_user_by_id(conn: sqlite3.Connection, user_id: str) -> User | None:
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def list_users_for_tenant(conn: sqlite3.Connection, tenant_id: str) -> list[User]:
    rows = conn.execute(
        "SELECT * FROM users WHERE tenant_id = ? ORDER BY created_at",
        (tenant_id,),
    ).fetchall()
    return [_row_to_user(r) for r in rows]


def deactivate_user(conn: sqlite3.Connection, user_id: str) -> None:
    conn.execute("UPDATE users SET active = 0 WHERE user_id = ?", (user_id,))


def authenticate(
    conn: sqlite3.Connection,
    *,
    tenant_slug: str,
    username: str,
    password: str,
) -> User:
    """Return the user on success; raise on failure.

    Failure modes are distinct so routes can log richly but the
    client-facing response is the same generic 401 — no user-existence
    oracle.
    """
    tenant = get_tenant_by_slug(conn, tenant_slug)
    if tenant is None:
        # Run argon2 hash anyway to keep timing approximately constant.
        _PWH.hash(password)
        raise UnknownUserError("tenant not found")

    _check_lockout(conn, tenant.tenant_id, username)

    row = conn.execute(
        "SELECT * FROM users WHERE tenant_id = ? AND username = ?",
        (tenant.tenant_id, username),
    ).fetchone()
    if row is None:
        _PWH.hash(password)
        _record_failed_login(conn, tenant.tenant_id, username)
        raise UnknownUserError("user not found")
    user = _row_to_user(row)
    if not user.active:
        _record_failed_login(conn, tenant.tenant_id, username)
        raise InactiveUserError("user deactivated")
    try:
        _PWH.verify(row["password_hash"], password)
    except VerifyMismatchError as exc:
        _record_failed_login(conn, tenant.tenant_id, username)
        raise WrongPasswordError("wrong password") from exc

    # Argon2 parameter upgrade: if the current hash is below the
    # library's defaults, rehash on successful login.
    if _PWH.check_needs_rehash(row["password_hash"]):
        new_hash = _PWH.hash(password)
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE user_id = ?",
            (new_hash, user.user_id),
        )

    conn.execute(
        "UPDATE users SET last_login_at = ? WHERE user_id = ?",
        (_now_iso(), user.user_id),
    )
    _clear_failed_login(conn, tenant.tenant_id, username)
    return user


def change_password(conn: sqlite3.Connection, *, user_id: str, new_password: str) -> None:
    if not new_password:
        raise ValueError("Passwort darf nicht leer sein.")
    new_hash = _PWH.hash(new_password)
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE user_id = ?",
        (new_hash, user_id),
    )


# ── Failed-login backoff ──────────────────────────────────────────────────


def _check_lockout(conn: sqlite3.Connection, tenant_id: str, username: str) -> None:
    row = conn.execute(
        "SELECT lockout_until FROM failed_logins WHERE tenant_id = ? AND username = ?",
        (tenant_id, username),
    ).fetchone()
    if row is None or row["lockout_until"] is None:
        return
    locked_until = datetime.fromisoformat(row["lockout_until"])
    if _now() < locked_until:
        raise LoginLockedError(locked_until=row["lockout_until"])


def _record_failed_login(conn: sqlite3.Connection, tenant_id: str, username: str) -> None:
    now = _now()
    now_iso = now.isoformat(timespec="seconds")
    row = conn.execute(
        "SELECT attempts, last_attempt FROM failed_logins WHERE tenant_id = ? AND username = ?",
        (tenant_id, username),
    ).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO failed_logins (tenant_id, username, attempts, last_attempt)
            VALUES (?, ?, 1, ?)
            """,
            (tenant_id, username, now_iso),
        )
        return
    last = datetime.fromisoformat(row["last_attempt"])
    attempts = 1 if now - last > _LOCK_WINDOW else int(row["attempts"]) + 1
    lockout_until = (
        (now + _LOCK_DURATION).isoformat(timespec="seconds")
        if attempts >= _LOCK_THRESHOLD
        else None
    )
    conn.execute(
        """
        UPDATE failed_logins
        SET attempts = ?, last_attempt = ?, lockout_until = ?
        WHERE tenant_id = ? AND username = ?
        """,
        (attempts, now_iso, lockout_until, tenant_id, username),
    )


def _clear_failed_login(conn: sqlite3.Connection, tenant_id: str, username: str) -> None:
    conn.execute(
        "DELETE FROM failed_logins WHERE tenant_id = ? AND username = ?",
        (tenant_id, username),
    )
