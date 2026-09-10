# Acquisition Pipeline Design

## Authority boundaries

- AWS S3 is authoritative for available objects and remote object metadata.
- `catalogs/spherex.sqlite3` is authoritative for local pipeline state.
- Exported catalogs and manifests are human-readable snapshots.
- FITS files are stored separately below `data/`.

## Catalog reconciliation

Each successful scan is transactional. Objects are identified by `(bucket, key)`
and compared using byte size, ETag, and `LastModified`.

- unseen key: `new`
- same key with a changed remote signature: `updated`
- previously current key absent from a successful scan of the same prefix:
  `removed`
- identical signature: unchanged

A failed or interrupted listing never marks unseen objects as removed. Event rows
remain available for auditing in `object_events`.

## Selection

The `stratified` selector is deterministic. It greedily prioritizes previously
unrepresented detectors, small-slew counters, observations, and processing dates.
The saved manifest freezes keys and their remote signatures so a debug run cannot
silently change underneath the user.

## Download states

Typical transitions:

```text
missing -> downloading -> completed
                    \-> failed -> downloading (retry)
existing unmanaged -> verified/adopted -> completed
```

The status record contains the remote signature, local path, attempts, byte count,
timestamps, FITS verification time, SHA-256, and the most recent error.

## Safety and update behavior

- The local path is derived from the S3 key only after traversal checks.
- Transfers write to `<filename>.part`.
- A stale partial file is deleted before a from-scratch retry.
- Size and FITS structure are verified before final installation.
- `os.replace` performs the final atomic installation.
- If an existing final file represents an older remote version, it remains intact
  until the replacement passes verification.
- Superseded FITS copies are not retained, but remote and download events record
  the transition.

## HPC migration

The code is platform-neutral and paths come from TOML. Initial HPC migration
should therefore require only new path/worker settings and a Slurm wrapper. SQLite
is suitable for a single coordinating process; concurrent jobs on multiple nodes
should later use a single writer, per-job manifests, or a server database.
