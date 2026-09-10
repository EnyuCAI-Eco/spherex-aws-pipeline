# Acquisition Manager Implementation Record

Date: 2026-09-08

## Added source files

- `spherex_pipeline/__init__.py`: package metadata
- `spherex_pipeline/__main__.py`: module entry point
- `spherex_pipeline/cli.py`: command-line interface
- `spherex_pipeline/config.py`: TOML settings and portable path resolution
- `spherex_pipeline/models.py`: structured filename and S3 object models
- `spherex_pipeline/filenames.py`: official Level 2 filename parser
- `spherex_pipeline/s3_access.py`: anonymous S3 client and paginated listing
- `spherex_pipeline/catalog.py`: catalog update orchestration
- `spherex_pipeline/database.py`: SQLite schema and transactional state changes
- `spherex_pipeline/selection.py`: deterministic selection and CSV manifests
- `spherex_pipeline/downloader.py`: planning, retries, conditional transfer, and status
- `spherex_pipeline/verification.py`: Level 2 HDU and SHA-256 verification

## Added configuration and project files

- `config.toml`: QR2 Level 2, fixed 10-file test, two workers, FITS and SHA checks
- `requirements.txt`: boto3 and Astropy runtime dependencies
- `.gitignore`: runtime databases, logs, FITS files, and partial downloads
- `README.md`: installation, workflow, commands, safety model, and references
- `notes/pipeline_design.md`: catalog, selection, download, and HPC design decisions
- `notes/implementation_2026-09-08.md`: this implementation record

## Added tests

- `tests/test_filenames.py`
- `tests/test_database.py`
- `tests/test_selection.py`
- `tests/test_downloader.py`

The eight tests cover official filename semantics, object reconciliation,
download invalidation after cloud changes, deterministic detector coverage, path
traversal rejection, ETag-conditional transfer, and atomic file installation.

## Modified existing files

- `scripts/03_parse_catalog.py`: corrected `1D2` into small-slew `1` and detector
  `2`; added canonical observation IDs and project-root-safe paths; now delegates
  parsing to the main package.
- `notes/data_structure.md`: corrected the official naming model and documented
  managed local paths.
- `notes/project_status.md`: replaced the obsolete next-step description with
  the completed implementation and integration-test state.
- `catalogs/level2_catalog_parsed.csv`: regenerated all 10,237 rows with the
  corrected parser; zero filenames were unmatched.

## Added runtime artifacts

- `catalogs/spherex.sqlite3`: authoritative catalog, scan events, downloads, and
  download event history
- `catalogs/level2_catalog_current.csv`: 10,237-row current-object export
- `catalogs/test10_manifest.csv`: frozen, reproducible 10-file selection
- `logs/spherex_pipeline.log`: catalog and transfer log
- `data/qr2/level2/...`: 10 verified FITS files mirroring their S3 keys

## Moved and removed data

- The original file in `data/test/` was moved into its managed S3-mirror path,
  verified, hashed, and adopted. It was not downloaded a second time.
- One 16 MiB random temporary fragment created by the original boto3 transfer
  helper was removed after that transfer stalled.
- The downloader was changed to a controlled streaming GET with `If-Match`, so
  future partial files use the predictable `.fits.part` suffix.
- No complete FITS file was deleted.

## Later archive cleanup

The five numbered practice scripts, the two historical CSV catalogs, and the
empty legacy `data/test/` directory were later moved out of the active project to
`C:\Users\26823\Desktop\practice`. The active pipeline does not depend on them.

## Integration results

- test prefix: `qr2/level2/2025W17_4B/`
- objects: 10,237
- parsed: 10,237
- selected and downloaded: 10 FITS
- total: 716,342,400 bytes (683.16 MiB)
- detectors: 1–6
- small-slew counters: 1–4
- processing dates: `2025-240`, `2025-241`
- FITS and SHA-256 verification: 10 passed, 0 failed
- second S3 scan: 0 new, 0 updated, 0 removed
- repeated download: 10 skipped, 0 bytes transferred
- remaining partial files: 0
- unit tests on Windows Python 3.13 and WSL Python 3.11: 8 passed
