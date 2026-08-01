# Dryad HRTEM Pilot Pair Audit

This case prepares a checksum-bound audit of the smallest complete processed image-label pair identified by the Dryad external-validation candidate assessment:

- `Au_5nm_260kx_450e_Std_UTC_FFCorr_Team05_Images.h5`
- `Au_5nm_260kx_450e_Std_UTC_FFCorr_Team05_Labels.h5`
- `Processed_datasets_metadata.csv`

The source is Dryad dataset `10.7941/D1SP93`, published on 2023-07-31 under CC0. The source reports Au, Ag, and CdSe HRTEM data, 407 raw images and segmentation maps, and 13 curated HDF5 image-label datasets. This pilot is Au rather than cobalt oxide.

## Current acquisition status

The live Dryad metadata endpoints are publicly accessible and have been verified. The three pilot files directly resolve to Dryad source version `247105`; they must not be rebound to the DOI's later metadata-only version merely because it is current.

Dataset identity is bound through each file's explicit `stash:dataset` link and the dataset endpoint's canonical DOI fields. Related article, repository, or Foundry-ML identifiers that may appear elsewhere in the version payload are preserved as provenance but are not reinterpreted as the Dryad dataset DOI.

The current source-version inventory reports SHA-256 digests:

- images: `e00d7ac5326dadd3e4abac8147544b8afa35433a5bad694806c8062373d14c09`
- labels: `a6d462296bdbf0c1c5b5294de97e239f908d0ff9718864e8f6ca5fb648b92fec`
- processed metadata: `ddc70cc66479e5ab7250376572cbcedbc8e4750c27dc18b2feda6d4a588bf796`

Dryad's API download endpoint requires an authenticated API user. The GitHub Actions workflow therefore behaves explicitly:

- without repository secret `DRYAD_API_TOKEN`, it verifies live metadata, source version, checksums, software tests, and records `blocked_missing_dryad_api_token`;
- with `DRYAD_API_TOKEN`, the workflow first records only that a credential is configured, marks authenticated download availability true only after all three binary downloads succeed, and then runs the real HDF5 and content-overlap audit.

A successful unauthenticated workflow is **not** a real-data audit result.

## Why this comes before model evaluation

The pair has human segmentation labels, but it cannot be treated as in-domain cobalt-oxide external validation. Before even a diagnostic cross-material stress test, the repository must verify:

1. Dryad file IDs, filenames, byte sizes, source-linked version, and source-declared SHA-256 checksums;
2. downloaded file hashes against those source values;
3. HDF5 keys, shapes, dtypes, finite values, patch counts, and same-index pairing;
4. patch intensity distributions without changing the source arrays;
5. exact observed label values without remapping;
6. binding to the processed-dataset metadata row;
7. exact and high-similarity content overlap against all 256 pinned cobalt-oxide training patches.

The source describes standardizing each `4096 x 4096` parent image before dividing it into `512 x 512` patches. Individual patches are therefore **not required** to retain mean zero and standard deviation one. Patch mean and standard deviation are recorded diagnostically; each patch is standardized again only for content-identity comparison.

## Pinned files

- Dryad image file ID: `2451485`
- Dryad label file ID: `2451482`
- Dryad processed metadata file ID: `2451515`
- Dryad file-linked source version: `247105`
- Cobalt training source: Zenodo record `14927582`, `training_images.h5`
- Cobalt training SHA-256: `e709b7f1fa383bd111bb0b7e8d4662452b46198f52e4e88b19bb3f3e222c0926`

Missing, unsupported, or mismatched checksums fail closed. Raw individual-file API responses are copied before enrichment, enriched records are written to separate files, and source version `247105` plus dataset DOI `10.7941/D1SP93` are verified before their checksums are used.

## Run

Automatic download requires a Dryad API token in the environment used by the caller:

```bash
export DRYAD_API_TOKEN="..."
python scripts/audit_dryad_hrtem_pilot_pair.py \
  --config case_studies/dryad_hrtem_pilot_pair_audit/case_config.json \
  --output outputs/dryad-hrtem-pilot-pair-audit
```

For GitHub Actions, store the token as repository secret `DRYAD_API_TOKEN`.

Use already downloaded files while still verifying them against saved, source-version-enriched Dryad API metadata:

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

Authenticated real-data audit:

- `tem_pilot_patch_inventory.csv`
- `tem_pilot_training_overlap.csv`
- `pilot_source_metadata_binding.json`
- `pilot_pair_audit_summary.json`
- `pilot_pair_audit_report.md`
- `pilot_pair_audit_artifact_manifest.json`

Workflow readiness and provenance:

- `dryad-acquisition-readiness.json`
- live individual-file API responses
- file-linked source-version metadata and paginated file inventory

Raw image and label arrays are not copied into the evidence package.

## Scientific boundary

**Evidence level: Diagnostic**

A completed authenticated data audit may permit freezing a protocol for a diagnostic Au-to-cobalt cross-material stress test only when the processed metadata row is bound exactly and uniquely. It cannot establish in-domain cobalt-oxide external validation, unbiased generalization, acquisition independence, multi-rater annotation reliability, physical size, causal relationships, optimization, or engineering-release readiness.

When acquisition is blocked, the scientific result is **Inconclusive** for HDF5 structure and content overlap because those arrays were not inspected.

No label remapping, smoothing, outlier removal, augmentation, model training, model inference, segmentation metric, or physical conversion is performed by this audit.
