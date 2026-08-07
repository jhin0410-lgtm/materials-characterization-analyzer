# SrTiO3 SAED Zenodo metadata audit

## Purpose

Audit Zenodo record `10.5281/zenodo.20300700` before downloading `SAED.zip` or either
multi-gigabyte 4D-STEM array.

The landing page describes the record as datasets for *Nanoscale Polar Landscapes in
Quantum Paraelectric SrTiO3* and currently exposes four files:

- `4D_35K.npy`;
- `4D_69K.npy`;
- `Kikuchi_COM.ipynb`;
- `SAED.zip`.

This stage verifies only record identity, dataset rights metadata and exact repository
file identity/MD5. It does not infer the representation inside `SAED.zip`.

## Why this comes before archive access

`SAED.zip` may contain raw static diffraction patterns, processed arrays, rendered
images, mixed outputs, or other representations. The filename alone cannot establish
which interpretation is scientifically valid.

Likewise, the two raw 4D-STEM arrays are a separate modality and temperature condition.
They must not be downloaded or pooled merely to increase an apparent SAED sample count.

## Run

```bash
python scripts/audit_zenodo_srtio3_saed_metadata.py \
  --config case_studies/zenodo_srtio3_saed_metadata_audit/case_config.json \
  --output outputs/zenodo_srtio3_saed_metadata_audit/metadata_snapshot.json
```

## Current decision boundary

A successful metadata audit can support a subsequent **SAED.zip-only** bounded archive
inventory if dataset-level reuse terms are explicitly present. It does not authorize:

- 4D-STEM downloads;
- pixel-array access;
- analyzer inference;
- phase indexing;
- parameter tuning;
- external-validation or engineering claims.

The next archive stage should determine member representation, pattern count, identity,
independence, dtype/shape metadata and whether centre/calibration information is embedded
or externally traceable.
