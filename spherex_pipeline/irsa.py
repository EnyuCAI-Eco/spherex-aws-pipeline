from __future__ import annotations

import csv
import io
import json
import time
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SIA_ENDPOINT = "https://irsa.ipac.caltech.edu/SIA"
SPHEREX_QR2_COLLECTION = "spherex_qr2"
# SIA v2 expresses a position using a circle. This 0.036-arcsec probe is about
# 1/170 of a SPHEREx pixel, so it is effectively a point while avoiding service
# implementations that reject a mathematically zero-radius circle.
POINT_PROBE_RADIUS_DEGREES = 0.00001


@dataclass(frozen=True)
class IrsaImageMatch:
    bucket: str
    key: str
    detector: int | None
    observation_id: str
    center_ra: float
    center_dec: float
    footprint: str
    access_url: str
    estimated_size_bytes: int


def build_point_query_url(ra: float, dec: float, *, max_records: int = 10000) -> str:
    """Build an IRSA SIA v2 query for images intersecting one sky point."""
    if not 0.0 <= ra < 360.0:
        raise ValueError("RA must be in the range [0, 360) degrees")
    if not -90.0 <= dec <= 90.0:
        raise ValueError("Dec must be in the range [-90, 90] degrees")
    if max_records < 1:
        raise ValueError("max_records must be at least 1")

    parameters = {
        "COLLECTION": SPHEREX_QR2_COLLECTION,
        # IRSA tests this tiny probe against the image's spherical footprint,
        # rather than only comparing it with the image center.
        "POS": (
            f"CIRCLE {ra:.12g} {dec:.12g} "
            f"{POINT_PROBE_RADIUS_DEGREES:.12g}"
        ),
        "RESPONSEFORMAT": "CSV",
        "MAXREC": str(max_records),
    }
    return f"{SIA_ENDPOINT}?{urlencode(parameters)}"


def _detector_from_row(row: dict[str, str], key: str) -> int | None:
    instrument = row.get("instrument_name", "")
    marker = "SPHEREx-D"
    if instrument.startswith(marker):
        value = instrument[len(marker) :]
        if value.isdigit():
            return int(value)

    filename = key.rsplit("/", 1)[-1]
    before_instrument = filename.split("_spx_", 1)[0]
    if "D" in before_instrument:
        value = before_instrument.rsplit("D", 1)[-1]
        if value.isdigit():
            return int(value)
    return None


def parse_sia_csv(payload: str) -> list[IrsaImageMatch]:
    matches: list[IrsaImageMatch] = []
    for row in csv.DictReader(io.StringIO(payload)):
        try:
            cloud_access = json.loads(row.get("cloud_access", "") or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("IRSA returned invalid cloud_access metadata") from exc
        aws = cloud_access.get("aws", {})
        bucket = str(aws.get("bucket_name", ""))
        key = str(aws.get("key", ""))
        if not bucket or not key:
            raise RuntimeError(
                "An IRSA SPHEREx result did not include an AWS bucket and key"
            )

        # ObsCore access_estsize is expressed in KiB.
        estimated_size_bytes = int(float(row.get("access_estsize", "0") or 0) * 1024)
        matches.append(
            IrsaImageMatch(
                bucket=bucket,
                key=key,
                detector=_detector_from_row(row, key),
                observation_id=row.get("obs_id", ""),
                center_ra=float(row["s_ra"]),
                center_dec=float(row["s_dec"]),
                footprint=row.get("s_region", ""),
                access_url=row.get("access_url", ""),
                estimated_size_bytes=estimated_size_bytes,
            )
        )
    return sorted(matches, key=lambda match: match.key)


def query_spherex_point(
    ra: float,
    dec: float,
    *,
    max_records: int = 10000,
    timeout: float = 60.0,
    attempts: int = 3,
    opener: Callable[..., object] = urlopen,
) -> list[IrsaImageMatch]:
    """Return QR2 spectral images whose IRSA footprints contain a sky point."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    url = build_point_query_url(ra, dec, max_records=max_records)
    request = Request(url, headers={"User-Agent": "spherex-aws-pipeline/0.1"})
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            with opener(request, timeout=timeout) as response:  # type: ignore[attr-defined]
                payload = response.read().decode("utf-8-sig")
            return parse_sia_csv(payload)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(attempt)

    raise RuntimeError(f"IRSA SIA query failed after {attempts} attempts") from last_error
