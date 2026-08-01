# Public FINDS SAED Diagnostic Case

This case validates the conservative SAED workflow on a checksum-bound public
example image with an explicit FINDS project center and camera constant. It is a
real-image software-integration case, not a crystallographic ground-truth case.

## Public source

- Repository: Zenodo
- Record: `13748483`
- DOI: `10.5281/zenodo.13748483`
- Dataset version: `v1`
- Licence: `GPL-3.0-or-later`
- Archive: `FINDS v0.5 2024-09-11.zip`
- Archive MD5: `d340ef34015b024320d38c5de9549f9b`
- Archive SHA-256: `3bd91d96469dbedd9f780292fc248fa6ce94e391f63d6d7a12c4e75738d1a7d6`

The archive is downloaded transiently. Source images and project files are not
committed to the repository and are not copied into source-audit artifacts.

## Selected FINDS project

The validated project contract binds:

- project file: `Project SAED A.txt`;
- image: `SAED A.jpg`;
- contextual d-value file: `SAED A d-values.txt`;
- camera constant: `587.5 Å·pixel = 58.75 nm·pixel`;
- reciprocal calibration: `0.01702127659574468 nm⁻¹/pixel` under `g = 1/d`;
- center: `(586, 575) pixel`;
- decoded image: `1170 × 1152`, RGB JPEG, converted to `uint8` grayscale.

The source image is a lossy rendered JPEG. Material identity, source sample ID,
acquisition ID, accelerating voltage, camera length, detector pixel size, and
raw detector-intensity provenance are unresolved and are not inferred from the
filename or visual appearance.

## Canonical adapter

The selected JPEG is decoded once using OpenCV, converted from BGR to grayscale,
and written to a lossless PNG container supported by the repository's SAED
analyzer. The adapter verifies pixel equality after PNG round-trip.

The adapter performs no:

- normalization;
- contrast adjustment;
- cropping;
- resizing;
- denoising;
- detector correction;
- saturation correction.

The PNG preserves the decoded grayscale JPEG array. It cannot restore
information already lost during JPEG encoding and does not convert the source
into raw detector data.

## Analysis and sensitivity contract

Seven runs are predeclared. In run IDs, `m` means a negative offset, `p` means a
positive offset, and `p0` explicitly records a zero offset formatted by the
runner.

| Run | Center offset | Smoothing window |
|---|---:|---:|
| `primary` | `(0, 0) px` | `7` |
| `smoothing_5` | `(0, 0) px` | `5` |
| `smoothing_11` | `(0, 0) px` | `11` |
| `center_m2_p0` | `(-2, 0) px` | `7` |
| `center_p2_p0` | `(+2, 0) px` | `7` |
| `center_p0_m2` | `(0, -2) px` | `7` |
| `center_p0_p2` | `(0, +2) px` | `7` |

All runs use:

- complete-annulus radial mean;
- `1 pixel` radial bins;
- analyzed radius `5–570 pixel`;
- bright-ring detection;
- Savitzky–Golay polynomial order `2`;
- prominence fraction `0.05`;
- minimum candidate separation `5 pixel`;
- camera-constant calibration from the project file.

Primary candidates are matched one-to-one to the nearest sensitivity candidate
within `5 pixel`. Analyzer candidate tables are not modified, and candidates are
not automatically accepted or rejected.

## Source d-values

The source file contains four contextual d-values:

- `2.022 Å`;
- `1.431 Å`;
- `1.167 Å`;
- `1.011 Å`.

These values are converted to nanometres and compared with primary detected
candidates only after detection. They are not used to choose or tune the center,
calibration, radius range, smoothing, prominence, candidate distance, or
candidate count. No d-value is assigned to a material, phase, reflection, or
zone axis.

## Run

```bash
python scripts/audit_public_finds_saed_source.py \
  --config case_studies/public_finds_saed/case_config.json \
  --output outputs/public-finds-saed/source-audit

python scripts/run_public_finds_saed_case.py \
  --config case_studies/public_finds_saed/case_config.json \
  --output outputs/public-finds-saed/result

python scripts/verify_public_finds_saed_case.py \
  --audit outputs/public-finds-saed/source-audit \
  --result outputs/public-finds-saed/result
```

## Outputs

```text
outputs/public-finds-saed/
├── source-audit/
│   ├── archive_inventory.csv
│   ├── source_audit_summary.json
│   ├── source_audit_report.md
│   └── source_audit_manifest.json
└── result/
    ├── canonical/saed_a_decoded_grayscale.png
    ├── analyses/<seven-run-id>/
    ├── saed_sensitivity_candidates.csv
    ├── saed_candidate_robustness.csv
    ├── saed_unmatched_sensitivity_candidates.csv
    ├── source_d_value_comparison.csv
    ├── case_summary.json
    ├── case_validation_report.md
    └── case_artifact_manifest.json
```

## Scientific closeout

**Evidence level: Diagnostic**

- Supported: archive and member identity, licence, FINDS project-to-image
  binding, center coordinates, camera-constant unit conversion, decoded-array
  PNG round-trip, analyzer execution, and parameter-sensitivity provenance.
- Diagnostic only: radial ring candidates, calibrated candidate d-spacings,
  candidate persistence across center and smoothing perturbations, and
  post-detection comparison with source d-values.
- Unresolved: material and sample identity, acquisition conditions, detector
  metadata, raw intensity provenance, center uncertainty beyond the predeclared
  perturbations, calibration traceability, and crystallographic ground truth.
- Unsupported: material identification, phase assignment, reflection indexing,
  zone-axis assignment, structure confirmation, or engineering-release use.
