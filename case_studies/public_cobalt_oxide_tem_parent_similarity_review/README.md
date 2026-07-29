# Public Cobalt Oxide TEM Parent Similarity Review

This case resolves the single `review_required` pair produced by the broader public TEM parent-overlap audit:

- source frame: `co0_7:frame-0` from `Co0_7_TEM_images.h5`;
- reconstructed training candidate parent: `3`;
- prior block-signature NCC: approximately `0.997395`;
- exact aligned quantized tile hashes: `0 / 64`.

The purpose is to determine whether similarity is distributed across the full image or driven by only a small region. It does not assert authoritative acquisition identity.

## Source contract

- Zenodo DOI: `10.5281/zenodo.14927582`
- dataset version: `v1`
- license: `CC BY 4.0`
- `training_images.h5`
  - MD5: `caac404a7ea2c65b2403aee5728a70eb`
  - SHA-256: `e709b7f1fa383bd111bb0b7e8d4662452b46198f52e4e88b19bb3f3e222c0926`
- `TEM_images.zip`
  - MD5: `d1e991346d07b8a112c4b6dbfd8367ba`
  - SHA-256: `a9e4618f697205bf8560ab14bc5e313d4011b51aaa6dbf8a5c62ddc22bc558d8`

The files are downloaded at runtime and are not committed to this repository.

## Comparison contract

The review reproduces the pinned aligned `8 × 8` tiling and independently standardizes each `512 × 512` source tile. Every source tile is compared with the corresponding training patch from candidate parent 3.

Recorded diagnostics include:

- pixel-level NCC, RMSE, MAE, and maximum absolute difference for all 64 tiles;
- block-signature NCC and RMSE;
- exact quantized tile-hash matches;
- global, median-tile, and minimum-tile NCC;
- counts above predefined NCC thresholds.

The predeclared strong-correspondence rule requires all of:

- global pixel NCC at least `0.995`;
- median tile pixel NCC at least `0.995`;
- minimum tile pixel NCC at least `0.98`.

Passing this rule supports conservative exclusion from an external-candidate pool. It does not confirm authoritative parent identity.

## Run

```bash
python scripts/audit_public_cobalt_oxide_tem_parent_similarity.py \
  --config case_studies/public_cobalt_oxide_tem_parent_similarity_review/case_config.json \
  --output outputs/public-cobalt-oxide-tem-parent-similarity-review
```

Using exact local copies:

```bash
python scripts/audit_public_cobalt_oxide_tem_parent_similarity.py \
  --config case_studies/public_cobalt_oxide_tem_parent_similarity_review/case_config.json \
  --training-images /path/to/training_images.h5 \
  --source-archive /path/to/TEM_images.zip \
  --output outputs/public-cobalt-oxide-tem-parent-similarity-review
```

## Outputs

- `tem_parent_similarity_review_tiles.csv`
- `parent_similarity_review_summary.json`
- `parent_similarity_review_report.md`
- `parent_similarity_review_artifact_manifest.json`

No source image arrays, labels, model files, or physical measurements are written.

## Scientific boundary

The evidence remains **Diagnostic**.

Even strong full-image correspondence cannot replace source-issued patch-to-parent and acquisition metadata. The public masks are source-predicted outputs rather than independent expert labels. Therefore this case cannot create an independent external validation set or support segmentation-performance claims.
