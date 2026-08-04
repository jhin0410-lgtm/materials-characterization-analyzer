# Characterization handoff bundle validation

`mca validate-handoff` verifies the portable characterization feature bundle produced by `mca.handoff_bundle.write_characterization_handoff_bundle` before it is consumed by another repository or workflow.

## Purpose

The validator checks file identity and contract consistency. It does not interpret features, aggregate measurements, infer missing metadata, or establish that different techniques measured the same physical aliquot.

Validated items include:

- bundle schema and bundle type;
- duplicate JSON keys and unknown top-level fields;
- feature and sample-context file byte counts and SHA-256 values;
- exact long-format feature columns;
- finite numeric feature values;
- nonblank sample, measurement, instrument, feature, unit, method, and quality fields;
- feature counts, sample counts, measurement counts, instruments, and quality-flag counts;
- exact `sample_id` agreement between feature and context tables;
- source, analysis, and comparability evidence references;
- the fail-closed join contract: `sample_id` only, no row-order join, no aggregation, and no missing-metadata inference;
- the producer-declared evidence level.

## Run

Print the validation summary:

```bash
mca validate-handoff \
  --bundle outputs/public-rwgs-case/result/handoff_bundle
```

Write checksum-bound validation evidence:

```bash
mca validate-handoff \
  --bundle outputs/public-rwgs-case/result/handoff_bundle \
  --output outputs/public-rwgs-case/handoff-validation
```

Generated evidence:

- `handoff_bundle_validation_summary.json`
- `handoff_bundle_validation_report.md`
- `handoff_bundle_validation_artifact_manifest.json`

The output directory must be absent or empty. Existing files are never overwritten.

## Success boundary

A valid bundle reports:

```text
valid_characterization_handoff_bundle
```

This means only that the current files match the producer manifest and the join/schema contract is internally consistent.

It does **not** establish:

- identical physical aliquots or sampling locations;
- compatible instrument conditions or material states;
- cross-modal comparability;
- phase, chemical-state, functional-group, particle, defect, or mechanism identity;
- causal or predictive relationships;
- model-training readiness;
- engineering-release readiness.

A consumer must continue to verify the scientific question, sample comparability, units, target definitions, exclusions, leakage boundaries, and source licences.

## Build a generic bundle

Use an explicit schema `1.0` config when a case does not have a dedicated exporter:

```bash
mca build-handoff \
  --config handoff_build_config.json \
  --output outputs/portable-handoff
```

The builder resolves evidence paths relative to the config, copies only the three declared evidence files into a staging directory, writes the bundle, validates the completed bundle, and atomically publishes the output directory. An existing output is never overwritten and failed builds remove the staging directory.

The builder does not derive sample identity, comparability, evidence level, or scientific limitations. These must be stated in the config.
