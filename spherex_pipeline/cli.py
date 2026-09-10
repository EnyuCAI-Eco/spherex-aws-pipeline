from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .catalog import update_catalog
from .config import Settings, load_settings
from .database import Database
from .downloader import (
    build_plan,
    execute_plan,
    format_bytes,
    summarize_plan,
    verify_manifest_files,
)
from .selection import read_manifest, select_objects, write_manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m spherex_pipeline",
        description="Catalog and safely download public SPHEREx S3 data.",
    )
    parser.add_argument("--config", default="config.toml", help="TOML configuration file")
    parser.add_argument("--log-level", help="Override configured logging level")
    commands = parser.add_subparsers(dest="command", required=True)

    catalog = commands.add_parser("catalog", help="Manage the local S3 metadata catalog")
    catalog_commands = catalog.add_subparsers(dest="catalog_command", required=True)
    update = catalog_commands.add_parser("update", help="Scan S3 and update SQLite")
    update.add_argument("--prefix", help="Override the configured S3 prefix")
    export = catalog_commands.add_parser("export", help="Export current objects to CSV")
    export.add_argument("--output", type=Path, help="Override configured CSV output")

    select = commands.add_parser("select", help="Create a reproducible download manifest")
    select.add_argument("--planning-period", help="Override configured planning period")
    select.add_argument("--limit", type=int, help="Override configured file limit")
    select.add_argument("--strategy", choices=("stratified", "first"))
    select.add_argument("--manifest", type=Path, help="Override manifest path")
    select.add_argument("--overwrite", action="store_true", help="Replace an existing manifest")

    download = commands.add_parser("download", help="Download files from a saved manifest")
    download.add_argument("--manifest", type=Path, help="Override manifest path")
    download.add_argument("--dry-run", action="store_true", help="Show work without downloading")
    download.add_argument("--workers", type=int, help="Override configured concurrency")

    status = commands.add_parser("status", help="Summarize recorded download status")
    status.add_argument("--failures", type=int, default=10, help="Number of failures to show")

    verify = commands.add_parser("verify", help="Re-verify files in a manifest")
    verify.add_argument("--manifest", type=Path, help="Override manifest path")
    return parser


def _configure_logging(settings: Settings, override: str | None) -> None:
    settings.log_file.parent.mkdir(parents=True, exist_ok=True)
    level_name = (override or settings.log_level).upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        raise ValueError(f"Unknown log level: {level_name}")
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(settings.log_file, encoding="utf-8"),
        ],
    )


def _resolved_override(value: Path | None, settings: Settings, default: Path) -> Path:
    if value is None:
        return default
    return value if value.is_absolute() else settings.project_root / value


def _print_plan(plan) -> dict[str, int]:
    for item in plan:
        print(
            f"{item.row['selection_order']:>2}  {item.action:<8}  "
            f"{format_bytes(int(item.row['size_bytes'])):>10}  {item.row['key']}"
        )
        if item.action == "blocked":
            print(f"    reason: {item.reason}")
    summary = summarize_plan(plan)
    print(
        "Plan: "
        f"download={summary['download']}, verify={summary['verify']}, "
        f"skip={summary['skip']}, blocked={summary['blocked']}, "
        f"transfer={format_bytes(summary['bytes'])}"
    )
    return summary


def run(args: argparse.Namespace, settings: Settings, database: Database) -> int:
    if args.command == "catalog":
        if args.catalog_command == "update":
            prefix = args.prefix or settings.catalog_prefix
            counts = update_catalog(settings, database, prefix)
            print(
                "Catalog updated: "
                f"listed={counts['listed']}, new={counts['new']}, "
                f"updated={counts['updated']}, removed={counts['removed']}"
            )
            return 0
        output = _resolved_override(args.output, settings, settings.export_csv_path)
        count = database.export_current_csv(output, settings.bucket)
        print(f"Exported {count} current objects to {output}")
        return 0

    if args.command == "select":
        planning_period = args.planning_period or settings.selection_planning_period
        limit = args.limit or settings.selection_limit
        strategy = args.strategy or settings.selection_strategy
        if limit < 1:
            raise ValueError("--limit must be at least 1")
        manifest = _resolved_override(args.manifest, settings, settings.manifest_path)
        selected = select_objects(
            database,
            bucket=settings.bucket,
            planning_period=planning_period,
            limit=limit,
            strategy=strategy,
        )
        write_manifest(manifest, selected, strategy=strategy, overwrite=args.overwrite)
        total = sum(int(row["size_bytes"]) for row in selected)
        detectors = sorted({int(row["detector"]) for row in selected})
        print(
            f"Wrote {len(selected)} objects ({format_bytes(total)}) to {manifest}; "
            f"detectors={detectors}"
        )
        return 0

    if args.command in {"download", "verify"}:
        manifest_arg = getattr(args, "manifest", None)
        manifest = _resolved_override(manifest_arg, settings, settings.manifest_path)
        rows = read_manifest(manifest)
        plan = build_plan(settings, database, rows)
        _print_plan(plan)
        if args.command == "download":
            if args.dry_run:
                return 0
            if args.workers:
                if args.workers < 1:
                    raise ValueError("--workers must be at least 1")
                settings = Settings(**{**settings.__dict__, "workers": args.workers})
            results = execute_plan(plan, settings, database)
            print(
                "Download result: "
                + ", ".join(f"{key}={value}" for key, value in results.items())
            )
            return 1 if results["failed"] or results["blocked"] else 0
        results = verify_manifest_files(plan, settings, database)
        print(
            "Verification result: "
            + ", ".join(f"{key}={value}" for key, value in results.items())
        )
        return 1 if results["failed"] or results["missing"] or results["blocked"] else 0

    if args.command == "status":
        counts = database.download_status_counts()
        if not counts:
            print("No downloads have been recorded yet.")
        for status, count, byte_count in counts:
            print(f"{status:<12} {count:>6} files  {format_bytes(byte_count):>10}")
        failures = database.recent_failures(args.failures)
        if failures:
            print("Recent failures:")
            for failure in failures:
                print(
                    f"- {failure['key']} (attempts={failure['attempts']}): "
                    f"{failure['error']}"
                )
        return 0

    raise AssertionError("unhandled command")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.config)
        _configure_logging(settings, args.log_level)
        database = Database(settings.database_path)
        database.initialize()
        return run(args, settings, database)
    except KeyboardInterrupt:
        print("Interrupted by user", file=sys.stderr)
        return 130
    except Exception as exc:
        logging.getLogger(__name__).exception("Command failed")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
