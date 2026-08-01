# Mendeley CoP/Co2P/Co3O4 TEM Candidate Audit

This case resolves whether Mendeley Data record `10.17632/8w66synjmx.1` can supply an independent cobalt-oxide TEM segmentation validation set.

## Result

**Evidence level:** Diagnostic

**Scientific result:** `rendered_microscopy_files_resolved_not_validation_ready`

The candidate is excluded from independent segmentation validation.

## Verified source contract

The anonymous public API used by the Mendeley landing page exposes one primary raw archive:

- dataset ID: `8w66synjmx`
- DOI: `10.17632/8w66synjmx.1`
- filename: `database.rar`
- bytes: `3472702`
- SHA-256: `db3204100545fe3a152c0a545d29ab7f27f85c86594de3e3484bb76020ad7edf`

A separate raw-data record, `10.17632/zhnbzhjrtr.1`, exposes a byte-identical archive. It is therefore a duplicate public record, not an independent dataset.

The source-checksum-verified archive contains 90 members and 57 files. Six microscopy-like members were selectively inspected without persisting source image bytes:

- `database/figure 1/figure 1b/0002 Ceta.tif`
- `database/figure 1/figure 1c-1e/0007 Ceta.tif`
- `database/figure 1/figure 1g/HAADF_HAADF.bmp`
- `database/figure 1/figure 1h/HAADF_Co.bmp`
- `database/figure 1/figure 1i/HAADF_P.bmp`
- `database/figure 1/figure 1j/HAADF_O.bmp`

The two TIFF files are uncompressed `1024 x 1024`, RGB, 8-bit-per-channel rendered images. The four HAADF or elemental-map files are `512 x 512` RGB BMP images. The files do not provide source-supported pixel calibration, original detector-intensity provenance, immutable sample or acquisition IDs, Co3O4 region binding, or independent segmentation labels.

## User-facing metadata audit

```bash
mca tem-mendeley-audit \
  --config case_studies/mendeley_cop_co2p_co3o4_tem_candidate/case_config.json \
  --output outputs/mendeley-cop-co2p-co3o4-tem-candidate
```

This command resolves immutable dataset snapshots and root-file UUID, size, and SHA-256 metadata. It does not download the archive. A failed primary root-file request remains `blocked_public_api_metadata_access` even when control records respond. Duplicate-record identity is asserted only when both inventories provide valid SHA-256 values and positive byte sizes, and the configured API base is the endpoint actually queried and reported.

## Reproducible real-data audit

The dedicated GitHub Actions workflow additionally:

1. verifies the source archive byte size and SHA-256;
2. inventories the RAR without extracting unrelated files;
3. selectively extracts only six microscopy-like members into temporary storage;
4. records image format, dimensions, mode, TIFF tags, and per-file SHA-256;
5. strips query strings and fragments from every persisted landing-page or asset URL;
6. regenerates the metadata artifact manifest after both probe files exist, so all uploaded metadata evidence is checksum-bound;
7. deletes the source bytes and uploads metadata-only evidence.

## Scientific boundary

The following remain unsupported:

- Co3O4 particle-region identity in the rendered figures;
- sample or acquisition independence;
- raw detector-intensity analysis;
- physical measurements without calibration;
- independent segmentation labels;
- external segmentation-performance claims;
- model selection or engineering release.

A valid next dataset must contain raw or lossless cobalt-oxide TEM detector data with immutable sample and acquisition lineage, verified non-use in model development, content-overlap clearance, and blinded independent labels with adjudication. U-Net retraining is not the current scientific priority.
