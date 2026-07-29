# Public Cobalt Oxide TEM Parent-Overlap Audit

This case tests whether any of the fifty public standardized 4k TEM source frames are content-equivalent to the four reconstructed parent images behind the 256 hand-labeled training patches. It also determines whether the audited bundle contains a scientifically usable external validation set.

## Sources

- Dataset: *Transmission electron microscopy images and deep Learning-predicted segmentation for statistical analysis of cobalt oxide nanoparticles*
- Zenodo DOI: `10.5281/zenodo.14927582`
- Dataset version: `v1`
- License: `CC BY 4.0`
- `training_images.h5`
  - MD5: `caac404a7ea2c65b2403aee5728a70eb`
  - SHA-256: `e709b7f1fa383bd111bb0b7e8d4662452b46198f52e4e88b19bb3f3e222c0926`
- `TEM_images.zip`
  - MD5: `d1e991346d07b8a112c4b6dbfd8367ba`
  - SHA-256: `a9e4618f697205bf8560ab14bc5e313d4011b51aaa6dbf8a5c62ddc22bc558d8`
- Training notebook repository: `ScottLabUCB/NN_training`
- Pinned commit: `9f92235102a805abc76e3d60065d677ee2068c90`
- Pinned notebook blob: `a21bf95fb41f63efb0c33b1563bc43a073afed58`

External files are downloaded at runtime and retain their original license and citation requirements.

## Why this audit comes before retraining

The public training file contains 256 standardized `512 × 512` patches. The pinned notebook shows that each 4k parent image is divided into an aligned `8 × 8` grid and that each tile is standardized independently:

```text
patch_index = row * 8 + column + 64 * parent_index
standardized_tile = (tile - tile_mean) / tile_std
```

The training HDF5 file does not embed parent IDs, but contiguous groups of 64 patches are strongly consistent with four parent grids. Before another U-Net run can add scientific evidence, the fifty public source frames must be checked for content overlap with those four candidates.

## Comparison rule

For each public source frame, the audit:

1. applies the pinned aligned `8 × 8` tiling;
2. re-standardizes each `512 × 512` tile using the pinned formula;
3. computes a SHA-256 fingerprint after decimal quantization;
4. compares each tile only with the corresponding tile position in all four training-parent candidates;
5. records low-resolution block-mean normalized cross-correlation as a diagnostic review metric.

A source frame is classified `content_equivalent_to_training_candidate_parent` only when all 64 aligned tile fingerprints match one candidate parent. A high-correlation or partial-match result is `review_required`; it is not silently promoted to overlap or independence.

A negative result means only that no content-equivalent overlap was detected under this audited alignment and standardization path. It does not prove acquisition-level independence against unknown crops, transforms, or unpublished images.

## Reproduced real-data result

The checksum-bound public audit reproduced:

- 4 reconstructed training-parent candidates;
- 50 public source frames;
- 200 aligned parent/frame comparisons;
- 0 exact content-equivalent overlaps under the 64-tile fingerprint rule;
- 49 frames with no content-equivalent overlap detected under the audited path;
- 1 frame requiring focused review: `co0_7:frame-0` against reconstructed candidate parent `3`;
- 0 independent external-validation candidates.

The focused review compared every corresponding tile at pixel and block-signature levels. It found:

- global pixel NCC: `0.9990847724679279`;
- global block-signature NCC: `0.9973949216510015`;
- median tile pixel NCC: `0.9996866574918363`;
- minimum tile pixel NCC: `0.9941011260031625`;
- all 64 tiles with pixel NCC at least `0.99`;
- 63 of 64 tiles with pixel NCC at least `0.995`;
- 0 exact quantized tile-hash matches.

This meets the predeclared strong-content-correspondence thresholds. Therefore `co0_7:frame-0` is conservatively excluded from any external-candidate pool as leakage control. This does **not** confirm authoritative parent or acquisition identity because the public files do not embed an immutable mapping.

The focused evidence and exact limitations are documented in `../public_cobalt_oxide_tem_parent_similarity_review/`.

## External validation boundary

The public `Segmented_images.zip` masks were previously audited as source-predicted outputs. They are not independent hand labels. Therefore:

- `co0_7:frame-0` is conservatively excluded because of strong content correspondence;
- the other 49 frames remain image-only candidates rather than proven parent-disjoint samples;
- no frame is an independent external validation sample in the current public bundle.

The conclusion can change only with an immutable source patch-to-parent/acquisition map and a predeclared parent-disjoint image set with independent labels that was never used for training, tuning, or model selection.

## Run

Download the pinned files automatically:

```bash
python scripts/audit_public_cobalt_oxide_tem_parent_overlap.py \
  --config case_studies/public_cobalt_oxide_tem_parent_overlap_audit/case_config.json \
  --output outputs/public-cobalt-oxide-tem-parent-overlap-audit
```

Use already downloaded exact files:

```bash
python scripts/audit_public_cobalt_oxide_tem_parent_overlap.py \
  --config case_studies/public_cobalt_oxide_tem_parent_overlap_audit/case_config.json \
  --training-images /path/to/training_images.h5 \
  --source-archive /path/to/TEM_images.zip \
  --output outputs/public-cobalt-oxide-tem-parent-overlap-audit
```

Focused review:

```bash
python scripts/audit_public_cobalt_oxide_tem_parent_similarity.py \
  --config case_studies/public_cobalt_oxide_tem_parent_similarity_review/case_config.json \
  --training-images /path/to/training_images.h5 \
  --source-archive /path/to/TEM_images.zip \
  --output outputs/public-cobalt-oxide-tem-parent-similarity-review
```

## Outputs

Broad audit:

- `tem_parent_overlap_frame_inventory.csv`
- `tem_parent_overlap_pairwise_comparisons.csv`
- `parent_overlap_audit_summary.json`
- `parent_overlap_audit_report.md`
- `parent_overlap_audit_artifact_manifest.json`

Focused review:

- `tem_parent_similarity_review_tiles.csv`
- `parent_similarity_review_summary.json`
- `parent_similarity_review_report.md`
- `parent_similarity_review_artifact_manifest.json`

No raw image arrays, model files, generated masks, or physical measurements are copied into the evidence package.

## Scientific closeout

**Evidence level: Diagnostic**

**Result: `no_independent_external_validation_set_available`**

The strongest supported action is conservative exclusion of `co0_7:frame-0` from an external-candidate pool. The remaining 49 frames are image-only candidates. They cannot support independent segmentation performance because authoritative parent metadata and independent labels are absent.
