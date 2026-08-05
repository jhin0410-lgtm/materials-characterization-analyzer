# Zenodo Silver TEM/SAED Archive Audit

This case performs the bounded follow-up to the metadata audit for Zenodo record `10.5281/zenodo.18942976`.

## Scope

The workflow transiently downloads exactly one pinned file:

- `TEM_SAED.zip`
- expected bytes: `1,417,789,651`
- expected MD5: `c7bda9d495dd0fd657a8fe0332db4f9c`

It then:

- computes archive SHA-256;
- validates the ZIP container;
- rejects unsafe paths, duplicate normalized paths, symlinks, encryption, unsupported compression, excessive member sizes, excessive compression ratios, and configured byte/member limits;
- streams every member to verify CRC and compute SHA-256 without extracting source content into the evidence directory;
- records suffix, representation class, filename role cues, sizes, compression, CRC, and SHA-256;
- deletes the source archive before evidence upload.

## Frozen limits

- archive bytes: at most `1,600,000,000`;
- members: at most `50,000`;
- total uncompressed bytes: at most `20,000,000,000`;
- one member: at most `5,000,000,000` bytes;
- one-member compression ratio: at most `500`;
- total member hashing budget: `20,000,000,000` bytes.

## Scientific boundary

This is archive and representation validation, not analyzer performance validation.

Prohibited in this case:

- retaining or uploading source archives or image members;
- cropping, normalization, smoothing, or other image preprocessing;
- TEM segmentation inference;
- SAED peak detection or calibration;
- annotation;
- parameter tuning;
- external-validation or engineering-readiness promotion.

Even if every checksum passes, scientific validation remains blocked until sample/acquisition lineage, raw status, independent TEM labels, static-SAED acquisition, pattern centre, and reciprocal calibration are established.

## Invocation

```bash
python scripts/audit_zenodo_silver_tem_saed_archive.py \
  --config case_studies/zenodo_silver_tem_saed_archive_audit/case_config.json \
  --output outputs/zenodo_silver_tem_saed_archive_audit
```

The command requires network access and sufficient temporary disk space. Generated artifacts are metadata-only.
