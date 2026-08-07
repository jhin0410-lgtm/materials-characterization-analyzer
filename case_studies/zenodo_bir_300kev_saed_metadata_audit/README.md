# BIR-MicroED 300 keV metadata audit

## Objective

Audit the Zenodo metadata for record `10.5281/zenodo.10995139` before any large
source transfer or SAED analyzer execution.

The record describes static selected-area electron-diffraction datasets stored in
native `.tvips` files and distributed in six ZIP archives covering three molecular
crystal compounds at 100 K and 293 K. The six archives total roughly 36.5 GB on
the Zenodo landing page.

This case deliberately performs **metadata-only** work first. A large public
archive is not automatically useful scientific evidence.

## Frozen metadata contract

The config pins:

- Zenodo record ID and DOI;
- version `v1`;
- exact record title;
- dataset resource type;
- six archive filenames;
- six repository MD5 values;
- source-description terms for electron diffraction, `.tvips`, and
  `static_diffraction`.

The live audit additionally records the API-declared byte count and trusted
content URL for every archive.

## Reuse boundary

The related article is open access, but an article licence must not be copied onto
the dataset by inference. The audit reads only the Zenodo record's own licence or
rights metadata.

If the dataset-level licence is absent, reuse remains blocked/inconclusive. If a
dataset licence is declared, it is recorded for review but this metadata-only
stage still does not authorize a 36.5 GB download.

## Run

```bash
python scripts/audit_zenodo_bir_300kev_metadata.py \
  --config case_studies/zenodo_bir_300kev_saed_metadata_audit/case_config.json \
  --output outputs/zenodo-bir-300kev-metadata/metadata_snapshot.json
```

The command makes one bounded JSON metadata request to the pinned Zenodo API. It
does not download any source archive, read `.tvips` bytes, preprocess a pattern,
run SAED inference, index a phase, tune a parameter, or retain source data.

## What a successful metadata audit supports

- record/DOI/version/title identity;
- exact six-archive inventory;
- repository-declared MD5 and byte counts;
- trusted Zenodo content URLs;
- dataset-level licence metadata when actually declared by the record.

## What remains unresolved

- ZIP integrity and member inventory;
- exact `.tvips` member hashes and representation details;
- detector-native intensity preservation;
- detector and microscope metadata;
- immutable sample/acquisition IDs and series independence;
- pattern centre and reciprocal calibration;
- source-author reflection or ring truth;
- verified non-use in analyzer development;
- external-validation or engineering readiness.

## Next bounded action

Only after the metadata/reuse gate is reviewed should a new contract authorize a
bounded archive audit. Because the full collection is roughly 36.5 GB, the next
step should justify which archive or subset addresses a concrete missing SAED
format/calibration/lineage question before transfer. Archives from different
compounds, temperatures, or BIR records must not be pooled merely to increase
sample count.

## Scientific closeout

This audit can support source identity, not SAED scientific validation. Expected
evidence status remains **Inconclusive** until the native member and calibration
requirements are resolved.
