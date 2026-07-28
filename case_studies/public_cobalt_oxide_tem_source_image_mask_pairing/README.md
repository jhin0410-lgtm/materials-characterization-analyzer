# Public Cobalt Oxide TEM Source-Image–Mask Pairing Audit

This case audits **real public experimental-derived standardized HRTEM image arrays and their source-predicted segmentation masks**. It does not use synthetic data for scientific evidence.

## Sources

- Dataset: *Transmission electron microscopy images and deep Learning-predicted segmentation for statistical analysis of cobalt oxide nanoparticles*
- Zenodo DOI: `10.5281/zenodo.14927582`
- Version: `v1`
- License: `CC BY 4.0`
- Source-image archive: `TEM_images.zip`
- Source-image archive published MD5: `d1e991346d07b8a112c4b6dbfd8367ba`
- Source-image archive tracked SHA-256: `a9e4618f697205bf8560ab14bc5e313d4011b51aaa6dbf8a5c62ddc22bc558d8`
- Mask archive: `Segmented_images.zip`
- Mask archive published MD5: `63edc9b44264f8a1397bff806d58eade`
- Mask archive tracked SHA-256: `bd7816f3cf2869e4a349fc04d3e0d0464b3e14e9c8c8655f51e6e487fb59824b`

External data retain their original license and citation requirements. Neither archive is committed to this software repository.

## Why this audit exists

The preceding source-mask case established the integrity of fifty public binary mask arrays, but the selected mask archive did not contain source HRTEM image arrays or pixel calibration. This audit tests whether the separately published source-image archive is structurally consistent with those masks.

The dataset record describes the segmentation results as corresponding to the TEM images. The audit therefore records **source-asserted structural pairing**, not an independently proven scientific correspondence.

## Audited contract

The exact public archives contain:

- ten source-image HDF5 members named `<prefix>_TEM_images.h5`;
- ten mask HDF5 members named `<prefix>_segmented_images.h5`;
- one exact source-image and mask member for each of ten opaque prefixes;
- source-image dataset `/images`;
- mask dataset `/labels`;
- shape `5 × 4096 × 4096` for every source-image and mask member;
- `float64` source-image and mask storage;
- fifty same-index source-image/mask frame pairs;
- all fifty source-image frames with absolute mean below `1e-10`;
- all fifty source-image frame standard deviations within `1e-12` of `1.0`;
- no root or dataset attributes containing pixel calibration.

The `/images` arrays are therefore numerically standardized source-image representations, not original detector-intensity exports. The audit preserves these stored values but does not describe them as raw detector measurements.

The prefixes are retained as opaque source identifiers. Values such as `Co0_4` or `DW0_7` are not converted into synthesis conditions, composition, water content, or process variables.

## Validated real-data result

The complete dedicated audit reproduced:

- 10 exact source-image HDF5 identities;
- 10 exact mask HDF5 identities;
- 10 explicit member-prefix pairs;
- 50 same-index frame pairs;
- equal `5 × 4096 × 4096` shape and `float64` dtype for every pair;
- source-image dataset `/images` and mask dataset `/labels`;
- no HDF5 root or dataset attributes;
- maximum absolute source-image frame mean: `8.84156029640204e-14`;
- maximum absolute deviation of source-image frame standard deviation from `1.0`: `1.9984014443252818e-15`;
- per-member and per-frame SHA-256 fingerprints.

These results show that the public source-image arrays are already numerically standardized. They do not recover original detector intensity, pixel calibration, or independent segmentation labels.

## Run

```bash
python scripts/audit_public_cobalt_oxide_tem_source_image_mask_pairing.py \
  --config case_studies/public_cobalt_oxide_tem_source_image_mask_pairing/case_config.json \
  --output outputs/public-cobalt-oxide-tem-source-image-mask-pairing
```

Using existing local downloads:

```bash
python scripts/audit_public_cobalt_oxide_tem_source_image_mask_pairing.py \
  --config case_studies/public_cobalt_oxide_tem_source_image_mask_pairing/case_config.json \
  --image-archive /path/to/TEM_images.zip \
  --mask-archive /path/to/Segmented_images.zip \
  --output outputs/public-cobalt-oxide-tem-source-image-mask-pairing
```

Both local files must match the pinned MD5 and SHA-256 values.

## Processing contract

For each explicit member pair, the audit:

1. verifies complete archive identity;
2. rejects unsafe paths, symlinks, encrypted entries, and member drift;
3. extracts one source-image and mask HDF5 member at a time;
4. verifies dataset names, shapes, dtypes, and attribute absence;
5. verifies all source-image values are finite and all mask values are finite and binary;
6. records SHA-256 fingerprints for each member and each of fifty frames;
7. verifies and records the existing per-frame zero-mean/unit-standard-deviation representation without applying normalization;
8. records mask foreground fraction without re-segmentation;
9. deletes temporary extracted HDF5 files before the next pair;
10. writes checksum-bound evidence outputs.

It does not sort, normalize, denoise, filter, threshold, align, register, interpolate, crop, relabel, or alter either array. The source-image arrays arrive already numerically standardized.

## Outputs

- `tem_source_image_mask_file_pairs.csv`
- `tem_source_image_mask_frame_pairs.csv`
- `source_image_mask_pairing_summary.json`
- `source_image_mask_pairing_report.md`
- `source_image_mask_pairing_artifact_manifest.json`

No source image or mask pixels are copied into the tracked output package.

## Calibration boundary

The associated publication reports an 86 pm pixel size for its 4k HRTEM image context. The public HDF5 members themselves do not embed per-file or per-frame calibration, and this audit does not establish an immutable calibration binding for each archive member.

Therefore:

- the 86 pm value is stored only as literature context;
- it is not applied to any pixel measurement;
- no `nm`, `nm²`, particle diameter, or physical area is generated.

## Software validation

Synthetic HDF5 and ZIP fixtures are used only to test deterministic output, safe-path and symlink rejection, hash drift, shape and frame-count mismatches, nonfinite and nonbinary values, unexpected HDF5 metadata, standardization drift, overwrite refusal, and preservation of the no-model and no-physical-conversion boundary.

Synthetic fixtures do not contribute to the real-data results.

## Scientific closeout

**Evidence level: Diagnostic**

### Supported

- exact source-image and mask archive identity;
- ten exact member-prefix pairs;
- equal source-image/mask array shapes and frame counts;
- source-asserted same-index frame inventory;
- per-member and per-frame content fingerprints;
- provenance-preserving structural interoperability.

### Not supported

- independent proof that each mask is the scientifically correct segmentation of its indexed standardized source-image frame;
- recovery of original detector-intensity values;
- segmentation accuracy or model performance;
- pixel calibration for individual public HDF5 members;
- nanometre-scale particle dimensions;
- treating connected components as confirmed particles;
- synthesis-condition interpretation from filenames;
- phase, mechanism, causal, predictive, optimization, or engineering-release claims.

The strongest next evidence would be a source-provided immutable member/frame mapping manifest, per-file calibration records, and independent validation labels.
