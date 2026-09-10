# SPHEREx AWS Data Pipeline

> 如果这是第一次使用新程序，请先阅读中文的
> [简明使用说明](notes/项目使用说明_简明版.md)。它解释了新旧程序的对应关系、
> 日常命令，以及目前可以暂时忽略的文件。

A reliable, configuration-driven pipeline for cataloging and downloading public
SPHEREx Quick Release 2 Level 2 FITS products from the IRSA AWS Open Data bucket.
The current phase is data acquisition engineering; no scientific analysis is
performed.

## What the pipeline does

1. Lists S3 objects anonymously with pagination.
2. Parses the official Level 2 filename convention.
3. Reconciles cloud metadata with an SQLite catalog.
4. Records new, updated, and no-longer-listed objects.
5. Selects a deterministic, detector-diverse test set.
6. Saves the exact selection as a reusable CSV manifest.
7. Estimates transfer volume before downloading.
8. Downloads through `.part` files, verifies them, and atomically installs them.
9. Tracks attempts, failures, remote versions, FITS verification, and SHA-256.

The SQLite database is the authoritative machine state. CSV files are exports or
saved selections, not the source of truth.

## Development background

Enyu Cai first worked through the companion practice scripts with step-by-step
GPT guidance. After defining the acquisition requirements, Enyu asked GPT-5.6 Sol
to implement this modular version and exercise it on a fixed set of 10 FITS files.
The project currently supports data acquisition, not scientific analysis.

## Quick start from GitHub (WSL or Linux)

From the root of a fresh checkout:

```bash
conda create -n spherex python=3.11 -y
conda activate spherex
python -m pip install -r requirements.txt
python -m spherex_pipeline catalog update --prefix qr2/level2/2025W17_4B/
python -m spherex_pipeline download --dry-run
python -m spherex_pipeline download
python -m spherex_pipeline verify
python -m spherex_pipeline status
```

The repository includes the fixed `catalogs/test10_manifest.csv`; the SQLite
database and FITS data are generated locally. If the public archive has changed
since this manifest was created, inspect the changes and run
`python -m spherex_pipeline select --overwrite` to create a current selection.
This intentionally changes the saved snapshot. Ten files occupy about 683 MiB.

Both stages were developed and run in WSL. The Python workflow should transfer
readily to Linux HPC with the same dependencies and appropriate storage paths.
HPC execution has not yet been validated: outbound S3 access, the batch scheduler,
and SQLite behavior on the site's filesystem still need checking. Use one
coordinating process for the SQLite database.

Known scope limits: this is an initial acquisition implementation, with a
10-file integration test. It does not yet provide scheduled monitoring or
distributed downloads. FITS structural checks and locally computed SHA-256
values do not prove that an unmanaged existing file matches the remote content.
In particular, a same-size old file can currently be adopted; review this path
before relying on automatic replacement of previously downloaded versions.

## Original local environment

From WSL:

```bash
cd /mnt/c/Users/26823/Desktop/SPHEREx_project
/home/eco/miniconda3/bin/conda run -n spherex python -m spherex_pipeline --help
```

The application requires Python 3.11 or newer, `boto3`, and `astropy`. To install
the declared dependencies in an activated environment:

```bash
python -m pip install -r requirements.txt
```

## Configuration

All normal settings are in `config.toml`. Paths are resolved relative to that
file, which makes execution independent of the current shell directory and eases
later migration to HPC storage.

The checked-in test configuration selects 10 files from `2025W17_4B`, uses two
download workers, performs FITS validation, and computes SHA-256.

## Standard workflow

Run these commands from the project root.

### 1. Update catalog metadata

Full configured QR2 Level 2 prefix:

```bash
python -m spherex_pipeline catalog update
```

Small integration-test prefix:

```bash
python -m spherex_pipeline catalog update \
  --prefix qr2/level2/2025W17_4B/
```

S3 does not offer a server-side "modified since" filter for `ListObjectsV2`, so
each update lists the selected prefix and incrementally reconciles those results
with SQLite. FITS contents are not downloaded during this step.

### 2. Export a human-readable current catalog

```bash
python -m spherex_pipeline catalog export
```

### 3. Create the fixed 10-file test manifest

```bash
python -m spherex_pipeline select
```

An existing manifest is protected from accidental replacement. Use
`--overwrite` only when intentionally generating a new deterministic selection.

### 4. Preview downloads and volume

```bash
python -m spherex_pipeline download --dry-run
```

### 5. Download safely

```bash
python -m spherex_pipeline download
```

The final local layout mirrors S3 below `data/`, for example:

```text
data/qr2/level2/2025W17_4B/l2b-v20-2025-240/2/example.fits
```

### 6. Inspect status or re-verify files

```bash
python -m spherex_pipeline status
python -m spherex_pipeline verify
```

Re-running `download` is safe: complete files whose remote signature still
matches are skipped. If the same S3 key changes, the manifest is rejected as
stale until selection is repeated against the updated catalog.

## Filename model

Official example:

```text
level2_2025W22_2B_0001_1D3_spx_l2b-v4-2025-152.fits
```

Important interpretation:

- planning period: `2025W22_2B`
- large-slew counter: `0001`
- small-slew counter: `1`
- detector: `3`
- canonical observation ID: `2025W22_2B_0001.1`
- pipeline level/version: `l2b` / `v4`
- processing date: `2025-152`

## Runtime files

- `catalogs/spherex.sqlite3`: authoritative catalog and download state
- `catalogs/level2_catalog_current.csv`: current-object export
- `catalogs/test10_manifest.csv`: fixed 10-file selection
- `logs/spherex_pipeline.log`: operational log
- `data/qr2/...`: downloaded FITS archive

The original numbered scripts and historical CSV catalogs have been moved to
`C:\Users\26823\Desktop\practice`. They are learning history and are not part of
the supported workflow. The current entry point is `python -m spherex_pipeline`.

## Tests

```bash
python -m unittest discover -s tests -v
```

The tests cover filename semantics, catalog reconciliation, deterministic
selection, and safe local path construction without contacting AWS.

## Official documentation

- [SPHEREx at IRSA](https://irsa.ipac.caltech.edu/Missions/spherex.html)
- [SPHEREx Explanatory Supplement](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp_QR.pdf)
- [IRSA cloud data access](https://irsa.ipac.caltech.edu/cloud_access/)
