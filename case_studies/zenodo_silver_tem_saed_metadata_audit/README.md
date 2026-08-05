# Zenodo Silver TEM/SAED Metadata Audit

This case audits the public Zenodo record `10.5281/zenodo.18942976` without downloading its `TEM_SAED.zip` archive.

## Verified result

The live metadata audit completed on 2026-08-05 and confirmed:

- record ID `18942976` and DOI `10.5281/zenodo.18942976`;
- status `published`;
- Zenodo API resource type `image`;
- licence `cc-by-4.0`;
- three-file record inventory;
- `TEM_SAED.zip` exact size `1,417,789,651` bytes;
- archive checksum `md5:c7bda9d495dd0fd657a8fe0332db4f9c`;
- a valid archive content link.

The verified values and GitHub Actions artifact identity are stored in `verified_snapshot.json`.

## Metadata quality flags

The API currently reports `publication_date: 2027-05-10`, which is later than the 2026-08-05 live audit date even though the record status is `published`. The reason is unresolved. The value is preserved as a warning rather than silently corrected.

The API also classifies this multi-file raw experimental record as resource type `image`. That classification is preserved rather than normalized to `dataset`.

These flags do not invalidate the archive checksum, but they limit provenance interpretation until resolved.

## Purpose

The metadata gate pins:

- record identity and publication status;
- Zenodo API resource classification;
- CC BY 4.0 licence;
- exact record file count;
- target archive filename, exact byte count, content link, and MD5 checksum.

The audit generates a bounded archive-acquisition plan. It does not inspect archive members or run an analyzer.

## Scientific boundary

- record identity and file inventory: **Supported**;
- temporal metadata consistency: **Inconclusive**;
- archive member inventory: **Inconclusive**;
- source archive download: not authorized by this metadata-only case;
- source or image artifact upload: prohibited;
- model inference, annotation, cropping, and parameter tuning: prohibited;
- TEM labels, raw status, sample/acquisition lineage, SAED centre, and reciprocal calibration: unresolved;
- external-validation ready: false;
- engineering-decision ready: false;
- analyzer scientific evidence: `Inconclusive`.

## Invocation

```bash
python scripts/audit_zenodo_silver_tem_saed_metadata.py \
  --config case_studies/zenodo_silver_tem_saed_metadata_audit/case_config.json \
  --output outputs/zenodo_silver_tem_saed_metadata_audit
```

Generated artifacts contain metadata and planning information only.
