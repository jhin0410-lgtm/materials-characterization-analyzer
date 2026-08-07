# SrTiO3 SAED remote archive inventory

## Purpose

Inspect only the ZIP tail and central-directory metadata for the verified
`SAED.zip` file in Zenodo record `10.5281/zenodo.20300700`.

The archive is 25,850,906 bytes. The two 4D-STEM NPY arrays are each
2,621,440,128 bytes and remain outside this audit.

## Why this stage is bounded

The filename `SAED.zip` does not prove whether its contents are raw/static detector
arrays, rendered images, processed exports or mixed representations. Before any
member payload is read, central-directory metadata can establish the exact member
inventory, filename extensions, compressed/uncompressed sizes and ZIP structure at
very low transfer cost.

This can determine the next useful source action without exposing diffraction pixels.

## Access contract

The live audit requests only:

1. the final 131,072 bytes of `SAED.zip` to locate the EOCD record;
2. the exact ZIP central-directory range declared by EOCD.

HTTP 206 is mandatory. HTTP 200 is rejected without a full-download fallback. ZIP64,
multi-disk ZIP, unsafe paths and oversized directories require separate review.

No member payload and no 4D-STEM bytes are accessed.

## Run

```bash
python scripts/audit_zenodo_srtio3_saed_remote_inventory.py \
  --config case_studies/zenodo_srtio3_saed_remote_inventory/case_config.json \
  --output outputs/zenodo_srtio3_saed_remote_inventory
```

Outputs:

```text
remote_inventory_snapshot.json
remote_member_inventory.csv
```

## Interpretation

Member names and extensions are **Diagnostic format evidence** only. For example,
`.tif`, `.png` or `.npy` members would narrow the representation hypothesis but would
not by themselves establish detector-native intensity, pattern independence, pattern
centre, reciprocal calibration, reflection truth or external-validation readiness.

A subsequent selected-member inspection must be separately authorized and should read
the minimum metadata/header bytes capable of changing the scientific decision.
