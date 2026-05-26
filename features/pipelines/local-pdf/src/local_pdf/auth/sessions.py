"""Session token create / lookup / revoke.

Sessions are opaque random tokens, 32 url-safe bytes. They're stored
as-is (no hashing) because the DB file is chmod 0600 — same trust
boundary as the cookie itself. If the file is readable by the
attacker, they already have everything.

The session row contains ``expires_at`` so the middleware can reject
expired sessions on lookup without a separate sweep. Expired rows are
garbage-collected lazily by :func:`prune_expired`; nothing currently
schedules it but a /api/admin/maintenance hook can call it on a
cadence.
"""

from __future__ import annotations

import secrets
import sqlite3  # noqa: TC003
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# Sessions live 24h by default. Short enough to limit damage from a
# leaked cookie; long enough that a reviewer doesn't have to log in
# every coffee break. Tuned in code, not schema.
_SESSION_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class Session:
    session_id: str
    user_id: str
    created_at: str
    expires_at: str
    revoked: bool


def _now() -> datetime:
    return datetime.now(UTC)


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _new_session_token() -> str:
    """Opaque 32-byte random, url-safe base64. ~256 bits of entropy."""
    return secrets.token_urlsafe(32)


def create_session(
    conn: sqlite3.Connection, *, user_id: str, ttl: timedelta | None = None
) -> Session:
    """Issue a session for ``user_id`` and return it.

    Caller writes the returned ``session_id`` into an HttpOnly cookie.
    """
    ttl_resolved = ttl if ttl is not None else _SESSION_TTL
    session_id = _new_session_token()
    now = _now()
    expires_at = (now + ttl_resolved).isoformat(timespec="seconds")
    created_at = now.isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO sessions (session_id, user_id, created_at, expires_at, revoked)
        VALUES (?, ?, ?, ?, 0)
        """,
        (session_id, user_id, created_at, expires_at),
    )
    return Session(
        session_id=session_id,
        user_id=user_id,
        created_at=created_at,
        expires_at=expires_at,
        revoked=False,
    )


def lookup_session(conn: sqlite3.Connection, session_id: str) -> Session | None:
    """Return the session if it's valid (not revoked, not expired),
    else ``None``. The middleware calls this on every request.
    """
    if not session_id:
        return None
    row = conn.execute(
        """
        SELECT session_id, user_id, created_at, expires_at, revoked
        FROM sessions WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    if int(row["revoked"]) != 0:
        return None
    expires = datetime.fromisoformat(row["expires_at"])
    if _now() >= expires:
        return None
    return Session(
        session_id=row["session_id"],
        user_id=row["user_id"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        revoked=False,
    )


def revoke_session(conn: sqlite3.Connection, session_id: str) -> None:
    """Mark the session revoked. Idempotent: re-revoking is a no-op."""
    if not session_id:
        return
    conn.execute("UPDATE sessions SET revoked = 1 WHERE session_id = ?", (session_id,))


def revoke_all_sessions_for_user(conn: sqlite3.Connection, user_id: str) -> None:
    """Force-logout all of a user's sessions. Use on password change
    or admin deactivation."""
    conn.execute("UPDATE sessions SET revoked = 1 WHERE user_id = ?", (user_id,))


def prune_expired(conn: sqlite3.Connection) -> int:
    """Delete rows whose ``expires_at`` is in the past. Returns the
    number of rows removed so a maintenance endpoint can log it.
    """
    cursor = conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (_now_iso(),))
    return cursor.rowcount or 0
