# Dryad HRTEM External-Validation Candidate Assessment

This case evaluates whether the public Dryad dataset *Segmented high-resolution transmission electron microscopy images of nanoparticles* can serve as external validation for the cobalt-oxide segmentation workflow.

It is a **source-readiness assessment**, not a model evaluation. No external arrays are downloaded or inspected in this stage.

## Source

- Repository: Dryad
- DOI: `10.7941/D1SP93`
- Published: `2023-07-31`
- License: `CC0-1.0`
- Reported total size: `33.69 GB`
- Reported raw HRTEM images: `407`
- Processed HDF5 image-label pairs: `13`

The repository reports:

- materials: Au, Ag, and CdSe;
- substrates: ultrathin carbon and SiN;
- pixel sizes: `0.02–0.042 nm/pixel`;
- electron doses: `80–884 e/Å²`;
- particle diameters: `2.2–20 nm`;
- full raw image size: `4096 × 4096`;
- TEAM 0.5 aberration-corrected TEM with a OneView camera;
- segmentation maps made by one human labeler using LabelBox;
- processed HDF5 keys `/images` and `/labels`.

Reported processing includes x-ray artifact removal, flat-field correction, per-image standardization, `512 × 512` patching, and removal of majority-background patches.

## Why it is not current cobalt-oxide external validation

The source is useful but does not satisfy the current in-domain validation contract:

1. The particle materials are Au, Ag, and CdSe rather than cobalt oxide.
2. Mary Scott is a creator on both the Dryad and cobalt-oxide records, so source and workflow independence cannot be assumed from DOI separation alone.
3. No immutable cross-dataset acquisition or parent-lineage exclusion manifest has been verified.
4. It has not been verified that these images or labels were absent from target-model development.
5. The assessed metadata reports one human labeler but no multi-rater adjudication or uncertainty package.

Therefore the dataset is classified:

```text
not_ready_for_in_domain_external_validation
```

It is retained as:

```text
candidate_for_cross_material_domain_shift_stress_test_after_data_audit
```

## Smallest pilot

The smallest complete processed pair in the source inventory is:

- images: `Au_5nm_260kx_450e_Std_UTC_FFCorr_Team05_Images.h5` (`184.55 MB` reported);
- labels: `Au_5nm_260kx_450e_Std_UTC_FFCorr_Team05_Labels.h5` (`92.28 MB` reported);
- combined reported size: `276.83 MB`.

This pair should be audited before any model inference:

1. resolve Dryad API file identifiers and checksums;
2. verify exact file identity;
3. inspect HDF5 keys, shapes, dtypes, attributes, and pairing;
4. recover or classify patch-to-parent/acquisition mapping;
5. compare content with all cobalt-oxide training-parent candidates;
6. freeze a parent-disjoint evaluation manifest;
7. document the material and acquisition domain shift.

Passing these checks would make the pair eligible only for a **cross-material stress test**, not cobalt-oxide in-domain performance validation.

## Run

```bash
python scripts/assess_dryad_hrtem_external_validation_candidate.py \
  --config case_studies/dryad_hrtem_external_validation_candidate_assessment/case_config.json \
  --output outputs/dryad-hrtem-external-validation-candidate-assessment
```

## Outputs

- `tem_external_validation_candidate_inventory.csv`
- `external_validation_candidate_summary.json`
- `external_validation_candidate_report.md`
- `external_validation_candidate_artifact_manifest.json`

## Scientific closeout

**Evidence level: Diagnostic**

**Result: `not_ready_for_in_domain_external_validation`**

The case supports source triage and a narrowly scoped pilot audit. It does not support model selection, segmentation-performance claims, physical measurements, or engineering release.
