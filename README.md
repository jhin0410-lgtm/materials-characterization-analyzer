# Materials Characterization Analyzer

[![CI](https://github.com/jhin0410-lgtm/materials-characterization-analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/jhin0410-lgtm/materials-characterization-analyzer/actions/workflows/ci.yml)
[![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD_3--Clause-blue.svg)](LICENSE)

`materials-characterization-analyzer` is a provenance-aware Python CLI for organizing XRD, SEM, EDS, Raman, TEM, SAED, XPS, FTIR, TGA, and DSC characterization inputs into validated tables, diagnostic figures, long-format features, manifests, and cautious summaries.

It is an analysis-support workflow, not an automatic material-identification, phase-confirmation, chemical-state-assignment, functional-group-assignment, reaction-mechanism, or quantitative-composition system.

## Current Scope

- **XRD**: two-column import, smoothing, peak detection, FWHM, optional Scherrer estimate, plot, and peak table.
- **SEM**: grayscale image import, Otsu thresholding, external-contour measurements, overlay, and size histogram.
- **EDS**: composition-table validation, sorting, charting, and cautious elemental summary.
- **Raman**: baseline correction, optional smoothing, peak candidates, descriptive FWHM, within-FWHM area, plot, features, and manifest.
- **TEM**: 8/16-bit image preservation, explicit bright/dark contrast segmentation, ROI, scale-aware region descriptors, plots, features, and manifest.
- **SAED**: 8/16-bit diffraction image preservation, explicit center, complete-annulus radial profile, ring candidates, optional calibrated `d_nm`, plots, features, and manifest.
- **XPS**: monotonic two-column binding-energy import, explicit energy referencing, Shirley/linear/no background, optional smoothing, descriptive peak candidates, plots, features, and manifest.
- **FTIR**: monotonic two-column wavenumber import, explicit absorbance/transmittance semantics, transmittance-to-absorbance conversion, optional baseline and smoothing, descriptive band candidates, plots, features, and manifest.
- **TGA/DSC**: explicit thermal mode and signal units, single increasing heating-segment validation, TGA mass-retention/DTG-like candidates, DSC endotherm-oriented candidates, optional diagnostic enthalpy, plots, features, and manifest.
- **Integrated XRD/SEM/EDS report**: combines existing result tables into one Markdown summary.
- **Result contract**: records source SHA-256, acquisition metadata, preprocessing history, artifacts, long-format features, warnings, limitations, and software/schema versions.

Raman, TEM, SAED, XPS, FTIR, TGA, and DSC are standalone baseline workflows and are not forced into the legacy integrated report.

## Scientific Design Principles

- Missing metadata are reported, not invented.
- Raw and processed data are kept separately when preprocessing can affect interpretation.
- Units, methods, source identity, and preprocessing identifiers accompany exported features.
- Automatic candidates and regions are marked `review_required`.
- Software validation and scientific validation are separate.
- Synthetic demo data exercise software behavior only; they are not experimental evidence.

## Public Repository Policy

- The project source code is released under the [BSD 3-Clause License](LICENSE).
- External datasets retain their original licenses. Referencing or downloading a dataset does not relicense it under the software license.
- Only synthetic fixtures and explicitly public, appropriately licensed assets may be committed.
- Downloaded raw datasets, private instrument exports, generated outputs, local configuration, credentials, and caches must remain untracked.
- Security-sensitive reports should follow [SECURITY.md](SECURITY.md).
- Proposed changes should follow [CONTRIBUTING.md](CONTRIBUTING.md), including the separation between software and scientific validation.

Public real-data case studies fetch their external sources at runtime, verify source identifiers and checksums, and do not vendor external raw datasets into this repository:

- `case_studies/public_carbon_multimodal/`: DWCNT Raman/FTIR/XPS/TGA diagnostic case;
- `case_studies/public_zr15nb_dsc/`: checksum-bound Zr15Nb DSC real-data case;
- `case_studies/public_finds_saed/`: calibrated FINDS SAED real-image diagnostic case.
- `case_studies/phaset3m_co3o4_candidate_audit/`: checksum-bound processed Co3O4 tilt-series diagnostic audit; not external segmentation validation.

The TEM external-validation intake under `case_studies/tem_external_validation_intake/` is a fail-closed dataset contract, not a certified scientific dataset.

## Installation

Python `3.10` or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Verify the installed public version:

```bash
mca --version
```

## Commands

### Integrated XRD / SEM / EDS

```bash
mca analyze-all \
  --xrd data/demo/synthetic_xrd.csv \
  --sem data/demo/synthetic_sem.png \
  --eds data/demo/synthetic_eds.csv \
  --microns-per-pixel 0.05 \
  --output outputs/integrated_demo \
  --sample-id demo_sample \
  --export-feature-records
```

### Raman

```bash
mca raman \
  --input data/demo/synthetic_raman.csv \
  --output outputs/raman_demo \
  --sample-id demo_raman \
  --laser-wavelength-nm 532 \
  --laser-power-mw 1 \
  --exposure-time-s 10 \
  --accumulation-count 3 \
  --spectral-resolution-cm-1 2
```

### TEM

```bash
python scripts/generate_synthetic_tem_demo.py \
  --output outputs/tem_demo/synthetic_tem.tif

mca tem \
  --input outputs/tem_demo/synthetic_tem.tif \
  --output outputs/tem_demo/result \
  --sample-id synthetic_tem_demo \
  --nm-per-pixel 0.25 \
  --contrast bright
```

`nm_per_pixel` must come from validated calibration for real measurements.

### SAED

```bash
python scripts/generate_synthetic_saed_demo.py \
  --output outputs/saed_demo/synthetic_saed.tif

mca saed \
  --input outputs/saed_demo/synthetic_saed.tif \
  --output outputs/saed_demo/result \
  --sample-id synthetic_saed_demo \
  --center-x-px 128 \
  --center-y-px 128 \
  --reciprocal-nm-inv-per-pixel 0.01 \
  --min-radius-px 8 \
  --prominence-fraction 0.08
```

Real `d_nm` output requires validated reciprocal calibration. This project defines reciprocal magnitude as `g = 1/d`, not `q = 2*pi/d`.

### XPS

```bash
python scripts/generate_synthetic_xps_demo.py \
  --output outputs/xps_demo/synthetic_xps.csv

mca xps \
  --input outputs/xps_demo/synthetic_xps.csv \
  --output outputs/xps_demo/result \
  --sample-id synthetic_xps_demo \
  --spectrum-type survey \
  --background-method shirley \
  --xray-source "synthetic demo" \
  --photon-energy-ev 1486.6 \
  --pass-energy-ev 100 \
  --step-size-ev 0.5 \
  --charge-neutralization unknown
```

No energy reference is inferred automatically. Use either `--energy-shift-ev` or a complete `--reference-observed-ev` / `--reference-target-ev` pair when scientifically justified.

### FTIR

```bash
python scripts/generate_synthetic_ftir_demo.py \
  --output outputs/ftir_demo/synthetic_ftir.csv

mca ftir \
  --input outputs/ftir_demo/synthetic_ftir.csv \
  --output outputs/ftir_demo/result \
  --sample-id synthetic_ftir_demo \
  --signal-type transmittance_percent \
  --baseline-method linear \
  --sampling-mode transmission \
  --spectral-resolution-cm-1 4 \
  --scan-count 16 \
  --detector "synthetic demo" \
  --background-description "synthetic reference"
```

FTIR signal type is mandatory. Header text is not used to infer whether the second column is absorbance or transmittance.

### TGA

```bash
python scripts/generate_synthetic_thermal_demo.py \
  --mode tga \
  --output outputs/thermal_demo/synthetic_tga.csv

mca thermal \
  --input outputs/thermal_demo/synthetic_tga.csv \
  --output outputs/thermal_demo/tga_result \
  --sample-id synthetic_tga_demo \
  --mode tga \
  --signal-type mass_percent \
  --atmosphere N2 \
  --heating-rate-c-min 10 \
  --sample-mass-mg 10 \
  --crucible-material alumina
```

### DSC

```bash
python scripts/generate_synthetic_thermal_demo.py \
  --mode dsc \
  --output outputs/thermal_demo/synthetic_dsc.csv

mca thermal \
  --input outputs/thermal_demo/synthetic_dsc.csv \
  --output outputs/thermal_demo/dsc_result \
  --sample-id synthetic_dsc_demo \
  --mode dsc \
  --signal-type heat_flow_w_g \
  --endotherm-direction up \
  --baseline-method linear \
  --atmosphere N2 \
  --heating-rate-c-min 10 \
  --sample-mass-mg 10 \
  --crucible-material aluminum
```

The thermal baseline accepts one strictly increasing heating segment. Cooling, holds, cycling, and multisegment programs require explicit segmentation and are not silently reordered.

### Public real-data case studies

Run the complete checksum-bound DSC case:

```bash
python scripts/audit_public_zr15nb_dsc_source.py \
  --config case_studies/public_zr15nb_dsc/case_config.json \
  --output outputs/public-zr15nb-dsc/source-audit

python scripts/run_public_zr15nb_dsc_case.py \
  --config case_studies/public_zr15nb_dsc/case_config.json \
  --output outputs/public-zr15nb-dsc/result

python scripts/review_public_zr15nb_dsc_candidates.py \
  --config case_studies/public_zr15nb_dsc/case_config.json \
  --result outputs/public-zr15nb-dsc/result
```

Run the calibrated FINDS SAED diagnostic case:

```bash
python scripts/audit_public_finds_saed_source.py \
  --config case_studies/public_finds_saed/case_config.json \
  --output outputs/public-finds-saed/source-audit

python scripts/run_public_finds_saed_case.py \
  --config case_studies/public_finds_saed/case_config.json \
  --output outputs/public-finds-saed/result

python scripts/verify_public_finds_saed_case.py \
  --audit outputs/public-finds-saed/source-audit \
  --result outputs/public-finds-saed/result
```

These cases are diagnostic. Their automatic candidates are not phase, reaction, reflection, or structure assignments.

## Main Outputs

### XRD

- `xrd_pattern_with_peaks.png`
- `xrd_peak_table.csv`

### SEM

- `sem_overlay.png`
- `sem_particle_size_distribution.png`
- `sem_measurements.csv`

### EDS

- `eds_composition_table.csv`
- `eds_composition_bar_chart.png`

### Raman

- `raman_processed_spectrum.csv`
- `raman_peak_table.csv`
- `raman_features_long.csv`
- `raman_spectrum_with_peaks.png`
- `raman_analysis_manifest.json`

### TEM

- `tem_measurements.csv`
- `tem_segmentation_mask.png`
- `tem_overlay.png`
- `tem_region_size_distribution.png`
- `tem_intensity_histogram.png`
- `tem_features_long.csv`
- `tem_analysis_manifest.json`

### SAED

- `saed_radial_profile.csv`
- `saed_ring_candidates.csv`
- `saed_features_long.csv`
- `saed_radial_profile.png`
- `saed_ring_overlay.png`
- `saed_analysis_manifest.json`

### XPS

- `xps_processed_spectrum.csv`
- `xps_peak_candidates.csv`
- `xps_features_long.csv`
- `xps_spectrum_with_candidates.png`
- `xps_analysis_manifest.json`

### FTIR

- `ftir_processed_spectrum.csv`
- `ftir_band_candidates.csv`
- `ftir_features_long.csv`
- `ftir_spectrum_with_candidates.png`
- `ftir_analysis_manifest.json`

### TGA / DSC

- `thermal_processed_data.csv`
- `thermal_event_candidates.csv`
- `thermal_features_long.csv`
- `thermal_curve_with_candidates.png`
- `thermal_analysis_manifest.json`

## Scientific Boundaries

- XRD peak candidates do not confirm phases.
- Scherrer output is an approximate crystallite-size estimate, not particle size.
- SEM and TEM threshold-derived regions require validated scale, segmentation, sampling, and contrast interpretation.
- EDS does not establish phase or chemical state by itself.
- Raman candidates do not assign compounds, bonds, phases, or vibrational modes.
- TEM contrast regions are not automatically particles, pores, grains, defects, precipitates, phases, or lattice features.
- SAED radial candidates are not indexed reflections, phases, zone axes, or crystal structures.
- SAED `d_nm` is absent unless explicit calibration is provided.
- XPS candidates do not identify elements, orbitals, chemical states, oxidation states, satellites, multiplets, or fitted components.
- XPS energy referencing is never inferred automatically, and within-FWHM area is not quantitative composition.
- FTIR candidates do not identify functional groups, compounds, phases, or bonding mechanisms.
- FTIR transmittance conversion and band areas are not quantitative concentration analysis.
- TGA candidates do not identify decomposition reactions, oxidation, evaporation, adsorption, or chemical species.
- DSC candidates do not confirm melting, crystallization, curing, oxidation, glass transition, or solid-state transformation.
- Thermal FWHM, area, and diagnostic enthalpy are not validated onset, fitted-component, or quantitative-composition results.
- Passing tests confirms software behavior only; it does not establish experimental validity or scientific interpretation.

Detailed limitations:

- [`docs/analysis_limitations.md`](docs/analysis_limitations.md)
- [`docs/characterization_contract.md`](docs/characterization_contract.md)
- [`docs/raman_workflow.md`](docs/raman_workflow.md)
- [`docs/tem_workflow.md`](docs/tem_workflow.md)
- [`docs/saed_workflow.md`](docs/saed_workflow.md)
- [`docs/xps_workflow.md`](docs/xps_workflow.md)
- [`docs/ftir_workflow.md`](docs/ftir_workflow.md)
- [`docs/thermal_workflow.md`](docs/thermal_workflow.md)

## Testing and Build Validation

```bash
pytest -q
python -m build
```

Pytest temporary files are written under the ignored `outputs/pytest-tmp` directory. CI also installs the built wheel, verifies `mca --version`, and checks that local raw/private/output paths were not packaged.

## Data and Repository Safety

Only commit public, anonymized, appropriately licensed, and scientifically documented data. Do not commit unpublished research data, institution-owned confidential data, customer data, proprietary vendor exports, personally identifiable information, credentials, or other sensitive instrument files.

The repository ignores common environment files, key material, local raw/private/downloaded datasets, generated outputs, caches, IDE files, and temporary files. This reduces accidental exposure but does not replace a manual review of staged changes.

If a secret has ever been committed, adding it to `.gitignore` or deleting it in a later commit does not revoke it or remove it from Git history. Rotate the secret and clean the affected history when necessary.

Synthetic demo inputs and generators must be clearly labelled and must not be presented as experimental evidence.

## Contributing and Security

- Contribution requirements: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security reporting: [SECURITY.md](SECURITY.md)

## Citation and Releases

- Machine-readable citation metadata: [CITATION.cff](CITATION.cff)
- User-facing change history: [CHANGELOG.md](CHANGELOG.md)
- Versioned release validation: [docs/release_checklist.md](docs/release_checklist.md)

When citing an analysis, cite both this software version and the original experimental dataset or publication recorded in the analysis provenance. The BSD 3-Clause software license does not replace external data licenses.

## Related Project

[`materials-data-analyzer`](https://github.com/jhin0410-lgtm/materials-data-analyzer) handles tabular experiment, process, battery, quality, reliability, and modeling workflows.

The repositories remain independently installable and should exchange information through stable sample/measurement identifiers and versioned contracts rather than row order or inferred filenames.

## License

The software in this repository is licensed under the [BSD 3-Clause License](LICENSE). Third-party datasets, publications, and externally hosted files remain subject to their own licenses and terms.

## Next Development Order

1. Acquire independent raw/lossless cobalt-oxide TEM data that passes `mca tem-validation-intake`; do not retrain the segmentation model before evaluation-set independence is protected.
2. Acquire a raw or lossless calibrated SAED dataset with material, acquisition, detector, and crystallographic reference metadata; the FINDS JPEG case remains software-integration evidence only.
3. Add a representative real-data case for any remaining baseline workflow only when it fills a defined scientific-validation gap rather than duplicating the existing RWGS, DWCNT, Zr15Nb DSC, or FINDS SAED cases.
4. Define and validate stable sample/measurement exchange contracts with `materials-data-analyzer` before cross-repository integration.
5. Add explicit XPS component fitting only after line-shape, constraints, reference, and uncertainty contracts are defined.
6. Add HRTEM lattice-fringe analysis only after calibration, ROI, FFT, uncertainty, and validation contracts are defined.
7. Add cooling, hold, cycling, simultaneous TGA-DSC, and multisegment thermal workflows only with explicit segment contracts.
8. Extend integrated reporting only after individual contracts and scientific validation gates are stable.
