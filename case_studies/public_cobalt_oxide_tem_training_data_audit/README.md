# Public Cobalt Oxide TEM Training-Data Readiness Audit

This case audits the exact public hand-labeled HRTEM training patches associated with the cobalt-oxide nanoparticle study. It validates data integrity and split readiness; it does not train or evaluate a segmentation model.

## Sources

- Dataset: *Transmission electron microscopy images and deep Learning-predicted segmentation for statistical analysis of cobalt oxide nanoparticles*
- Zenodo DOI: `10.5281/zenodo.14927582`
- Dataset version: `v1`
- License: `CC BY 4.0`
- `training_images.h5`
  - published MD5: `caac404a7ea2c65b2403aee5728a70eb`
  - tracked SHA-256: `e709b7f1fa383bd111bb0b7e8d4662452b46198f52e4e88b19bb3f3e222c0926`
- `training_labels.h5`
  - published MD5: `087a4df4cd67fa97cdf790c40bdc828b`
  - tracked SHA-256: `28db52db53209a8a068f722990264a136ab187a192340ef3770e81d9c0de7c40`
- Training notebook repository: `ScottLabUCB/NN_training`
- Pinned repository commit: `9f92235102a805abc76e3d60065d677ee2068c90`

External files retain their original license and citation requirements. The HDF5 files are downloaded at runtime and are not committed to this repository.

## Why this audit exists

The Zenodo record describes the files as hand-labeled training data. The linked training notebook loads 256 image patches and 256 two-channel labels, then applies shuffled eight-fold `KFold` directly to patch indices.

A separate notebook shows the source tiling order used to divide each 4k image into an `8 × 8` grid of 64 `512 × 512` patches:

```text
patch_index = row * 8 + column + 64 * parent_index
```

If patches from the same parent image appear in both training and validation, the validation set is not independent at the parent-image level. This audit checks the public HDF5 structure and quantifies that risk without fitting a model.

## Verified public data contract

The complete real-data audit reproduced:

- image dataset `/images` with shape `256 × 512 × 512` and dtype `float64`;
- label dataset `/labels` with shape `256 × 512 × 512 × 2` and dtype `float64`;
- no root or dataset attributes;
- contiguous, uncompressed HDF5 storage;
- 256 finite image patches;
- 256 finite binary complementary one-hot labels;
- no exact duplicate image patches;
- no exact duplicate label patches;
- all image patches already standardized to approximately zero mean and unit standard deviation.

Observed source-image range after source standardization:

- minimum: `-26.453024268925645`
- maximum: `21.97890372229253`
- maximum absolute patch mean: at most `1.3877787807814457e-17`
- maximum absolute patch-standard-deviation difference from `1.0`: below the `1e-12` contract

The files do not contain:

- parent-image IDs;
- patch coordinates;
- acquisition IDs;
- per-patch pixel calibration;
- an independent validation or test partition.

## Candidate parent-image reconstruction

Contiguous blocks of 64 patches were evaluated as four candidate `8 × 8` parent-image grids. This candidate grouping is supported by both the pinned tiling code and edge continuity:

| Diagnostic | Observed contiguous grouping | Random patch pairing | Ratio |
|---|---:|---:|---:|
| Image seam mean absolute difference | `0.6027527824255584` | `1.1371069913522882` | `0.5300756982495933` |
| Label seam mean absolute difference | `0.00959559849330357` | `0.46188790457589285` | `0.020774734298604946` |

The substantially lower observed seam discontinuity strongly supports four parent grids. It does not replace source-provided immutable parent IDs, so the status remains:

```text
diagnostic_inference_not_embedded_metadata
```

## Published notebook split audit

The pinned training notebook uses:

```python
KFold(n_splits=8, shuffle=True, random_state=42)
```

on the 256 patch indices. Reproducing that split against the four reconstructed candidate parent groups gives:

- 224 training patches and 32 validation patches per fold;
- all four candidate parent groups in every training fold;
- all four candidate parent groups in every validation fold;
- all four candidate parent groups overlapping train and validation in all eight folds.

Therefore the published patch-level KFold is not parent-image-disjoint validation.

## Run

Download the pinned files automatically:

```bash
python scripts/audit_public_cobalt_oxide_tem_training_data.py \
  --config case_studies/public_cobalt_oxide_tem_training_data_audit/case_config.json \
  --output outputs/public-cobalt-oxide-tem-training-data-audit
```

Using existing local files:

```bash
python scripts/audit_public_cobalt_oxide_tem_training_data.py \
  --config case_studies/public_cobalt_oxide_tem_training_data_audit/case_config.json \
  --images /path/to/training_images.h5 \
  --labels /path/to/training_labels.h5 \
  --output outputs/public-cobalt-oxide-tem-training-data-audit
```

Both files must match the pinned MD5 and SHA-256 values.

## Outputs

- `tem_training_patch_inventory.csv`
- `tem_training_candidate_parent_seams.csv`
- `tem_training_notebook_split_overlap.csv`
- `training_data_readiness_summary.json`
- `training_data_readiness_report.md`
- `training_data_readiness_artifact_manifest.json`

No source image or label arrays are copied into the tracked output package.

## Processing contract

The audit:

1. verifies complete file identity;
2. rejects local symlink inputs and output overwrite;
3. validates exact HDF5 keys, shapes, dtypes, storage layout, and attribute absence;
4. validates every image and label value;
5. verifies complementary one-hot labels;
6. records per-patch image and label SHA-256 fingerprints;
7. records the existing patch standardization without applying new preprocessing;
8. reconstructs only a diagnostic four-parent candidate grouping;
9. reproduces the source notebook's patch split without model training;
10. writes checksum-bound evidence outputs.

It does not normalize, augment, denoise, filter, threshold, relabel, train, infer, or calculate segmentation accuracy.

## Calibration boundary

The dataset description reports pixel sizes from 67 to 86 pm across the training-image context. The public HDF5 files do not bind a calibration value to each patch. Therefore the range is recorded only as literature context and is not used to calculate physical dimensions.

## Scientific closeout

**Evidence level: Diagnostic**

**Result: `not_ready_for_independent_model_performance_claims`**

### Supported

- exact public file identity;
- paired patch and label integrity;
- binary complementary one-hot label representation;
- source-standardized image representation;
- absence of exact duplicate patches;
- diagnostic reconstruction of four candidate parent grids;
- direct quantification of parent-overlap risk in the source notebook split.

### Not supported

- independent segmentation accuracy;
- unbiased parent-image generalization estimates;
- treating patch-level KFold metrics as external validation;
- pixel calibration for individual patches;
- nanometre-scale particle measurements;
- filename or index-derived synthesis conditions;
- causal, predictive, optimization, or engineering-release claims.

The strongest next evidence would be a source-provided immutable patch-to-parent mapping and a predeclared parent-disjoint external validation set with independent labels. A leave-one-parent-out analysis using only four reconstructed parents could be diagnostic, but it would still be limited and should not be described as broad model validation.
