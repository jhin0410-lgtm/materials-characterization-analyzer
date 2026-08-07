# BIR-MicroED 300 keV remote TVIPS inventory

## Purpose

Inspect the ZIP **central directory only** for the smallest verified BIR-MicroED
300 keV archive, `AVAAGA_300kV_293K.zip`, without downloading the 3.53 GB ZIP or
any `.tvips` member payload.

This is the next bounded source-audit step after the live metadata gate verified
record identity, six archive identities, repository MD5 values, exact byte counts,
and dataset-level CC BY 4.0 reuse metadata.

## Why central-directory probing comes before download

The current SAED evidence gap is not simply a shortage of bytes. Before source
transfer, we need to know whether the archive contains a usable TVIPS series
structure at all. Established TVIPS readers require the first `_000.tvips` file
because it carries the main stream header; filename inventory can therefore answer
a narrow format-readiness question at far lower transfer cost than a full archive.

Member names still do **not** prove sample identity, acquisition independence,
pattern centre, reciprocal calibration, detector-native intensity preservation,
or reflection truth.

## Bounded transfer contract

The live audit performs exactly two HTTP range reads if the source is a standard
single-disk non-ZIP64 archive:

1. the last 131,072 bytes to locate the ZIP end-of-central-directory record;
2. the exact central-directory byte range declared by that record.

If the server returns HTTP 200 instead of HTTP 206, the command stops before
reading the response body. There is no full-download fallback.

The audit also stops for:

- multi-disk ZIP;
- ZIP64 metadata requiring a separate parser review;
- central directories larger than 64 MiB;
- more than 200,000 members;
- unsafe member paths;
- inconsistent byte-range responses.

## Run

```bash
python scripts/audit_zenodo_bir_300kev_remote_inventory.py \
  --config case_studies/zenodo_bir_300kev_saed_remote_inventory/case_config.json \
  --output outputs/zenodo_bir_300kev_remote_inventory
```

Outputs:

```text
remote_inventory_snapshot.json
remote_member_inventory.csv
```

The CSV records only central-directory metadata such as member path, compressed
and uncompressed byte counts, compression method, CRC-32 metadata, local-header
offset, and TVIPS series filename structure. It contains no member payload.

## Decision after the audit

A useful outcome is evidence that the archive contains one or more TVIPS series
with explicit `_000.tvips` main-header files. That supports a later **selected
header-inspection** experiment, not analyzer validation.

If the central directory has no TVIPS members, no valid `_000` series, requires an
unsupported container variant, or cannot be ranged safely, stop and reassess the
source instead of downloading the full collection.

If the format inventory is viable, the next authorization should remain narrow:
read only the minimum selected TVIPS header/payload range needed to test an
established reader and determine which microscope/detector/axis metadata are
actually present. Quantitative SAED indexing still requires independent evidence
for pattern centre and reciprocal calibration.

## Scientific evidence level

Expected closeout: **Diagnostic**. This stage can establish remote archive member
structure and TVIPS filename-series readiness only. It creates no external
validation, phase-indexing, causal, or engineering-decision evidence.
