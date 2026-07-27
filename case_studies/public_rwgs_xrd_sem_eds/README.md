# Public RWGS XRD–SEM–EDS Diagnostic Case

This case validates the repository's XRD, SEM-readiness, EDS-adapter, provenance, and cross-technique comparability contracts on a small public catalyst-characterization dataset.

It is intentionally not a conventional `mca analyze-all` example. The selected SEM image is unsuitable for the current global-threshold particle-region method, so quantitative SEM segmentation is blocked rather than replaced with misleading particle-size results.

## Public source

- Dataset: **Characterization datasets of RWGS catalysts**
- DOI: `10.5281/zenodo.13474908`
- Dataset version: `v1`
- Published: `2024-08-29`
- License: `CC BY 4.0`
- Creators: Maria Balaguer and Elena Vicente

The workflow downloads the public files directly from Zenodo. Raw archives and extracted instrument files are not committed to this repository.

## Selected nominal sample

The case uses the nominal `5%Cu/Al2O3` sample because it is the only sample label represented in all three available source groups:

- XRD: `_5%Cu_Al2O3.ASC`
- SEM: `5%Cu_Al2O3.tif`
- EDS: `5Cu-Al2O3_Site 3_2023-09-18_17-48-56.xlsx`

The synthesis protocol describes incipient-wetness impregnation of gamma-alumina with aqueous `Cu(NO3)2·3H2O`, drying at 120 °C for 2 h, and calcination at 450 °C for 6 h.

The filenames and study context support a common nominal sample label. They do **not** prove that XRD, SEM, and EDS used the identical physical aliquot.

## Execution contract

### XRD

The source ASC pattern is converted to canonical CSV with:

- 4,401 rows;
- 2θ range from 2.01° to 90.01°;
- constant 0.02° step;
- no sorting;
- no interpolation;
- no numeric-value modification.

The baseline XRD analyzer then performs smoothing, diagnostic peak-candidate detection, and descriptive FWHM extraction.

The source package does not document the X-ray source, wavelength, diffractometer, or instrumental broadening. Therefore:

- no phase assignment is performed;
- no Scherrer crystallite-size estimate is generated;
- cross-study peak-width comparison remains limited.

### SEM

The image footer reports:

- GeminiSEM 500-8203017153;
- 1.45 kX magnification;
- 2.9 mm working distance;
- 1.50 kV accelerating voltage;
- ESB signal;
- 10 µm embedded scale bar.

Manual scale review records a 130-pixel endpoint separation, corresponding to `0.0769230769 µm/pixel`. The annotation footer is cropped only for qualitative field review.

Quantitative segmentation is blocked with status `blocked_method_mismatch`. The ESB image contains compositional contrast across overlapping catalyst agglomerates; global Otsu external-contour segmentation cannot reliably distinguish complete particles from Cu-rich regions, overlap, fractures, support morphology, or background.

No `sem_measurements.csv`, particle-size distribution, or area-fraction feature is produced.

### EDS

The source XLSX reports weight percent for seven elements. Every source row is preserved:

- C: 16.11 wt%
- O: 29.71 wt%
- Al: 25.43 wt%
- Si: 0.20 wt%
- Ni: 21.49 wt%
- Cu: 6.54 wt%
- Au: 0.52 wt%

The workbook note says C, Si, and Au were discarded for interpretation. The adapter records that note but does not silently apply the exclusion.

The workbook does not provide atomic percent. The case derives atomic percent algebraically from source-reported weight percent and explicitly configured atomic weights. Derived atomic percent is labelled as derived and must not be described as instrument-reported.

The reported `21.49 wt% Ni` conflicts with the nominal Cu/gamma-Al2O3 synthesis description. This is retained as a data-quality warning; the case does not confirm nominal composition.

## Run locally

```bash
python scripts/discover_public_rwgs_xrd_sem_eds.py \
  --config case_studies/public_rwgs_xrd_sem_eds/discovery_config.json \
  --output outputs/public-rwgs-case/discovery

python scripts/run_public_rwgs_xrd_sem_eds_case.py \
  --config case_studies/public_rwgs_xrd_sem_eds/case_config.json \
  --discovery outputs/public-rwgs-case/discovery \
  --output outputs/public-rwgs-case/result
```

Windows PowerShell uses the same commands with backticks or one-line invocations.

## Main outputs

- `discovery/downloads.json`
- `discovery/archive_inventories.json`
- `result/selected_source_manifest.json`
- `result/adapters/xrd_5wt_cu_al2o3.csv`
- `result/adapters/eds_source_reported_weight_percent.csv`
- `result/adapters/eds_with_derived_atomic_percent.csv`
- `result/analyses/xrd/xrd_peak_table.csv`
- `result/analyses/xrd/xrd_pattern_with_peaks.png`
- `result/analyses/sem/sem_suitability.json`
- `result/analyses/sem/sem_field_cropped.png`
- `result/analyses/eds/eds_composition_table.csv`
- `result/analyses/eds/eds_composition_bar_chart.png`
- `result/characterization_features_long.csv`
- `result/characterization_manifest.json`
- `result/comparability_matrix.csv`
- `result/case_validation_report.md`
- `result/case_summary.json`

## Scientific closeout

- **Result:** `Diagnostic`
- **Strongest evidence:** checksum-verified public acquisition, same nominal sample-label mapping, value-preserving XRD adaptation, complete EDS row preservation, and explicit SEM suitability blocking.
- **Primary limitation:** identical aliquots are unconfirmed; SEM quantitative segmentation is unsuitable; Ni conflicts with the nominal synthesis description; key XRD and EDS acquisition metadata are absent.
- **Evidence that would change the conclusion:** aliquot-linkage records, complete instrument/acquisition metadata, an explanation or repeat measurement for Ni, validated SEM labels or segmentation references, and XRD radiation/instrument metadata.
- **Suitable for:** software integration, provenance, adapter, and data-quality diagnostics.
- **Not suitable for:** phase confirmation, quantitative particle-size claims, nominal-composition confirmation, catalytic-mechanism claims, or engineering release decisions.
