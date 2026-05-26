"""Online backup of the auth DB.

Uses SQLite's online-backup API (``sqlite3.Connection.backup``) which
copies the live DB into a destination file while readers + writers
proceed in parallel — gives us a consistent snapshot without
quiescing the server. WAL + journal files are folded into the
destination automatically.

The output is gzipped on the fly to keep snapshots compact (a 50 MB
auth.db with mostly text rows usually shrinks to ~3 MB).
"""

from __future__ import annotations

import contextlib
import gzip
import shutil
import sqlite3
import tempfile
from pathlib import Path

from local_pdf.auth.db import auth_db_path


def backup_auth_db(data_root: Path, dest: Path) -> dict:
    """Online-backup the auth DB at ``data_root`` to ``dest`` (gzipped).

    Returns a dict with ``source``, ``dest``, ``bytes_written``,
    ``source_pages`` so callers can log / surface the result.

    Raises ``FileNotFoundError`` if the source DB doesn't exist; the
    caller maps that to 404 / a clear CLI error. Idempotent: a
    pre-existing ``dest`` is overwritten atomically via tempfile +
    rename so a crashed backup never leaves a half-written file.
    """
    source = auth_db_path(data_root)
    if not source.exists():
        raise FileNotFoundError(f"auth.db not found at {source}")

    dest.parent.mkdir(parents=True, exist_ok=True)

    src_conn = sqlite3.connect(str(source))
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".db.tmp", dir=str(dest.parent), delete=False
        ) as tmp_db_file:
            tmp_db_path = Path(tmp_db_file.name)
        dst_conn = sqlite3.connect(str(tmp_db_path))
        try:
            # ``pages=-1`` copies all pages in one shot; the API yields
            # back to writers between pages internally.
            src_conn.backup(dst_conn, pages=-1)
        finally:
            dst_conn.close()
        # Gzip the snapshot to the final destination.
        bytes_written = 0
        with (
            tmp_db_path.open("rb") as src_fp,
            tempfile.NamedTemporaryFile(
                suffix=".gz.tmp", dir=str(dest.parent), delete=False
            ) as tmp_gz_file,
        ):
            tmp_gz_path = Path(tmp_gz_file.name)
            with gzip.open(tmp_gz_file, "wb", compresslevel=6) as gz:
                shutil.copyfileobj(src_fp, gz)
        bytes_written = tmp_gz_path.stat().st_size
        tmp_gz_path.replace(dest)
        # Source page count for human-readable telemetry.
        src_page_count = src_conn.execute("PRAGMA page_count").fetchone()[0]
    finally:
        src_conn.close()
        # Best-effort tmp cleanup; if rename succeeded these are gone.
        with contextlib.suppress(OSError):
            tmp_db_path.unlink(missing_ok=True)

    return {
        "source": str(source),
        "dest": str(dest),
        "bytes_written": bytes_written,
        "source_pages": int(src_page_count),
    }
