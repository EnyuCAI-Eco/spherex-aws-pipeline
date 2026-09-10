from __future__ import annotations

import csv
import logging
import sqlite3
import threading
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Iterator

from .models import RemoteObject


LOGGER = logging.getLogger(__name__)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket TEXT NOT NULL,
    prefix TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    listed_count INTEGER NOT NULL DEFAULT 0,
    new_count INTEGER NOT NULL DEFAULT 0,
    updated_count INTEGER NOT NULL DEFAULT 0,
    removed_count INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS remote_objects (
    bucket TEXT NOT NULL,
    key TEXT NOT NULL,
    filename TEXT NOT NULL,
    product TEXT,
    planning_period TEXT,
    observation_id TEXT,
    large_slew_counter TEXT,
    small_slew_counter INTEGER,
    detector INTEGER,
    instrument TEXT,
    pipeline_level TEXT,
    pipeline_version TEXT,
    processing_date TEXT,
    size_bytes INTEGER NOT NULL,
    etag TEXT NOT NULL,
    last_modified TEXT NOT NULL,
    storage_class TEXT,
    checksum_algorithms TEXT,
    parse_status TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_seen_run INTEGER NOT NULL,
    is_current INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (bucket, key),
    FOREIGN KEY (last_seen_run) REFERENCES scans(id)
);

CREATE INDEX IF NOT EXISTS idx_remote_current_period
    ON remote_objects(is_current, planning_period, detector);

CREATE TABLE IF NOT EXISTS object_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL,
    event_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    bucket TEXT NOT NULL,
    key TEXT NOT NULL,
    old_size_bytes INTEGER,
    new_size_bytes INTEGER,
    old_etag TEXT,
    new_etag TEXT,
    old_last_modified TEXT,
    new_last_modified TEXT,
    FOREIGN KEY (scan_id) REFERENCES scans(id)
);

CREATE TABLE IF NOT EXISTS downloads (
    bucket TEXT NOT NULL,
    key TEXT NOT NULL,
    remote_size_bytes INTEGER NOT NULL,
    remote_etag TEXT NOT NULL,
    remote_last_modified TEXT NOT NULL,
    local_path TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    bytes_downloaded INTEGER NOT NULL DEFAULT 0,
    selected_at TEXT,
    last_attempt_at TEXT,
    completed_at TEXT,
    verified_at TEXT,
    sha256 TEXT,
    error TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (bucket, key)
);

CREATE TABLE IF NOT EXISTS download_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket TEXT NOT NULL,
    key TEXT NOT NULL,
    event_at TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._write_lock = threading.Lock()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._write_lock, self.connect() as connection:
            connection.executescript(SCHEMA)

    def start_scan(self, bucket: str, prefix: str) -> int:
        with self._write_lock, self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO scans(bucket, prefix, started_at, status)
                VALUES (?, ?, ?, 'running')
                """,
                (bucket, prefix, utc_now()),
            )
            return int(cursor.lastrowid)

    def fail_scan(self, scan_id: int, error: str) -> None:
        with self._write_lock, self.connect() as connection:
            connection.execute(
                """
                UPDATE scans SET completed_at = ?, status = 'failed', error = ?
                WHERE id = ?
                """,
                (utc_now(), error, scan_id),
            )

    def sync_objects(
        self,
        scan_id: int,
        bucket: str,
        prefix: str,
        objects: Iterable[RemoteObject],
    ) -> dict[str, int]:
        counts = {"listed": 0, "new": 0, "updated": 0, "removed": 0}
        now = utc_now()

        with self._write_lock, self.connect() as connection:
            for remote in objects:
                counts["listed"] += 1
                old = connection.execute(
                    """
                    SELECT size_bytes, etag, last_modified
                    FROM remote_objects WHERE bucket = ? AND key = ?
                    """,
                    (bucket, remote.key),
                ).fetchone()

                if old is None:
                    event_type = "new"
                    counts["new"] += 1
                elif (
                    old["size_bytes"],
                    old["etag"],
                    old["last_modified"],
                ) != remote.signature:
                    event_type = "updated"
                    counts["updated"] += 1
                else:
                    event_type = None

                parsed = remote.parsed
                values = (
                    remote.bucket,
                    remote.key,
                    parsed.filename if parsed else Path(remote.key).name,
                    parsed.product if parsed else None,
                    parsed.planning_period if parsed else None,
                    parsed.observation_id if parsed else None,
                    parsed.large_slew_counter if parsed else None,
                    parsed.small_slew_counter if parsed else None,
                    parsed.detector if parsed else None,
                    parsed.instrument if parsed else None,
                    parsed.pipeline_level if parsed else None,
                    parsed.pipeline_version if parsed else None,
                    parsed.processing_date if parsed else None,
                    remote.size_bytes,
                    remote.etag,
                    remote.last_modified,
                    remote.storage_class,
                    remote.checksum_algorithms,
                    "parsed" if parsed else "unmatched",
                    now,
                    now,
                    scan_id,
                )
                connection.execute(
                    """
                    INSERT INTO remote_objects(
                        bucket, key, filename, product, planning_period,
                        observation_id, large_slew_counter, small_slew_counter,
                        detector, instrument, pipeline_level, pipeline_version,
                        processing_date, size_bytes, etag, last_modified,
                        storage_class, checksum_algorithms, parse_status,
                        first_seen_at, last_seen_at, last_seen_run, is_current
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, 1
                    )
                    ON CONFLICT(bucket, key) DO UPDATE SET
                        filename = excluded.filename,
                        product = excluded.product,
                        planning_period = excluded.planning_period,
                        observation_id = excluded.observation_id,
                        large_slew_counter = excluded.large_slew_counter,
                        small_slew_counter = excluded.small_slew_counter,
                        detector = excluded.detector,
                        instrument = excluded.instrument,
                        pipeline_level = excluded.pipeline_level,
                        pipeline_version = excluded.pipeline_version,
                        processing_date = excluded.processing_date,
                        size_bytes = excluded.size_bytes,
                        etag = excluded.etag,
                        last_modified = excluded.last_modified,
                        storage_class = excluded.storage_class,
                        checksum_algorithms = excluded.checksum_algorithms,
                        parse_status = excluded.parse_status,
                        last_seen_at = excluded.last_seen_at,
                        last_seen_run = excluded.last_seen_run,
                        is_current = 1
                    """,
                    values,
                )

                if event_type:
                    connection.execute(
                        """
                        INSERT INTO object_events(
                            scan_id, event_at, event_type, bucket, key,
                            old_size_bytes, new_size_bytes, old_etag, new_etag,
                            old_last_modified, new_last_modified
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            scan_id,
                            now,
                            event_type,
                            bucket,
                            remote.key,
                            old["size_bytes"] if old else None,
                            remote.size_bytes,
                            old["etag"] if old else None,
                            remote.etag,
                            old["last_modified"] if old else None,
                            remote.last_modified,
                        ),
                    )
                    if event_type == "updated":
                        connection.execute(
                            """
                            UPDATE downloads SET
                                status = 'stale',
                                error = 'remote object changed; create a new manifest',
                                updated_at = ?
                            WHERE bucket = ? AND key = ?
                            """,
                            (now, bucket, remote.key),
                        )

                if counts["listed"] % 1000 == 0:
                    LOGGER.info("Cataloged %d S3 objects", counts["listed"])

            removed = connection.execute(
                """
                SELECT key, size_bytes, etag, last_modified
                FROM remote_objects
                WHERE bucket = ?
                  AND substr(key, 1, length(?)) = ?
                  AND is_current = 1
                  AND last_seen_run != ?
                """,
                (bucket, prefix, prefix, scan_id),
            ).fetchall()
            counts["removed"] = len(removed)
            for old in removed:
                connection.execute(
                    """
                    INSERT INTO object_events(
                        scan_id, event_at, event_type, bucket, key,
                        old_size_bytes, old_etag, old_last_modified
                    ) VALUES (?, ?, 'removed', ?, ?, ?, ?, ?)
                    """,
                    (
                        scan_id,
                        now,
                        bucket,
                        old["key"],
                        old["size_bytes"],
                        old["etag"],
                        old["last_modified"],
                    ),
                )
                connection.execute(
                    """
                    UPDATE downloads SET
                        status = 'remote_missing',
                        error = 'object was absent from the latest successful prefix scan',
                        updated_at = ?
                    WHERE bucket = ? AND key = ?
                    """,
                    (now, bucket, old["key"]),
                )
            connection.execute(
                """
                UPDATE remote_objects SET is_current = 0
                WHERE bucket = ?
                  AND substr(key, 1, length(?)) = ?
                  AND last_seen_run != ?
                """,
                (bucket, prefix, prefix, scan_id),
            )
            connection.execute(
                """
                UPDATE scans SET
                    completed_at = ?, status = 'completed', listed_count = ?,
                    new_count = ?, updated_count = ?, removed_count = ?
                WHERE id = ?
                """,
                (
                    utc_now(),
                    counts["listed"],
                    counts["new"],
                    counts["updated"],
                    counts["removed"],
                    scan_id,
                ),
            )
        return counts

    def current_objects(
        self,
        bucket: str,
        planning_period: str | None = None,
    ) -> list[dict[str, object]]:
        query = """
            SELECT * FROM remote_objects
            WHERE bucket = ? AND is_current = 1 AND parse_status = 'parsed'
        """
        parameters: list[object] = [bucket]
        if planning_period:
            query += " AND planning_period = ?"
            parameters.append(planning_period)
        query += " ORDER BY key"
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(query, parameters)]

    def get_remote_object(self, bucket: str, key: str) -> dict[str, object] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM remote_objects WHERE bucket = ? AND key = ?",
                (bucket, key),
            ).fetchone()
            return dict(row) if row else None

    def export_current_csv(self, path: Path, bucket: str) -> int:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM remote_objects
                WHERE bucket = ? AND is_current = 1
                ORDER BY key
                """,
                (bucket,),
            ).fetchall()
            if not rows:
                raise RuntimeError("The catalog is empty; run 'catalog update' first")
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            with temporary.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(dict(row) for row in rows)
            temporary.replace(path)
            return len(rows)

    def get_download(self, bucket: str, key: str) -> dict[str, object] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM downloads WHERE bucket = ? AND key = ?",
                (bucket, key),
            ).fetchone()
            return dict(row) if row else None

    def set_download_status(
        self,
        *,
        bucket: str,
        key: str,
        remote_size_bytes: int,
        remote_etag: str,
        remote_last_modified: str,
        local_path: str,
        status: str,
        message: str | None = None,
        increment_attempts: bool = False,
        bytes_downloaded: int = 0,
        sha256: str | None = None,
        verified: bool = False,
    ) -> None:
        now = utc_now()
        with self._write_lock, self.connect() as connection:
            old = connection.execute(
                "SELECT attempts, selected_at FROM downloads WHERE bucket = ? AND key = ?",
                (bucket, key),
            ).fetchone()
            attempts = (int(old["attempts"]) if old else 0) + int(increment_attempts)
            selected_at = old["selected_at"] if old else now
            completed_at = now if status == "completed" else None
            verified_at = now if verified else None
            connection.execute(
                """
                INSERT INTO downloads(
                    bucket, key, remote_size_bytes, remote_etag,
                    remote_last_modified, local_path, status, attempts,
                    bytes_downloaded, selected_at, last_attempt_at,
                    completed_at, verified_at, sha256, error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(bucket, key) DO UPDATE SET
                    remote_size_bytes = excluded.remote_size_bytes,
                    remote_etag = excluded.remote_etag,
                    remote_last_modified = excluded.remote_last_modified,
                    local_path = excluded.local_path,
                    status = excluded.status,
                    attempts = excluded.attempts,
                    bytes_downloaded = excluded.bytes_downloaded,
                    last_attempt_at = excluded.last_attempt_at,
                    completed_at = excluded.completed_at,
                    verified_at = excluded.verified_at,
                    sha256 = excluded.sha256,
                    error = excluded.error,
                    updated_at = excluded.updated_at
                """,
                (
                    bucket,
                    key,
                    remote_size_bytes,
                    remote_etag,
                    remote_last_modified,
                    local_path,
                    status,
                    attempts,
                    bytes_downloaded,
                    selected_at,
                    now if increment_attempts else None,
                    completed_at,
                    verified_at,
                    sha256,
                    message if status == "failed" else None,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO download_events(bucket, key, event_at, status, message)
                VALUES (?, ?, ?, ?, ?)
                """,
                (bucket, key, now, status, message),
            )

    def download_status_counts(self) -> list[tuple[str, int, int]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT status, COUNT(*) AS count, SUM(bytes_downloaded) AS bytes
                FROM downloads GROUP BY status ORDER BY status
                """
            ).fetchall()
            return [
                (str(row["status"]), int(row["count"]), int(row["bytes"] or 0))
                for row in rows
            ]

    def recent_failures(self, limit: int = 10) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT key, attempts, error, updated_at
                FROM downloads WHERE status = 'failed'
                ORDER BY updated_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
