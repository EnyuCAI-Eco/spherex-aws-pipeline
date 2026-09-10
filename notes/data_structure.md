# SPHEREx Data Structure Notes

## AWS structure

```text
s3://nasa-irsa-spherex/
└── qr2/
    └── level2/
```

## Level 2 filename format (official IRSA convention)

Example:

```text
level2_2025W17_4B_0001_1D2_spx_l2b-v20-2025-240.fits
```

Parsed components:

- `planning_period`: `2025W17_4B`
- `large_slew_counter`: `0001`
- `small_slew_counter`: `1`
- `detector`: `2`
- canonical `observation_id`: `2025W17_4B_0001.1`
- `pipeline_level`: `l2b`
- `pipeline_version`: `v20`
- `processing_date`: `2025-240` (year and day-of-year)

The `D` in `1D2` separates the small-slew counter (`1`) from detector (`2`).
It is not part of the detector identifier.

## FITS HDU structure

- PRIMARY
- IMAGE
- FLAGS
- VARIANCE
- ZODI
- PSF
- WCS-WAVE

## Managed local path

The downloader mirrors the S3 key below `data/`:

```text
data/qr2/level2/<planning_period>/<pipeline>/<detector>/<filename>
```

## Pipeline boundary

```text
S3 listing -> SQLite catalog -> saved manifest -> safe download -> verification
```

The current project ends at verified data acquisition. Scientific processing and
analysis are intentionally outside this phase.

## Official references

- SPHEREx mission and archive: https://irsa.ipac.caltech.edu/Missions/spherex.html
- SPHEREx Explanatory Supplement: https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp_QR.pdf
- IRSA cloud access: https://irsa.ipac.caltech.edu/cloud_access/
