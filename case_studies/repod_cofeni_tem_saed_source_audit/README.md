# RepOD CoFeNi TEM/HRTEM/SAED Source Audit

This case performs a live, checksum-bound audit of RepOD dataset `10.18150/SIOWH6` version 1.0.

## Scope

The audit is limited to:

- `TEM_SAED.zip`;
- `HRTEM_SAED.zip`;
- `HAADF_STEM.tif`.

The workflow verifies the released record, licence, repository MD5 values, downloaded byte counts, archive integrity, safe member paths, member SHA-256 values, file formats, image dimensions, and embedded metadata keys.

## Scientific boundary

This is a source audit, not analyzer validation. The files are a different material domain (CoFeNi rather than cobalt oxide), contain no independent TEM segmentation labels, and do not yet provide member-level immutable sample/acquisition lineage or traceable SAED pattern centre and reciprocal calibration.

Consequently:

- source files are downloaded only into a transient directory;
- no source archive or image is uploaded as an artifact;
- no model inference, annotation, cropping, or parameter tuning is performed;
- the analyzer scientific evidence remains `Inconclusive`;
- `external_validation_ready` and `engineering_decision_ready` remain false.

## Local invocation

```bash
python scripts/audit_repod_cofeni_tem_saed.py \
  --config case_studies/repod_cofeni_tem_saed_source_audit/case_config.json \
  --output outputs/repod_cofeni_tem_saed_source_audit
```

The command requires network access to the public RepOD API. Generated evidence is metadata-only.
