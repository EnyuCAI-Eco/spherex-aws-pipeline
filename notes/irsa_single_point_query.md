# IRSA single-point query prototype

Date: 2026-09-21

## Research question

Given one ICRS sky position `(RA, Dec)`, identify every SPHEREx QR2 Level 2
spectral image that covers the point before downloading any full FITS file.

## Result

IRSA's SIA v2 endpoint can already perform the spatial-footprint lookup:

```text
https://irsa.ipac.caltech.edu/SIA
```

The prototype sends `COLLECTION=spherex_qr2` and represents the target with a
0.036-arcsec circle, about 1/170 of a SPHEREx pixel. The returned rows include:

- `s_region`: the image footprint as an ICRS polygon
- `s_ra`, `s_dec`: the image center
- `s_xel1`, `s_xel2`, and `s_pixel_scale`: image dimensions and pixel scale
- `access_url`: the complete FITS URL
- `cloud_access`: AWS bucket, key, and region

An initial live query at `(210.80225, 54.34894)` returned SPHEREx rows and
directly mapped them to `s3://nasa-irsa-spherex/qr2/level2/...` objects. Later
checks received HTTP 502 responses from IRSA's proxy, including at a different
coordinate, so the command includes retries but should still report a clear
failure when the remote service is temporarily unavailable.

## Why this is better than center-distance alone

For a square image of angular side length `L`, the center-to-corner distance is
approximately `L * sqrt(2) / 2`. This is useful as a cheap candidate filter:

```text
angular separation(target, image center) <= L * sqrt(2) / 2
```

It is not an exact containment test. A point can lie within the circumscribed
circle but outside the rotated square, and flat RA differences become
misleading near the poles. IRSA instead compares the target with the spherical
footprint polygon in `s_region`. Gregory's center-distance idea remains useful
as a local fallback or first-stage filter if the remote service is unavailable.

## Current command

```bash
python -m spherex_pipeline search --ra 210.80225 --dec 54.34894
```

The command is read-only. It prints matching S3 keys and an estimated total
full-FITS volume; it does not create a manifest or download data.

## Next checkpoint

1. Run the command on Gregory's actual science target.
2. Check one returned image against its local FITS WCS as an independent
   validation of IRSA's footprint.
3. Add a deliberate `search -> manifest -> dry-run -> download` bridge.
4. Only build a local header/WCS index if IRSA reliability, reproducibility, or
   offline operation makes that necessary.

## Official references

- IRSA SIA v2: https://irsa.ipac.caltech.edu/ibe/sia.html
- SPHEREx archive search: https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/searching.html
- IRSA cloud access: https://irsa.ipac.caltech.edu/cloud_access/
