from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .config import Settings
from .database import Database
from .s3_access import make_s3_client
from .verification import sha256_file, verify_level2_fits


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlanItem:
    row: dict[str, Any]
    local_path: Path
    action: str
    reason: str


def format_bytes(value: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.2f} {unit}"
        amount /= 1024
    raise AssertionError("unreachable")


def safe_local_path(root: Path, key: str) -> Path:
    pure = PurePosixPath(key)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"Unsafe S3 key for local storage: {key!r}")
    resolved_root = root.resolve()
    target = resolved_root.joinpath(*pure.parts).resolve()
    try:
        target.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"S3 key escapes the download root: {key!r}") from exc
    return target


def _same_signature(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        int(left["size_bytes"]) == int(right["size_bytes"])
        and str(left["etag"]) == str(right["etag"])
        and str(left["last_modified"]) == str(right["last_modified"])
    )


def build_plan(
    settings: Settings,
    database: Database,
    manifest_rows: list[dict[str, Any]],
) -> list[PlanItem]:
    plan: list[PlanItem] = []
    for row in manifest_rows:
        if row["bucket"] != settings.bucket:
            raise RuntimeError(
                f"Manifest bucket {row['bucket']!r} does not match configured "
                f"bucket {settings.bucket!r}"
            )
        target = safe_local_path(settings.download_root, str(row["key"]))
        remote = database.get_remote_object(settings.bucket, str(row["key"]))
        if remote is None or not int(remote["is_current"]):
            plan.append(PlanItem(row, target, "blocked", "object is not current in catalog"))
            continue
        if not _same_signature(row, remote):
            plan.append(PlanItem(row, target, "blocked", "manifest is stale; rerun select"))
            continue

        record = database.get_download(settings.bucket, str(row["key"]))
        target_size = target.stat().st_size if target.exists() else None
        record_is_current = bool(
            record
            and int(record["remote_size_bytes"]) == int(row["size_bytes"])
            and str(record["remote_etag"]) == str(row["etag"])
            and str(record["remote_last_modified"]) == str(row["last_modified"])
        )
        if (
            record_is_current
            and record["status"] == "completed"
            and target_size == int(row["size_bytes"])
        ):
            plan.append(PlanItem(row, target, "skip", "already complete and current"))
        elif target_size == int(row["size_bytes"]):
            plan.append(PlanItem(row, target, "verify", "existing file needs adoption/verification"))
        else:
            reason = "file is missing" if target_size is None else "local size differs from catalog"
            plan.append(PlanItem(row, target, "download", reason))
    return plan


def summarize_plan(plan: list[PlanItem]) -> dict[str, int]:
    summary = {"download": 0, "verify": 0, "skip": 0, "blocked": 0, "bytes": 0}
    for item in plan:
        summary[item.action] += 1
        if item.action == "download":
            summary["bytes"] += int(item.row["size_bytes"])
    return summary


def _record(
    database: Database,
    item: PlanItem,
    status: str,
    *,
    message: str | None = None,
    increment_attempts: bool = False,
    bytes_downloaded: int = 0,
    sha256: str | None = None,
    verified: bool = False,
) -> None:
    row = item.row
    database.set_download_status(
        bucket=str(row["bucket"]),
        key=str(row["key"]),
        remote_size_bytes=int(row["size_bytes"]),
        remote_etag=str(row["etag"]),
        remote_last_modified=str(row["last_modified"]),
        local_path=str(item.local_path),
        status=status,
        message=message,
        increment_attempts=increment_attempts,
        bytes_downloaded=bytes_downloaded,
        sha256=sha256,
        verified=verified,
    )


def _verify_and_hash(path: Path, settings: Settings) -> str | None:
    if settings.verify_fits:
        verify_level2_fits(path)
    return sha256_file(path) if settings.sha256 else None


def _adopt_existing(item: PlanItem, settings: Settings, database: Database) -> tuple[str, str]:
    try:
        digest = _verify_and_hash(item.local_path, settings)
        _record(
            database,
            item,
            "completed",
            message="adopted existing verified file",
            bytes_downloaded=int(item.row["size_bytes"]),
            sha256=digest,
            verified=settings.verify_fits,
        )
        return ("completed", str(item.row["key"]))
    except Exception as exc:
        _record(database, item, "failed", message=f"existing-file verification failed: {exc}")
        return ("failed", str(item.row["key"]))


def _download_one(item: PlanItem, settings: Settings, database: Database) -> tuple[str, str]:
    client = make_s3_client(settings)
    target = item.local_path
    partial = target.with_suffix(target.suffix + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)

    last_error = "unknown download error"
    for attempt in range(1, settings.max_attempts + 1):
        try:
            if partial.exists():
                partial.unlink()
            _record(
                database,
                item,
                "downloading",
                message=f"attempt {attempt} of {settings.max_attempts}",
                increment_attempts=True,
            )
            expected_etag = str(item.row["etag"])
            response = client.get_object(
                Bucket=str(item.row["bucket"]),
                Key=str(item.row["key"]),
                IfMatch=f'"{expected_etag}"',
            )
            response_etag = str(response.get("ETag", "")).strip('"')
            if response_etag != expected_etag:
                raise IOError(
                    f"ETag mismatch: manifest has {expected_etag}, response has "
                    f"{response_etag}"
                )
            response_size = int(response["ContentLength"])
            if response_size != int(item.row["size_bytes"]):
                raise IOError(
                    f"response size mismatch: expected {item.row['size_bytes']}, "
                    f"server reported {response_size}"
                )
            body = response["Body"]
            try:
                with partial.open("wb") as handle:
                    while block := body.read(8 * 1024 * 1024):
                        handle.write(block)
            finally:
                body.close()
            actual_size = partial.stat().st_size
            expected_size = int(item.row["size_bytes"])
            if actual_size != expected_size:
                raise IOError(
                    f"size mismatch: expected {expected_size} bytes, received {actual_size}"
                )
            digest = _verify_and_hash(partial, settings)
            os.replace(partial, target)
            _record(
                database,
                item,
                "completed",
                message="downloaded and verified",
                bytes_downloaded=expected_size,
                sha256=digest,
                verified=settings.verify_fits,
            )
            return ("completed", str(item.row["key"]))
        except Exception as exc:
            last_error = str(exc)
            _record(database, item, "failed", message=last_error)
            LOGGER.warning(
                "Download attempt %d/%d failed for %s: %s",
                attempt,
                settings.max_attempts,
                item.row["key"],
                exc,
            )
            if attempt < settings.max_attempts:
                time.sleep(settings.backoff_seconds * (2 ** (attempt - 1)))
    return ("failed", f"{item.row['key']}: {last_error}")


def execute_plan(
    plan: list[PlanItem],
    settings: Settings,
    database: Database,
) -> dict[str, int]:
    results = {"completed": 0, "failed": 0, "skipped": 0, "blocked": 0}
    actionable = [item for item in plan if item.action in {"download", "verify"}]
    results["skipped"] = sum(item.action == "skip" for item in plan)
    results["blocked"] = sum(item.action == "blocked" for item in plan)
    for item in plan:
        if item.action == "blocked":
            LOGGER.error("Blocked %s: %s", item.row["key"], item.reason)

    with ThreadPoolExecutor(max_workers=settings.workers) as executor:
        futures = {
            executor.submit(
                _adopt_existing if item.action == "verify" else _download_one,
                item,
                settings,
                database,
            ): item
            for item in actionable
        }
        for future in as_completed(futures):
            item = futures[future]
            try:
                status, detail = future.result()
            except Exception as exc:
                status, detail = "failed", f"{item.row['key']}: {exc}"
                _record(database, item, "failed", message=str(exc))
            results[status] += 1
            LOGGER.info("%s: %s", status.upper(), detail)
    return results


def verify_manifest_files(
    plan: list[PlanItem],
    settings: Settings,
    database: Database,
) -> dict[str, int]:
    results = {"verified": 0, "failed": 0, "missing": 0, "blocked": 0}
    for item in plan:
        if item.action == "blocked":
            LOGGER.error("Verification blocked for %s: %s", item.row["key"], item.reason)
            results["blocked"] += 1
            continue
        if not item.local_path.exists():
            results["missing"] += 1
            continue
        if item.local_path.stat().st_size != int(item.row["size_bytes"]):
            _record(database, item, "failed", message="verification size mismatch")
            results["failed"] += 1
            continue
        status, _ = _adopt_existing(item, settings, database)
        results["verified" if status == "completed" else "failed"] += 1
    return results
