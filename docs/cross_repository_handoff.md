# Cross-Repository Characterization Handoff

## Purpose

`materials-characterization-analyzer` exports numeric characterization features for file-based consumption by independently installed repositories such as `materials-data-analyzer`.

The producer and consumer must not import each other's internal modules. The exchange boundary is a versioned bundle containing:

- `characterization_features_long.csv`;
- `sample_context.csv`;
- `characterization_handoff_bundle.json`.

## Feature contract

The long-format feature table uses these columns in order:

```text
sample_id
measurement_id
instrument
feature_name
feature_label
value
unit
method
source_file
source_sha256
preprocessing_id
quality_flag
```

`sample_id` is the only allowed join key. Matching IDs are necessary but do not independently prove physical specimen identity.

## Bundle manifest

Schema version `1.0` records:

- producer repository and software/schema versions;
- feature and sample-context paths, SHA-256 values, sizes, columns, and counts;
- instrument, measurement, quality-flag, source-hash, and preprocessing coverage;
- source, analysis, and comparability evidence references;
- explicit join policy;
- scientific evidence level and claim boundary;
- a machine-readable `downstream_use_policy`.

All manifest paths are relative filenames stored beside the manifest. Consumers must verify checksums before reading tables.

## Downstream-use policy

Newly written bundles always include a policy. When no stronger policy is supplied, the producer emits a conservative default that permits only `display` and `descriptive` workflows.

The ordered use levels are:

```text
display < descriptive < association < predictive < causal < engineering
```

The policy records:

- `maximum_allowed_use`;
- `feature_stage`: `observable`, `derived`, or `interpreted`;
- `evidence_level` matching `scientific_closeout.evidence_level`;
- `review_status`;
- `independence_group_field`;
- `measurement_timing` relative to the modeled outcome;
- explicit causal-design and operational-validation flags;
- unresolved limitations.

Fail-closed rules include:

1. `Inconclusive` or `Unsupported` evidence cannot authorize use above descriptive.
2. `Diagnostic` evidence cannot authorize use above association.
3. Association or stronger use requires an explicit independent grouping field retained in `sample_context.csv`.
4. Predictive or stronger use requires features measured before the outcome.
5. Causal use requires an explicitly validated causal design.
6. Engineering use additionally requires explicit operational validation.
7. Unreviewed interpreted features cannot authorize use above descriptive.

These checks prevent silent promotion of diagnostic features, row-level pseudo-replication, post-outcome leakage, and unsupported engineering claims. They do not prove that the declared grouping, timing, causal design, or validation evidence is scientifically sufficient.

## Required consumer behavior

A conforming consumer must:

1. verify `schema_version` and `bundle_type`;
2. resolve referenced files relative to the manifest without path traversal;
3. verify every recorded SHA-256;
4. validate the exact feature schema and numeric values;
5. validate unique sample-context IDs and exact sample-ID set agreement;
6. preserve quality flags, methods, units, preprocessing IDs, and source hashes;
7. reject row-order joins, silent duplicate aggregation, and inferred metadata;
8. retain the producer scientific claim boundary;
9. independently validate the downstream-use policy;
10. require the requested association or model split group to match the producer-declared independence field;
11. block the workflow before output generation when eligibility fails;
12. preserve the eligibility decision in consumer audit outputs.

Legacy bundles without `downstream_use_policy` remain readable for compatibility, but consumers must treat them as descriptive-only.

## Scientific boundary

The bundle proves a software and provenance handoff when validation succeeds. It does not prove:

- identical physical aliquots across instruments;
- sample comparability beyond recorded evidence;
- phase, compound, chemical-state, or mechanism assignments;
- causal process-response relationships;
- predictive generalization;
- engineering-release readiness.

The public DWCNT and NIST AM-Bench optical-metrology cases are classified as `Diagnostic` and are suitable for contract validation and descriptive integration only.
