# BIR-MicroED 300 keV remote TVIPS inventory

## Purpose

Inspect the ZIP **central directory only** for the smallest verified BIR-MicroED
300 keV archive, `AVAAGA_300kV_293K.zip`, without downloading the 3.53 GB ZIP or
any `.tvips` member payload.

This follows the live metadata gate that verified record identity, six archive
identities, repository MD5 values, exact byte counts, and dataset-level CC BY 4.0
reuse metadata.

## Why central-directory probing comes before download

The current SAED evidence gap is not simply a shortage of bytes. Before source
transfer, we need to know whether the archive contains a TVIPS structure that an
established reader can plausibly consume. HyperSpy documents split TVIPS streams
as files ending `_xyz.tvips`, with `_000.tvips` carrying the essential main stream
header. Filename inventory can test compatibility with that convention at far
lower transfer cost than a full archive.

Member names still do **not** prove sample identity, acquisition independence,
pattern centre, reciprocal calibration, detector-native intensity preservation,
or reflection truth. Absence of `_000` in a filename also does not prove an
internal TVIPS header is absent; that requires member-payload/header evidence.

## Bounded transfer contract

The live audit performs exactly two HTTP range reads for a standard single-disk
non-ZIP64 archive:

1. the last 131,072 bytes to locate the ZIP end-of-central-directory record;
2. the exact central-directory byte range declared by that record.

If the server returns HTTP 200 instead of HTTP 206, the command stops before
reading the response body. There is no full-download fallback.

The audit also stops for multi-disk ZIP, ZIP64 metadata requiring separate review,
a central directory larger than 64 MiB, more than 200,000 members, unsafe member
paths, or inconsistent byte-range responses.

## Verified live result — 2026-08-07

The pinned live source result is in:

```text
verified_remote_inventory_snapshot.json
```

For `AVAAGA_300kV_293K.zip`:

- archive size: `3,527,509,304` bytes;
- remote bytes read: `131,788` bytes total;
- central directory: `716` bytes;
- ZIP members: `5` total — one directory and four `.tvips` files;
- `.tvips` member count: `4`;
- conventional `_xyz.tvips` split-stream members: `0`;
- `_000.tvips` split-stream main files: `0`;
- full archive downloaded: **no**;
- TVIPS member payload read: **no**.

The four member paths are:

```text
AVAAGA_300kV_293K/AVAAGA-dry_static_diffraction_300kV_293K_1fps_series1.tvips
AVAAGA_300kV_293K/AVAAGA-dry_static_diffraction_300kV_293K_1fps_series2.tvips
AVAAGA_300kV_293K/AVAAGA-dry_static_diffraction_300kV_293K_1fps_series3.tvips
AVAAGA_300kV_293K/AVAAGA-dry_static_diffraction_300kV_293K_1fps_series4.tvips
```

Therefore:

- TVIPS member presence: **Supported**;
- HyperSpy documented split-stream filename compatibility: **Unsupported**;
- internal TVIPS header validity: **Inconclusive**;
- sample/acquisition lineage: **Inconclusive**;
- pattern centre and reciprocal calibration: **Inconclusive**;
- external-validation readiness: **Inconclusive**.

This is exactly why a full 3.53 GB download is not currently justified merely to
"try the reader".

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

The CSV contains central-directory metadata only: member path, compressed and
uncompressed sizes, compression method, repository CRC-32 metadata, local-header
offset, and TVIPS filename-structure diagnostics.

## Next decision

Do **not** infer that the four files are invalid TVIPS containers solely because
they lack the documented `_000` naming convention. The next useful evidence, if
pursued, is a separately authorized **minimal member-prefix/header probe** for one
selected `.tvips` member. That experiment should recover only enough decompressed
prefix bytes to compare the internal header with an established TVIPS parser
contract.

If the header is unsupported or lacks the needed detector/axis metadata, stop
rather than downloading the rest of the 36.47 GB collection. If the header is
usable, any quantitative SAED validation still requires independent evidence for
pattern centre, reciprocal calibration, acquisition lineage, and reference
reflection truth.

## Scientific evidence level

**Diagnostic.** This stage establishes remote archive/member structure and a
negative filename-compatibility result for the documented HyperSpy split-stream
convention. It creates no analyzer-performance, phase-indexing, causal,
external-validation, or engineering-decision evidence.
