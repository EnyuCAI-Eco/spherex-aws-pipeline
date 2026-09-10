from __future__ import annotations

import hashlib
from pathlib import Path


REQUIRED_LEVEL2_HDUS = {
    "PRIMARY",
    "IMAGE",
    "FLAGS",
    "VARIANCE",
    "ZODI",
    "PSF",
    "WCS-WAVE",
}


def verify_level2_fits(path: Path) -> None:
    try:
        from astropy.io import fits
    except ImportError as exc:
        raise RuntimeError(
            "astropy is required for FITS verification. Install requirements.txt "
            "in the active environment."
        ) from exc

    with fits.open(path, mode="readonly", memmap=True) as hdus:
        hdus.verify("exception")
        names = {str(hdu.name).upper() for hdu in hdus}
        missing = REQUIRED_LEVEL2_HDUS - names
        if missing:
            raise ValueError(
                "FITS file is missing expected Level 2 HDUs: "
                + ", ".join(sorted(missing))
            )


def sha256_file(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()
