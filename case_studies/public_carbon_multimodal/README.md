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

The dedicated GitHub Actions workflow performs the same acquisition and analysis and uploads the evidence for 14 days.

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
    └── case_summary.json
```

## Scientific closeout

**Evidence level: Diagnostic**

- Strongest evidence: public source identifiers and checksums, one dataset package, documented acquisition conditions, explicit adapters, and real-data execution of existing contracts.
- Primary limitation: identical physical aliquots are not confirmed and preparation differs between techniques.
- Suitable for: software integration validation, provenance demonstration, and exploratory within-technique review.
- Not suitable for: phase confirmation, chemical-state assignment, functional-group proof, reaction or mechanism claims, or engineering release decisions without independent validation.
