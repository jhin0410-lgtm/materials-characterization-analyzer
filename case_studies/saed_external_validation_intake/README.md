# SAED external-validation intake

This case provides a fail-closed intake gate for a future raw or demonstrably lossless calibrated SAED dataset. It is designed for issue #36 and should be run before any analyzer execution, parameter selection, reflection comparison, or phase/zone-axis assessment.

## Command

```bash
mca saed-validation-intake \
  --manifest path/to/saed_validation_intake_manifest.json \
  --data-root path/to/checksum_bound_saed_dataset \
  --output outputs/saed_validation_intake
```

Start from `manifest_template.example.json`, preserve the source filenames and directory identities, replace every placeholder SHA-256 with the checksum of the corresponding local file, and record only source- or operator-supported metadata. Do not infer sample, acquisition, detector, center, calibration, material, or preprocessing fields from appearance or filename order.

## Required source evidence

Each active pattern must have:

- a stable pattern, sample, acquisition, and material identifier;
- a raw detector or demonstrably lossless representation retaining original intensity information;
- exact local SHA-256 identity;
- accelerating voltage and detector model;
- a traceable center and center source;
- exactly one declared reciprocal calibration route: direct reciprocal scale, camera constant, or reference d-spacing/radius pair;
- a calibration source;
- an explicit preprocessing list, using `["none"]` when no preprocessing occurred;
- no use in center, smoothing, prominence, radius-bound, or candidate-count selection.

The active cohort must contain at least two independent samples and two independent acquisitions, no exact duplicate active content, valid reuse authorization, supported material identity, and evidence that it was not used to develop or select the target analyzer.

## Statuses

- `blocked_source_or_calibration_readiness`: one or more source, identity, independence, representation, calibration, file-integrity, or review gates failed.
- `ready_to_freeze_saed_analysis_protocol`: intake evidence is sufficient to freeze analysis/indexing/reference rules, but analyzer execution is still premature.
- `ready_for_predeclared_saed_external_evaluation`: all reviews, analysis parameters, indexing rules, references, metrics, uncertainty, exclusions, protocol ID, and canonical manifest checksum are frozen.

Even the final status does not establish crystallographic accuracy or engineering readiness. It authorizes only one predeclared evaluation run under the frozen protocol.

## Outputs

- `saed_validation_intake_patterns.csv`
- `saed_validation_intake_summary.json`
- `saed_validation_intake_report.md`
- `saed_validation_intake_artifact_manifest.json`

The source files are not copied into the output. The intake reads them only to verify path safety, byte size, and SHA-256. It performs no image decoding, intensity conversion, normalization, smoothing, center estimation, analyzer execution, indexing, or phase assignment.

## Scientific boundary

Synthetic files used by CI validate software behavior only. Manifest declarations are not independent proof that material identity, calibration, acquisition independence, or reference assignments are true. Those claims require source documentation and separate review. If evidence is unavailable, retain the blocker instead of weakening the contract.
