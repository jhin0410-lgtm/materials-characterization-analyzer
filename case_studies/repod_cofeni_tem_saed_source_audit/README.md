# RepOD CoFeNi TEM/HRTEM/SAED Source Audit

This case performs a live, checksum-bound audit of RepOD dataset `10.18150/SIOWH6` version 1.0.

## Scope

The audit is limited to:

- `TEM_SAED.zip`;
- `HRTEM_SAED.zip`;
- `HAADF_STEM.tif`.

The workflow verifies the released record, file-level licence, repository MD5 values, downloaded byte counts, archive integrity, safe member paths, member SHA-256 values, file formats, image dimensions, and embedded metadata keys.

## Verified result

The live audit completed successfully on 2026-08-05.

- RepOD record files: 12
- audited source targets: 3
- audited image members: 7
- lossless-capable TIFF raster exports: 7
- native microscopy containers: 0
- rendered JPEG-like rasters: 0
- SAED-named members: 3
- TEM/HRTEM-named members: 2
- source archives or images retained in evidence: 0

The checksum-bound result is recorded in `verified_snapshot.json`. The associated GitHub Actions metadata-only artifact is identified there by run ID, artifact ID, and artifact digest.

## Scientific closeout

### Source audit

**Supported.** Record version, file-level CC BY 4.0 licence, repository MD5 values, computed SHA-256 values, ZIP integrity, and member identities were verified.

### Analyzer validation

**Inconclusive.** This is a source audit, not analyzer performance validation.

The files are a different material domain (CoFeNi rather than cobalt oxide), contain no independent TEM segmentation labels, and do not provide:

- native detector containers or confirmed raw-detector status;
- immutable member-level sample and acquisition lineage;
- verified acquisition independence;
- member-level accelerating voltage, detector, camera length, or pixel geometry;
- a traceable SAED pattern centre;
- reciprocal calibration;
- source-bound reflection assignments.

Consequently:

- source files are downloaded only into a transient directory;
- no source archive or image is uploaded as an artifact;
- no model inference, annotation, cropping, or parameter tuning is performed;
- the analyzer scientific evidence remains `Inconclusive`;
- intake is `accepted_for_bounded_diagnostic_only`;
- `external_validation_ready` and `engineering_decision_ready` remain false.

## Local invocation

```bash
python scripts/audit_repod_cofeni_tem_saed.py \
  --config case_studies/repod_cofeni_tem_saed_source_audit/case_config.json \
  --output outputs/repod_cofeni_tem_saed_source_audit
```

The command requires network access to the public RepOD API. Generated evidence is metadata-only.
