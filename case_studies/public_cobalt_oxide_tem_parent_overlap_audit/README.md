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

## External validation boundary

The public `Segmented_images.zip` masks were previously audited as source-predicted outputs. They are not independent hand labels. Therefore:

- a frame overlapping a training parent is excluded;
- a frame without detected overlap is only an image candidate;
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

## Outputs

- `tem_parent_overlap_frame_inventory.csv`
- `tem_parent_overlap_pairwise_comparisons.csv`
- `parent_overlap_audit_summary.json`
- `parent_overlap_audit_report.md`
- `parent_overlap_audit_artifact_manifest.json`

No raw image arrays, model files, or generated masks are copied into the evidence package.

## Scientific closeout

**Evidence level: Diagnostic**

**Result: `no_independent_external_validation_set_available`**

This audit can identify and exclude content-equivalent training-parent overlap and document image-only candidates. It cannot establish independent segmentation performance because authoritative parent metadata and independent labels are absent.
