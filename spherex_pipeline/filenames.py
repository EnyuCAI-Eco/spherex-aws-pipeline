from __future__ import annotations

import re
from pathlib import PurePosixPath

from .models import ParsedFilename


# Official IRSA example:
# level2_2025W22_2B_0001_1D3_spx_l2b-v4-2025-152.fits
# Here "1" is the small-slew counter and "3" is the detector number.
LEVEL2_PATTERN = re.compile(
    r"^"
    r"(?P<product>level2)_"
    r"(?P<planning_period>\d{4}W\d{1,2}_[A-Z0-9]+)_"
    r"(?P<large_slew_counter>\d+)_"
    r"(?P<small_slew_counter>\d+)D(?P<detector>[1-6])_"
    r"(?P<instrument>spx)_"
    r"(?P<pipeline_level>l2[a-z])-"
    r"(?P<pipeline_version>v\d+)-"
    r"(?P<processing_year>\d{4})-(?P<processing_doy>\d{3})"
    r"\.fits$"
)


def parse_level2_filename(filename_or_key: str) -> ParsedFilename | None:
    """Parse an official SPHEREx Level 2 filename, returning None if unmatched."""
    filename = PurePosixPath(filename_or_key).name
    match = LEVEL2_PATTERN.fullmatch(filename)
    if match is None:
        return None

    values = match.groupdict()
    return ParsedFilename(
        filename=filename,
        product=values["product"],
        planning_period=values["planning_period"],
        large_slew_counter=values["large_slew_counter"],
        small_slew_counter=int(values["small_slew_counter"]),
        detector=int(values["detector"]),
        instrument=values["instrument"],
        pipeline_level=values["pipeline_level"],
        pipeline_version=values["pipeline_version"],
        processing_date=(
            f"{values['processing_year']}-{values['processing_doy']}"
        ),
    )
