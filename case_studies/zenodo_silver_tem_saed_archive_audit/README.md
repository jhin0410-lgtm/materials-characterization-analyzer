# Zenodo Silver TEM/SAED Archive Audit

This case performs the bounded archive audit for Zenodo record `10.5281/zenodo.18942976`.

## Verified result

The live audit completed successfully on 2026-08-05.

- archive: `TEM_SAED.zip`
- bytes: `1,417,789,651`
- MD5: `c7bda9d495dd0fd657a8fe0332db4f9c`
- SHA-256: `4569a878be7053c2e84867a5693e9483fd9b937b765ce5e3be15e3f154b5fa12`
- members: `241`
- total uncompressed bytes: `1,732,391,068`
- member CRC and SHA-256 verification: complete
- unsafe paths, duplicate normalized paths, symlinks, encryption, or unsupported compression: not detected
- source archive or source members retained in evidence: no

### Representation inventory

- TIFF raster exports: `212`
- text files: `19`
- DOCX files: `9`
- XLSX files: `1`
- native microscopy containers: `0`
- JPEG-like rendered rasters: `0`

All 241 members are under the top-level `MET/` directory. The folder structure primarily encodes synthesis conditions and sequential image names.

Only two members have explicit SAED name cues:

- `MET/Etanólico/ResultsSAED0016.txt`
- `MET/Etanólico/ResultsSAED0017.txt`

The inventory does not provide an unambiguous filename-level mapping from these result files to static diffraction-pattern images. No filename identifies a calibration file, and no native detector container is present.

The checksum-bound aggregate result and artifact identity are stored in `verified_snapshot.json`.

## Scientific closeout

### Source identity, archive integrity, and member hashing

**Supported.** The exact public archive, repository MD5, computed archive SHA-256, ZIP safety constraints, member CRC values, and streamed member SHA-256 values were verified.

### TEM external validation

**Inconclusive.** The archive supplies many TIFF images but no independent segmentation labels, immutable sample/acquisition lineage, or confirmed native raw status. It is also silver nanoparticle data rather than the current cobalt-oxide target domain.

### SAED external validation

**Inconclusive.** Two small SAED-named text files exist, but static pattern identity, pattern-to-result mapping, acquisition independence, pattern centre, reciprocal calibration, and source-bound reflection assignments remain unresolved.

Consequently:

- intake is `accepted_for_bounded_diagnostic_only`;
- analyzer scientific evidence remains `Inconclusive`;
- external-validation ready remains false;
- engineering-decision ready remains false;
- no preprocessing, model inference, annotation, calibration, or parameter tuning was performed.

## Frozen audit behavior

The workflow:

- downloads only the pinned archive into a transient directory;
- rejects unsafe paths, duplicate normalized paths, symlinks, encryption, unsupported compression, excessive sizes, compression ratios, and configured limits;
- streams every member to verify CRC and compute SHA-256;
- records metadata-only evidence;
- deletes the source archive before artifact upload.

## Invocation

```bash
python scripts/audit_zenodo_silver_tem_saed_archive.py \
  --config case_studies/zenodo_silver_tem_saed_archive_audit/case_config.json \
  --output outputs/zenodo_silver_tem_saed_archive_audit
```

The command requires network access and sufficient temporary disk space. Generated artifacts are metadata-only.
