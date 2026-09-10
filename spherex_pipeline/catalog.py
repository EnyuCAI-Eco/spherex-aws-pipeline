from __future__ import annotations

import logging

from .config import Settings
from .database import Database
from .s3_access import iter_s3_objects


LOGGER = logging.getLogger(__name__)


def update_catalog(settings: Settings, database: Database, prefix: str) -> dict[str, int]:
    """Perform a complete, paginated listing and reconcile it with local state."""
    scan_id = database.start_scan(settings.bucket, prefix)
    LOGGER.info("Scanning s3://%s/%s", settings.bucket, prefix)
    try:
        counts = database.sync_objects(
            scan_id,
            settings.bucket,
            prefix,
            iter_s3_objects(settings, prefix),
        )
    except Exception as exc:
        database.fail_scan(scan_id, str(exc))
        raise
    LOGGER.info(
        "Catalog scan complete: listed=%d new=%d updated=%d removed=%d",
        counts["listed"],
        counts["new"],
        counts["updated"],
        counts["removed"],
    )
    return counts
