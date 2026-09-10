from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .database import Database


MANIFEST_FIELDS = [
    "selection_order",
    "selected_at",
    "strategy",
    "bucket",
    "key",
    "filename",
    "size_bytes",
    "etag",
    "last_modified",
    "planning_period",
    "observation_id",
    "large_slew_counter",
    "small_slew_counter",
    "detector",
    "pipeline_level",
    "pipeline_version",
    "processing_date",
]


def _stratified(candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Greedily maximize detector, small-slew, and observation coverage."""
    remaining = list(candidates)
    chosen: list[dict[str, Any]] = []
    detectors: set[object] = set()
    small_slews: set[object] = set()
    observations: set[object] = set()
    processing_dates: set[object] = set()

    while remaining and len(chosen) < limit:
        best_index = 0
        best_score = -1
        for index, row in enumerate(remaining):
            score = 0
            score += 1000 if row["detector"] not in detectors else 0
            score += 100 if row["small_slew_counter"] not in small_slews else 0
            score += 10 if row["observation_id"] not in observations else 0
            score += 1 if row["processing_date"] not in processing_dates else 0
            if score > best_score:
                best_index = index
                best_score = score
        selected = remaining.pop(best_index)
        chosen.append(selected)
        detectors.add(selected["detector"])
        small_slews.add(selected["small_slew_counter"])
        observations.add(selected["observation_id"])
        processing_dates.add(selected["processing_date"])
    return chosen


def select_objects(
    database: Database,
    *,
    bucket: str,
    planning_period: str | None,
    limit: int,
    strategy: str,
) -> list[dict[str, Any]]:
    candidates = database.current_objects(bucket, planning_period)
    if len(candidates) < limit:
        raise RuntimeError(
            f"Only {len(candidates)} matching current objects are available, "
            f"but the requested limit is {limit}"
        )
    if strategy == "stratified":
        return _stratified(candidates, limit)
    if strategy == "first":
        return candidates[:limit]
    raise ValueError(f"Unknown selection strategy: {strategy}")


def write_manifest(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    strategy: str,
    overwrite: bool = False,
) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"Manifest already exists: {path}. Reuse it, or pass --overwrite "
            "to select a new deterministic set."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    selected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for order, row in enumerate(rows, start=1):
            output = {field: row.get(field, "") for field in MANIFEST_FIELDS}
            output.update(
                selection_order=order,
                selected_at=selected_at,
                strategy=strategy,
            )
            writer.writerow(output)
    temporary.replace(path)


def read_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}; run 'select' first")
    with path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise RuntimeError(f"Manifest is empty: {path}")
    missing = set(MANIFEST_FIELDS) - set(rows[0])
    if missing:
        raise RuntimeError(f"Manifest is missing columns: {', '.join(sorted(missing))}")
    for row in rows:
        row["selection_order"] = int(row["selection_order"])
        row["size_bytes"] = int(row["size_bytes"])
        row["small_slew_counter"] = int(row["small_slew_counter"])
        row["detector"] = int(row["detector"])
    return sorted(rows, key=lambda row: row["selection_order"])
