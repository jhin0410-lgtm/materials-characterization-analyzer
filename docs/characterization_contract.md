# Characterization Result Contract

## Purpose

The v0.2 contract provides a stable boundary between instrument-specific analyzers and downstream reporting, comparison, or modeling workflows. It records what was measured, what processing was applied, which files were generated, and which limitations remain.

The contract does not identify materials, assign phases, infer mechanisms, or convert missing metadata into assumed values.

## Core objects

### `PreprocessingStep`

Records one ordered preprocessing or analysis operation:

- `step_id`
- `operation`
- `parameters`
- `notes`

### `FeatureRecord`

Stores one numeric sample-level feature in long format:

- `sample_id`
- `measurement_id`
- `instrument`
- `feature_name`
- `feature_label`
- `value`
- `unit`
- `method`
- `source_file`
- `source_sha256`
- `preprocessing_id`
- `quality_flag`

The `feature_label` field is used for dimensions such as an EDS element. For example, an Fe weight-percent row uses `feature_name=element_weight_percent` and `feature_label=Fe`. This avoids adding a new CSV column for every possible element.

### `AnalysisResult`

Stores one instrument measurement with:

- source path and SHA-256 digest;
- acquisition metadata supplied by the user or importer;
- ordered preprocessing history;
- generated tables and figures;
- long-format feature records;
- warnings and scientific limitations;
- software and schema versions.

## Analyze-all export

The existing workflow remains unchanged unless the new flag is supplied.

```bash
python -m mca.cli analyze-all \
  --xrd data/demo/synthetic_xrd.csv \
  --sem data/demo/synthetic_sem.png \
  --eds data/demo/synthetic_eds.csv \
  --microns-per-pixel 0.05 \
  --output outputs \
  --sample-id demo_synthetic_sample \
  --export-feature-records
```

This additionally writes:

- `outputs/characterization_features_long.csv`
- `outputs/characterization_manifest.json`

The existing `--extract-features` option still writes the backward-compatible one-row `sample_features.csv` file.

## Export from existing result tables

Available result tables can be converted independently. At least one result table is required.

```bash
python -m mca.cli feature-records \
  --sample-id sample_001 \
  --xrd-peaks outputs/xrd_peak_table.csv \
  --xrd-source data/raw/sample_001.xy \
  --sem-measurements outputs/sem_measurements.csv \
  --sem-source data/raw/sample_001_sem.png \
  --eds-composition outputs/eds_composition_table.csv \
  --eds-source data/raw/sample_001_eds.csv \
  --output outputs
```

When an original source file is not supplied, the manifest records `raw_source_file_not_provided`. When existing result tables are imported without known processing history, it records `preprocessing_history_not_provided`. The tool does not reconstruct or guess either item.

## Scientific safeguards

- XRD peak features do not confirm phases.
- A Scherrer estimate stored in the same unit as an unspecified wavelength is exported with `unit=same_as_wavelength` and `quality_flag=unit_unresolved`; it is not silently relabeled as nanometres.
- SEM threshold-derived features use `quality_flag=review_required`.
- EDS composition features use `quality_flag=review_required` and do not imply phase or chemical-state identification.
- SHA-256 digests support source-file identity checks, but they do not prove that sample identity, acquisition metadata, calibration, or experimental design are correct.

## Extension rule for Raman, TEM, and later analyzers

A new analyzer should:

1. preserve its raw source path and SHA-256 digest;
2. validate instrument-specific axes, units, and required metadata;
3. record every material preprocessing step;
4. emit stable `FeatureRecord` rows with explicit units and methods;
5. attach quality warnings and scientific limitations;
6. return or construct an `AnalysisResult` without changing existing public CLI behavior unless a deliberate migration is documented.

Raman should be the next implementation because it can reuse one-dimensional spectral utilities while keeping Raman-specific baseline, peak, laser, and assignment rules separate from XRD. TEM image analysis should follow, with SAED treated as a separate calibrated diffraction workflow rather than a generic TEM image option.
