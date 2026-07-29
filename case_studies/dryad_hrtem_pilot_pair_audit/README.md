# Dryad HRTEM Pilot Pair Audit

This case audits the smallest complete processed image-label pair identified by the Dryad external-validation candidate assessment:

- `Au_5nm_260kx_450e_Std_UTC_FFCorr_Team05_Images.h5`
- `Au_5nm_260kx_450e_Std_UTC_FFCorr_Team05_Labels.h5`
- `Processed_datasets_metadata.csv`

The source is Dryad dataset `10.7941/D1SP93`, published on 2023-07-31 under CC0. The landing page reports Au, Ag, and CdSe HRTEM data, 407 raw images and segmentation maps, and 13 curated HDF5 image-label datasets. The pilot is Au rather than cobalt oxide.

## Why this comes before model evaluation

The pair has human segmentation labels, but it cannot be treated as in-domain cobalt-oxide external validation. Before even a diagnostic cross-material stress test, the repository must verify:

1. current Dryad file IDs, names, sizes, and MD5 checksums through the API;
2. downloaded SHA-256 provenance;
3. HDF5 keys, shapes, dtypes, finite values, patch counts, and same-index pairing;
4. source-reported image standardization without altering values;
5. exact observed label values without remapping;
6. binding to the processed-dataset metadata row;
7. exact and high-similarity content overlap against all 256 pinned cobalt-oxide training patches.

## Pinned files

- Dryad image file ID: `2451485`
- Dryad label file ID: `2451482`
- Dryad processed metadata file ID: `2451515`
- Cobalt training source: Zenodo record `14927582`, `training_images.h5`
- Cobalt training SHA-256: `e709b7f1fa383bd111bb0b7e8d4662452b46198f52e4e88b19bb3f3e222c0926`

The Dryad checksums are resolved from the current API response at runtime and then verified against downloaded bytes. The raw API responses are represented by checksum fingerprints in the output; missing or unsupported digests fail closed.

## Run

Download and audit the pinned files automatically:

```bash
python scripts/audit_dryad_hrtem_pilot_pair.py \
  --config case_studies/dryad_hrtem_pilot_pair_audit/case_config.json \
  --output outputs/dryad-hrtem-pilot-pair-audit
```

Use already downloaded files while still verifying them against saved Dryad API metadata:

```bash
python scripts/audit_dryad_hrtem_pilot_pair.py \
  --config case_studies/dryad_hrtem_pilot_pair_audit/case_config.json \
  --images /path/to/Images.h5 \
  --labels /path/to/Labels.h5 \
  --processed-metadata /path/to/Processed_datasets_metadata.csv \
  --training-images /path/to/training_images.h5 \
  --images-api-metadata /path/to/image-api.json \
  --labels-api-metadata /path/to/label-api.json \
  --processed-metadata-api /path/to/metadata-api.json \
  --output outputs/dryad-hrtem-pilot-pair-audit
```

## Outputs

- `tem_pilot_patch_inventory.csv`
- `tem_pilot_training_overlap.csv`
- `pilot_source_metadata_binding.json`
- `pilot_pair_audit_summary.json`
- `pilot_pair_audit_report.md`
- `pilot_pair_audit_artifact_manifest.json`

Raw image and label arrays are not copied into the evidence package.

## Scientific boundary

**Evidence level: Diagnostic**

A successful data audit can permit freezing a protocol for a diagnostic Au-to-cobalt cross-material stress test. It cannot establish in-domain cobalt-oxide external validation, unbiased generalization, acquisition independence, multi-rater annotation reliability, physical size, causal relationships, optimization, or engineering-release readiness.

No label remapping, smoothing, outlier removal, augmentation, model training, model inference, segmentation metric, or physical conversion is performed by this audit.
