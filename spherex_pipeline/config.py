from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Settings:
    project_root: Path
    bucket: str
    region: str
    unsigned: bool
    catalog_prefix: str
    database_path: Path
    export_csv_path: Path
    selection_planning_period: str | None
    selection_limit: int
    selection_strategy: str
    manifest_path: Path
    download_root: Path
    workers: int
    max_attempts: int
    backoff_seconds: float
    verify_fits: bool
    sha256: bool
    log_level: str
    log_file: Path


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"Configuration section [{name}] must be a table")
    return value


def _resolve(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (root / path)


def load_settings(config_path: str | Path) -> Settings:
    path = Path(config_path).expanduser().resolve()
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    aws = _section(data, "aws")
    catalog = _section(data, "catalog")
    selection = _section(data, "selection")
    download = _section(data, "download")
    logging_config = _section(data, "logging")
    root = path.parent

    settings = Settings(
        project_root=root,
        bucket=str(aws.get("bucket", "nasa-irsa-spherex")),
        region=str(aws.get("region", "us-east-1")),
        unsigned=bool(aws.get("unsigned", True)),
        catalog_prefix=str(catalog.get("prefix", "qr2/level2/")),
        database_path=_resolve(root, str(catalog.get("database", "catalogs/spherex.sqlite3"))),
        export_csv_path=_resolve(root, str(catalog.get("export_csv", "catalogs/level2_catalog_current.csv"))),
        selection_planning_period=(
            str(selection["planning_period"])
            if selection.get("planning_period")
            else None
        ),
        selection_limit=int(selection.get("limit", 10)),
        selection_strategy=str(selection.get("strategy", "stratified")),
        manifest_path=_resolve(root, str(selection.get("manifest", "catalogs/test10_manifest.csv"))),
        download_root=_resolve(root, str(download.get("root", "data"))),
        workers=int(download.get("workers", 2)),
        max_attempts=int(download.get("max_attempts", 3)),
        backoff_seconds=float(download.get("backoff_seconds", 2.0)),
        verify_fits=bool(download.get("verify_fits", True)),
        sha256=bool(download.get("sha256", True)),
        log_level=str(logging_config.get("level", "INFO")).upper(),
        log_file=_resolve(root, str(logging_config.get("file", "logs/spherex_pipeline.log"))),
    )

    if settings.selection_limit < 1:
        raise ValueError("selection.limit must be at least 1")
    if settings.workers < 1:
        raise ValueError("download.workers must be at least 1")
    if settings.max_attempts < 1:
        raise ValueError("download.max_attempts must be at least 1")
    if not settings.catalog_prefix.endswith("/"):
        raise ValueError("catalog.prefix must end with '/'")
    return settings
