"""Local multi-tenant auth + tenants + sessions.

SQLite-backed because the access pattern is point-lookups on the hot
path (`SELECT user WHERE session = ?` on every request) and the data
model is normalised (tenant -> user -> session, plus failed-login
backoff). The append-only JSONL store would force a full-scan on every
auth check.

This module is the ONLY place where a real username/email lives. Every
audit log persists the user's pseudonym instead — see
``HumanActor.pseudonym`` in ``goldens.schemas.base``.

Public exports:

* :func:`open_auth_db` — context-managed sqlite3 connection
* :func:`ensure_schema` — idempotent CREATE TABLE migrations
* :func:`auth_db_path` — derives the file path from a data_root

Submodules:

* :mod:`local_pdf.auth.tenants` — Tenant CRUD
* :mod:`local_pdf.auth.users` — User CRUD with argon2id hashing
* :mod:`local_pdf.auth.sessions` — Session create / lookup / revoke
* :mod:`local_pdf.auth.pseudonyms` — auto-generator + validator
"""

from __future__ import annotations

from local_pdf.auth.db import (
    auth_db_path,
    ensure_schema,
    open_auth_db,
)

__all__ = ["auth_db_path", "ensure_schema", "open_auth_db"]
