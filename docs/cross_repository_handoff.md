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
- scientific evidence level, limitations, and allowed/prohibited uses.

All manifest paths are relative filenames stored beside the manifest. Consumers must verify checksums before reading tables.

## Required consumer behavior

A conforming consumer must:

1. verify `schema_version` and `bundle_type`;
2. resolve referenced files relative to the manifest without path traversal;
3. verify every recorded SHA-256;
4. validate the exact feature schema and numeric values;
5. validate unique sample-context IDs and exact sample-ID set agreement;
6. preserve quality flags, methods, units, preprocessing IDs, and source hashes;
7. reject row-order joins, silent duplicate aggregation, and inferred metadata;
8. retain the producer scientific claim boundary.

## Scientific boundary

The bundle proves a software and provenance handoff when validation succeeds. It does not prove:

- identical physical aliquots across instruments;
- sample comparability beyond recorded evidence;
- phase, compound, chemical-state, or mechanism assignments;
- causal process-response relationships;
- predictive or engineering-release readiness.

The public DWCNT case is classified as `Diagnostic` and is suitable for contract validation and descriptive multimodal integration only.
