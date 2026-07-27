# Materials Characterization Analyzer

[![CI](https://github.com/jhin0410-lgtm/materials-characterization-analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/jhin0410-lgtm/materials-characterization-analyzer/actions/workflows/ci.yml)

`materials-characterization-analyzer` is a provenance-aware Python CLI for organizing XRD, SEM, EDS, Raman, TEM, SAED, and XPS characterization inputs into validated tables, diagnostic figures, long-format features, manifests, and cautious summaries.

It is an analysis-support workflow, not an automatic material-identification, phase-confirmation, chemical-state-assignment, or quantitative-composition system.

## Current Scope

- **XRD**: two-column import, smoothing, peak detection, FWHM, optional Scherrer estimate, plot, and peak table.
- **SEM**: grayscale image import, Otsu thresholding, external-contour measurements, overlay, and size histogram.
- **EDS**: composition-table validation, sorting, charting, and cautious elemental summary.
- **Raman**: baseline correction, optional smoothing, peak candidates, descriptive FWHM, within-FWHM area, plot, features, and manifest.
- **TEM**: 8/16-bit image preservation, explicit bright/dark contrast segmentation, ROI, scale-aware region descriptors, plots, features, and manifest.
- **SAED**: 8/16-bit diffraction image preservation, explicit center, complete-annulus radial profile, ring candidates, optional calibrated `d_nm`, plots, features, and manifest.
- **XPS**: monotonic two-column binding-energy import, explicit energy referencing, Shirley/linear/no background, optional smoothing, descriptive peak candidates, plots, features, and manifest.
- **Integrated XRD/SEM/EDS report**: combines existing result tables into one Markdown summary.
- **Result contract**: records source SHA-256, acquisition metadata, preprocessing history, artifacts, long-format features, warnings, limitations, and software/schema versions.

Raman, TEM, SAED, and XPS are standalone baseline workflows and are not yet forced into the legacy integrated report.

## Scientific Design Principles

- Missing metadata are reported, not invented.
- Raw and processed data are kept separately when preprocessing can affect interpretation.
- Units, methods, source identity, and preprocessing identifiers accompany exported features.
- Automatic candidates and regions are marked `review_required`.
- Software validation and scientific validation are separate.
- Synthetic demo data exercise software behavior only; they are not experimental evidence.

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

The metadata above are synthetic demonstration values, not recovered instrument metadata.

### TEM

Generate an explicit synthetic image:

```bash
python scripts/generate_synthetic_tem_demo.py \
  --output outputs/tem_demo/synthetic_tem.tif
```

Run the baseline:

```bash
mca tem \
  --input outputs/tem_demo/synthetic_tem.tif \
  --output outputs/tem_demo/result \
  --sample-id synthetic_tem_demo \
  --nm-per-pixel 0.25 \
  --contrast bright
```

`nm_per_pixel` must come from validated calibration for real measurements. The workflow does not infer it from a label, filename, or magnification value.

### SAED

Generate an explicit synthetic diffraction image:

```bash
python scripts/generate_synthetic_saed_demo.py \
  --output outputs/saed_demo/synthetic_saed.tif
```

Run the radial baseline:

```bash
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

The reciprocal calibration above is synthetic demonstration metadata. Real `d_nm` output requires validated calibration. This project defines reciprocal magnitude as `g = 1/d`, not `q = 2*pi/d`.

### XPS

Generate an explicit synthetic survey spectrum:

```bash
python scripts/generate_synthetic_xps_demo.py \
  --output outputs/xps_demo/synthetic_xps.csv
```

Run the spectrum baseline:

```bash
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

No energy reference is inferred automatically. Use either `--energy-shift-ev` or a complete `--reference-observed-ev` / `--reference-target-ev` pair when a scientifically justified reference is available. The metadata above are synthetic demonstration values.

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
- Passing tests confirms software behavior only; it does not establish experimental validity or scientific interpretation.

Detailed limitations:

- [`docs/analysis_limitations.md`](docs/analysis_limitations.md)
- [`docs/characterization_contract.md`](docs/characterization_contract.md)
- [`docs/raman_workflow.md`](docs/raman_workflow.md)
- [`docs/tem_workflow.md`](docs/tem_workflow.md)
- [`docs/saed_workflow.md`](docs/saed_workflow.md)
- [`docs/xps_workflow.md`](docs/xps_workflow.md)

## Testing

```bash
pytest -q
```

Pytest temporary files are written under the ignored `outputs/pytest-tmp` directory.

## Data and Repository Safety

Only commit public, anonymized, and appropriately licensed data. Do not commit unpublished research data, institution-owned confidential data, customer data, proprietary vendor exports, or other sensitive instrument files.

Synthetic demo inputs and generators must be clearly labelled and must not be presented as experimental evidence.

## Related Project

[`materials-data-analyzer`](https://github.com/jhin0410-lgtm/materials-data-analyzer) handles tabular experiment, process, battery, quality, reliability, and modeling workflows.

The repositories remain independently installable and should exchange information through stable sample/measurement identifiers and versioned contracts rather than row order or inferred filenames.

## Next Development Order

1. Validate Raman, TEM, SAED, and XPS baselines on representative public or appropriately shareable data with complete metadata.
2. Add explicit XPS component fitting only after line-shape, constraints, reference, and uncertainty contracts are defined.
3. Add FTIR with spectral preprocessing and band-assignment safeguards.
4. Add TGA/DSC with temperature-program, atmosphere, mass normalization, and event-definition metadata.
5. Extend integrated reporting only after individual contracts and scientific validation gates are stable.
