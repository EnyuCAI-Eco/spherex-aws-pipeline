from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import timezone

from .config import Settings
from .filenames import parse_level2_filename
from .models import RemoteObject


def make_s3_client(settings: Settings):
    """Create a public, anonymous S3 client unless credentials are requested."""
    try:
        import boto3
        from botocore import UNSIGNED
        from botocore.config import Config
    except ImportError as exc:
        raise RuntimeError(
            "boto3 is required for S3 access. Install requirements.txt in the "
            "active environment."
        ) from exc

    options: dict[str, object] = {
        "region_name": settings.region,
        "retries": {"max_attempts": 10, "mode": "standard"},
    }
    if settings.unsigned:
        options["signature_version"] = UNSIGNED
    return boto3.client("s3", config=Config(**options))


def iter_s3_objects(settings: Settings, prefix: str) -> Iterator[RemoteObject]:
    client = make_s3_client(settings)
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            modified = item["LastModified"].astimezone(timezone.utc).isoformat()
            algorithms = item.get("ChecksumAlgorithm")
            yield RemoteObject(
                bucket=settings.bucket,
                key=item["Key"],
                size_bytes=int(item["Size"]),
                etag=str(item.get("ETag", "")).strip('"'),
                last_modified=modified,
                storage_class=item.get("StorageClass"),
                checksum_algorithms=(
                    json.dumps(algorithms, separators=(",", ":"))
                    if algorithms
                    else None
                ),
                parsed=parse_level2_filename(item["Key"]),
            )
