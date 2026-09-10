# SPHEREx AWS Data Pipeline — Project Status

Last updated: 2026-09-08

## Goal

Build a reproducible system that discovers, catalogs, selects, downloads, and
tracks public SPHEREx products from IRSA's AWS S3 archive. The current phase ends
at verified data acquisition; scientific analysis is deferred.

## Environment

- Windows and WSL
- WSL project path: `/mnt/c/Users/26823/Desktop/SPHEREx_project`
- Conda environment: `spherex`
- validated Python version: 3.11.15
- data source: `s3://nasa-irsa-spherex/`
- current product: `qr2/level2/`

## Archived learning prototypes

- `01_list_spherex.py`: initial object listing
- `02_make_catalog.py`: initial CSV catalog
- `03_parse_catalog.py`: CSV filename parsing, now corrected
- `04_download_test.py`: original one-file downloader
- `05_read_fits.py`: initial FITS inspection

These scripts and the two historical CSV catalogs are archived in
`C:\Users\26823\Desktop\practice`. The supported application is
`python -m spherex_pipeline`.

## Completed acquisition manager

- anonymous, paginated S3 listing
- transactional SQLite catalog reconciliation
- new, updated, and removed object event history
- official Level 2 filename parsing
- deterministic stratified selection and persistent CSV manifests
- dry-run volume estimates
- ETag-conditional downloads to predictable `.part` files
- byte-count verification, FITS/HDU verification, SHA-256, and atomic install
- retries, error recording, status summaries, and download history
- stale-download marking when a remote object changes or disappears
- configuration-driven paths and concurrency for later HPC migration

## Official filename correction

For:

```text
level2_2025W17_4B_0001_1D2_spx_l2b-v20-2025-240.fits
```

the correct interpretation is:

- planning period: `2025W17_4B`
- large-slew counter: `0001`
- small-slew counter: `1`
- detector: `2`
- canonical observation ID: `2025W17_4B_0001.1`

The earlier interpretation of `1D2` as one detector field was incorrect.

## Integration test completed

Test prefix: `qr2/level2/2025W17_4B/`

- S3 objects cataloged: 10,237
- filename parse failures: 0
- selected FITS files: 10
- detector coverage: 1 through 6
- small-slew coverage: 1 through 4
- processing dates represented: `2025-240`, `2025-241`
- total FITS volume: 683.16 MiB (716,342,400 bytes)
- FITS/SHA verification: 10 passed, 0 failed
- second catalog scan: 0 new, 0 updated, 0 removed
- second download run: 10 skipped, 0 bytes transferred

The original test FITS was moved from `data/test/` into the managed S3-mirror
layout and adopted after validation, avoiding a duplicate transfer.

## Current project layout

```text
SPHEREx_project/
├── config.toml
├── requirements.txt
├── spherex_pipeline/
├── tests/
├── catalogs/               # SQLite, CSV export, saved manifest
├── data/qr2/...            # managed FITS archive
├── logs/
└── notes/
```

## Next recommended development

1. Run one full `qr2/level2/` metadata scan and measure catalog scale.
2. Define operational selection policies beyond the fixed debug manifest.
3. Add a scheduler only after several manual update cycles succeed.
4. For HPC, place `data/` and possibly the database on suitable storage and add
   a Slurm wrapper. Keep one catalog writer unless migrating state to a server
   database.
