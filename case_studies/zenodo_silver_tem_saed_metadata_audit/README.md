# Zenodo Silver TEM/SAED Metadata Audit

This case audits the public Zenodo record `10.5281/zenodo.18942976` without downloading its 1.4 GB `TEM_SAED.zip` archive.

## Purpose

The first gate is to pin:

- record identity and publication status;
- dataset resource type;
- CC BY 4.0 licence;
- exact record file count;
- target archive filename, exact byte count, content URL, and MD5 checksum.

The audit then generates a bounded archive-acquisition plan. It does not inspect archive members or run an analyzer.

## Scientific boundary

- source archive download: not authorized by this metadata-only case;
- source or image artifact upload: prohibited;
- model inference, annotation, cropping, and parameter tuning: prohibited;
- archive member inventory: incomplete;
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
