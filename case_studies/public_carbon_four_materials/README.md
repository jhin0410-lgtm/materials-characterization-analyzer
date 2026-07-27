# Public Carbon Four-Material Multimodal Case

This case extends the single-sample DWCNT workflow to four explicit public sample classes from one versioned dataset package:

- `public-dwcnt` - double-walled carbon nanotubes;
- `public-mwcnt` - multi-walled carbon nanotubes;
- `public-flg` - few-layer graphene;
- `public-gnp` - graphene nanoplatelets.

## Public source

- Dataset: **In-depth characterization of 4 raw carbon nanomaterials: MWCNT, DWCNT, FLG and GNP**
- Repository: Recherche Data Gouv
- Persistent ID: `doi:10.57745/7KA2UG`
- Dataset version: `1.0`
- License: Etalab Open License 2.0

Raw files are fetched at runtime and are not committed to this repository.

## Exact source binding

The case config records the Dataverse `datafile_id` and expected filename for every selected Raman, FTIR, XPS wide-scan, TGA-air, and TEM-readiness source. Execution stops when either identifier differs from the current inventory. There is no token-scoring fallback.

The selected Raman file is one reported replicate per material class. Replicate spectra are not silently averaged or pooled.

## TGA mass metadata correction

The source readme defines:

- `W_sa`: starting sample mass before the dry-air purge;
- `W_sp`: sample mass change measured after the one-hour dry-air purge;
- `W_sm`: starting sample mass for the separate TGA-MS helium experiment.

The case records those meanings explicitly. `W_sp` is not labeled as an empty-crucible mass, and `W_sm` is not labeled as a sample-plus-crucible mass. No missing empty-crucible or sample-plus-crucible value is inferred.

## Run

```bash
python scripts/run_public_carbon_four_materials_case.py \
  --config case_studies/public_carbon_four_materials/case_config.json \
  --output outputs/public-carbon-four-materials
```

The output directory must be absent or empty. Existing files are not deleted or overwritten.

## Workflow

```text
Dataverse metadata inventory
-> exact datafile ID and filename checks
-> checksum-verified source download
-> existing single-sample Raman / FTIR / XPS / TGA contracts x 4 samples
-> TEM source readiness checks with quantitative segmentation blocked
-> 16-analysis persisted manifest
-> four-row sample context
-> versioned multi-sample characterization handoff bundle
-> Diagnostic closeout report
```

## Main outputs

```text
outputs/public-carbon-four-materials/
├── source_inventory.json
├── samples/
│   ├── public-dwcnt/
│   ├── public-mwcnt/
│   ├── public-flg/
│   └── public-gnp/
├── case_source_manifest.json
├── case_analysis_manifest.json
├── comparability_matrix.csv
├── characterization_features_long.csv
├── sample_context.csv
├── characterization_handoff_bundle.json
├── case_summary.json
└── case_validation_report.md
```

## Scientific closeout

**Evidence level: Diagnostic**

Supported:

- exact public source acquisition and checksum-backed provenance;
- real-data execution for four explicit `sample_id` values;
- 16 Raman/FTIR/XPS/TGA analysis results in one persisted manifest;
- multi-sample cross-repository file-contract validation;
- descriptive, review-required within-technique feature transfer.

Not supported:

- treating DWCNT, MWCNT, FLG, and GNP as controlled levels of one process variable;
- process-response modeling or optimization;
- causal or mechanistic interpretation;
- identical physical aliquots across techniques;
- phase, chemical-state, functional-group, or reaction confirmation;
- predictive generalization or engineering-release decisions.

This case advances interoperability from one sample to four real samples. It still does not provide the controlled process histories, compatible outcomes, replicates, and uncertainty needed for process science.
