# Public DWCNT Multimodal Validation Case

This case study exercises the repository on real public characterization files while preserving scientific boundaries and file-level provenance.

## Public source

- Dataset: **In-depth characterization of 4 raw carbon nanomaterials: MWCNT, DWCNT, FLG and GNP**
- Repository: Recherche Data Gouv
- Persistent ID: `doi:10.57745/7KA2UG`
- Dataset version: `1.0`
- License: Etalab Open License 2.0
- Primary source label used here: `DWCNT`

Raw files are fetched from the repository API during execution. They are not committed to this Git repository.

## Why this dataset

The dataset contains Raman, FTIR, XPS, TGA-air, TGA-MS, and TEM measurements for the same four source material classes under a single published data package. This provides stronger provenance and comparability than mixing unrelated files selected only because they share a material name.

The common `DWCNT` label still does **not** prove that every instrument measured the identical physical aliquot. Cross-technique comparison is therefore classified as conditional.

## Executed scope

| Modality | Case action | Status |
|---|---|---|
| Raman | Adapt public semicolon table and run existing Raman contract | Conditionally comparable |
| FTIR | Adapt absorbance table and run existing FTIR contract | Conditionally comparable |
| XPS | Adapt wide scan and run existing XPS contract without inferred energy reference | Conditionally comparable |
| TGA-air | Decode CP1252 source, explicitly remove bounded initial stabilization, and run TGA contract | Conditionally comparable |
| TEM | Verify source, checksum, dimensions, metadata, and scale-bar review | Analysis blocked |
| SAED | No source file in dataset | Not available / not comparable |
| DSC | No source file in dataset | Not available / not comparable |

## TEM suitability decision

The selected TEM image shows intertwined nanotubes on a holey carbon support. The current TEM baseline performs global bright/dark Otsu region segmentation. It cannot distinguish nanotubes and bundles from support holes.

Running that method would create physically misleading region-size outputs, so the case deliberately blocks quantitative TEM segmentation. It records only source provenance, image dimensions and dtype, acquisition metadata, and the manually reviewed scale-bar ratio.

## TGA source adaptation

The TGA-air file is CP1252/ISO-8859 text and uses a documented seven-column export. The adapter maps:

1. temperature to `temperature_c`;
2. time to `time_s`;
3. the sixth column, reported mass retention percent, to `signal`.

The raw export contains a short initial temperature stabilization near room temperature. The adapter does not sort or interpolate the trajectory. It selects the earliest remaining suffix that is strictly increasing only when:

- excluded rows are no more than `max(100 rows, 5% of the file)`;
- the excluded temperature span is no more than `5 °C`;
- the remaining temperature and time axes are strictly increasing.

The exclusion count, source encoding, mapping, and source/canonical checksums are recorded in `case_source_manifest.json`.

### TGA mass metadata semantics

The source readme defines three sample-mass symbols that must not be relabeled:

- `W_sa = 3.531 mg`: starting DWCNT sample mass before the dry-air purge;
- `W_sp = 0.0247 mg`: sample mass change measured after the one-hour dry-air purge;
- `W_sm = 3.605 mg`: starting sample mass for the separate TGA-MS helium experiment.

`W_sp` is **not** an empty-crucible mass and `W_sm` is **not** a sample-plus-crucible mass. The case config now records the source meanings explicitly and states that neither missing quantity was inferred.

## Run

```bash
python scripts/discover_public_carbon_multimodal.py \
  --config case_studies/public_carbon_multimodal/case_config.json \
  --output outputs/public-carbon-case/discovery \
  --download

python scripts/execute_public_carbon_multimodal_case.py \
  --config case_studies/public_carbon_multimodal/case_config.json \
  --discovery outputs/public-carbon-case/discovery \
  --output outputs/public-carbon-case/result
```

## Export for `materials-data-analyzer`

After the case succeeds, export the persisted analysis evidence as a versioned file bundle:

```bash
python scripts/export_public_carbon_handoff_bundle.py \
  --config case_studies/public_carbon_multimodal/case_config.json \
  --result outputs/public-carbon-case/result
```

The exporter reads the persisted analysis manifest rather than importing any consumer code. It writes:

- `characterization_features_long.csv`: combined Raman, FTIR, XPS, and TGA numeric features using the stable 12-column contract;
- `sample_context.csv`: explicit source sample and dataset context keyed by `sample_id`;
- `characterization_handoff_bundle.json`: producer version, file checksums, counts, instruments, evidence references, join policy, and scientific claim boundary.

The consumer must resolve files through the bundle manifest, verify all checksums, and join only through explicit `sample_id`. Row-order joining, silent aggregation, and inferred metadata are prohibited. The source-file strings inside feature rows remain producer provenance labels; `source_sha256` is the content binding.

The dedicated GitHub Actions workflow performs the public acquisition and analysis and uploads the evidence for 14 days.

## Main outputs

```text
outputs/public-carbon-case/
├── discovery/
│   ├── inventory.json
│   ├── selected_files.json
│   ├── downloads.json
│   └── discovery_report.md
└── result/
    ├── canonical/
    ├── analyses/
    ├── case_source_manifest.json
    ├── case_analysis_manifest.json
    ├── comparability_matrix.csv
    ├── case_validation_report.md
    ├── case_summary.json
    ├── characterization_features_long.csv
    ├── sample_context.csv
    └── characterization_handoff_bundle.json
```

## Scientific closeout

**Evidence level: Diagnostic**

- Strongest evidence: public source identifiers and checksums, one dataset package, documented acquisition conditions, explicit adapters, and real-data execution of existing contracts.
- Primary limitation: identical physical aliquots are not confirmed and preparation differs between techniques.
- Suitable for: software integration validation, provenance demonstration, exploratory within-technique review, and cross-repository contract validation.
- Not suitable for: process-response modeling, phase confirmation, chemical-state assignment, functional-group proof, reaction or mechanism claims, or engineering release decisions without independent validation.
