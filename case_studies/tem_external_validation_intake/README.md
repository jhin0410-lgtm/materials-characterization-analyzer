# TEM External-Validation Intake

`mca tem-validation-intake` validates a proposed independent cobalt-oxide TEM segmentation dataset before annotation or model inference.

It checks declared metadata, safe local paths, file existence, and SHA-256 identity. It does not infer missing metadata, inspect material identity, train a model, compute segmentation metrics, or certify an engineering release.

## Command

```bash
mca tem-validation-intake \
  --manifest path/to/tem_validation_intake_manifest.json \
  --data-root path/to/checksum_bound_dataset \
  --output outputs/tem_validation_intake
```

The data root remains unchanged. Files are read only to verify byte size and SHA-256.

## Required dataset evidence

The manifest must declare:

- a stable dataset ID and version;
- source type and reuse authorization;
- exact cobalt-oxide material domain;
- whether sample and acquisition IDs are source- or operator-assigned rather than inferred;
- target-training and model-selection non-use;
- creator overlap and cross-dataset lineage independence;
- at least two required blinded independent labelers.

Each image must have a unique stable image ID, safe relative path, SHA-256, sample ID, acquisition ID, TEM/HRTEM modality, representation class, detector-intensity status, and explicit model-development non-use fields.

Rendered publication figures are not accepted as raw validation images.

## Annotation contract

For every active image, external-evaluation preparation requires:

- at least two unique blinded independent labelers;
- no exposure to model predictions;
- no use of the annotation in training, threshold selection, hyperparameter tuning, or model selection;
- exactly one adjudicated consensus label;
- one frozen label-definition version.

## Evaluation protocol contract

Model inference remains blocked until all of the following are recorded as passed or frozen:

- source metadata review;
- image-content audit;
- label-content audit;
- target-training content-overlap audit;
- checksum-bound test manifest with a canonical SHA-256 stored in `frozen_manifest_sha256`;
- metrics;
- confidence-interval method;
- exclusion rules;
- stable frozen protocol ID.

The canonical digest normalizes only the self-referential `test_manifest_checksum_frozen` and `frozen_manifest_sha256` fields. Dataset identity, active/excluded images, annotations, audit states, metric/uncertainty/exclusion freeze fields, and the protocol ID remain checksum-bound. Run the intake before final freeze, copy `manifest_identity.computed_manifest_sha256` into `frozen_manifest_sha256`, then set `test_manifest_checksum_frozen` to `true` without changing any other field.

Even then, the intake reports only `ready_for_predeclared_external_evaluation`. An independent performance claim requires the later frozen inference run and its validated results.

## Statuses

- `blocked_dataset_or_image_readiness`: lineage, representation, non-use, independent-unit, or duplicate-content gate failed.
- `ready_for_blinded_annotation_pilot`: source images pass intake, but labels have not been created.
- `independent_annotation_incomplete`: some labels exist, but blinded independent annotation or consensus is incomplete.
- `ready_to_freeze_evaluation_protocol`: labels are complete, but audits or protocol fields are not all frozen.
- `ready_for_predeclared_external_evaluation`: the intake contract permits the single predeclared inference step.

## Scientific limitation

A successful intake is evidence that the declared local contract is internally consistent and checksum-bound. It is not independent proof that the material identity, acquisition history, calibration, annotation quality, or scientific generalization claim is correct.

Synthetic fixtures used in tests validate software behavior only and are not real-world external-validation evidence.
