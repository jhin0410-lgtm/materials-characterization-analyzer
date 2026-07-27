# Materials Characterization Analyzer

[![CI](https://github.com/jhin0410-lgtm/materials-characterization-analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/jhin0410-lgtm/materials-characterization-analyzer/actions/workflows/ci.yml)

`materials-characterization-analyzer` is a Python CLI project for organizing XRD, SEM, EDS, and Raman characterization inputs into validated tables, diagnostic figures, provenance-aware manifests, and cautious summaries.

The project is an analysis-support workflow. It is not an automatic material-identification system, and it does not confirm phases, compounds, bonds, chemical states, or mechanisms from isolated instrument outputs.

## Current Scope

- **XRD**: two-column import, smoothing, peak detection, FWHM, optional Scherrer estimate, plot, and peak table.
- **SEM**: image import, grayscale conversion, Otsu thresholding, external-contour measurements, overlay, and size histogram.
- **EDS**: composition-table validation, sorting, charting, and cautious elemental summary.
- **Raman**: two-column import, optional asymmetric least-squares baseline correction, optional Savitzky-Golay smoothing, automatic peak detection, descriptive FWHM, within-FWHM area, diagnostic plot, and provenance manifest.
- **Integrated XRD/SEM/EDS report**: combines existing result tables into one Markdown report.
- **Result contract**: stores source SHA-256, acquisition metadata, preprocessing history, artifacts, long-format features, warnings, limitations, and software/schema versions.

Raman is currently a standalone baseline workflow. It is not yet inserted into the legacy XRD/SEM/EDS integrated Markdown report.

## Scientific Design Principles

- Missing metadata are reported, not invented.
- Raw and processed signals are kept separately when preprocessing can affect interpretation.
- Units and calculation methods are stored with exported features.
- Software validation and scientific validation are treated as different requirements.
- Automatic peak or region detection is marked for review.
- Synthetic demo data exercise software behavior only and are not experimental evidence.

## Instrument Workflows

### XRD

The XRD module accepts selected `.csv`, `.txt`, and `.xy` two-column files. Standardized columns are:

- `two_theta`
- `intensity`

It can smooth intensity, detect peaks, estimate FWHM, optionally calculate Scherrer crystallite-size estimates, and save:

- `xrd_pattern_with_peaks.png`
- `xrd_peak_table.csv`

Detected peaks do not confirm phases. Scherrer output is an approximate crystallite-size estimate, not a particle-size measurement.

### SEM

The SEM module reads an image and requires a manually supplied `microns-per-pixel` value. It can apply simple threshold-based segmentation and save:

- `sem_overlay.png`
- `sem_particle_size_distribution.png`
- `sem_measurements.csv`

Threshold-derived regions depend on contrast, focus, magnification, preparation, scale calibration, crop, and segmentation settings. They require manual review.

### EDS

The EDS module accepts a CSV composition table with standardized columns:

- `element`
- `weight_percent`
- `atomic_percent`

It saves:

- `eds_composition_table.csv`
- `eds_composition_bar_chart.png`

EDS supports elemental-composition review. It does not determine crystal structure, confirm a phase, or establish chemical state by itself.

### Raman

The Raman module accepts `.csv`, `.txt`, and `.tsv` two-column spectra. Standardized columns are:

- `raman_shift_cm_1`
- `intensity`

The default workflow performs asymmetric least-squares baseline correction, Savitzky-Golay smoothing, peak detection, FWHM calculation, and integration of non-negative baseline-corrected intensity within each FWHM interval.

It saves:

- `raman_processed_spectrum.csv`
- `raman_peak_table.csv`
- `raman_features_long.csv`
- `raman_spectrum_with_peaks.png`
- `raman_analysis_manifest.json`

No Raman band assignment is generated. See [`docs/raman_workflow.md`](docs/raman_workflow.md) for processing definitions and limitations.

## Project Structure

```text
materials-characterization-analyzer/
|-- .github/workflows/ci.yml
|-- README.md
|-- pyproject.toml
|-- requirements.txt
|-- data/
|   `-- demo/
|       |-- README.md
|       |-- synthetic_xrd.csv
|       |-- synthetic_sem.png
|       |-- synthetic_eds.csv
|       `-- synthetic_raman.csv
|-- docs/
|   |-- analysis_limitations.md
|   |-- characterization_contract.md
|   |-- raman_workflow.md
|   `-- images/
|-- outputs/
|   `-- .gitkeep
|-- src/mca/
|   |-- cli.py
|   |-- cli_entry.py
|   |-- contracts.py
|   |-- provenance.py
|   |-- feature_records.py
|   |-- raman.py
|   |-- raman_cli.py
|   |-- raman_features.py
|   |-- importers.py
|   |-- xrd.py
|   |-- sem.py
|   |-- eds.py
|   |-- report.py
|   `-- utils.py
`-- tests/
```

`outputs/` is intended for local generated artifacts and is ignored by Git except for `outputs/.gitkeep`.

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

An alternative dependency installation is:

```bash
pip install -r requirements.txt
```

## Quick Start

### Integrated XRD/SEM/EDS demo

```bash
mca analyze-all \
  --xrd data/demo/synthetic_xrd.csv \
  --sem data/demo/synthetic_sem.png \
  --eds data/demo/synthetic_eds.csv \
  --microns-per-pixel 0.05 \
  --output outputs/integrated_demo
```

Windows PowerShell:

```powershell
mca analyze-all `
  --xrd data/demo/synthetic_xrd.csv `
  --sem data/demo/synthetic_sem.png `
  --eds data/demo/synthetic_eds.csv `
  --microns-per-pixel 0.05 `
  --output outputs/integrated_demo
```

### Raman demo

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

The acquisition values above are demo metadata, not metadata recovered from a real instrument file.

### Individual legacy modules

```bash
mca xrd --input data/demo/synthetic_xrd.csv --output outputs/xrd
mca sem --input data/demo/synthetic_sem.png --microns-per-pixel 0.05 --output outputs/sem
mca eds --input data/demo/synthetic_eds.csv --output outputs/eds
mca report --xrd outputs/xrd/xrd_peak_table.csv --sem outputs/sem/sem_measurements.csv --eds outputs/eds/eds_composition_table.csv --output outputs/report
```

## Feature and Provenance Exports

The legacy one-row feature table remains available:

```bash
mca analyze-all \
  --xrd data/demo/synthetic_xrd.csv \
  --sem data/demo/synthetic_sem.png \
  --eds data/demo/synthetic_eds.csv \
  --microns-per-pixel 0.05 \
  --output outputs/integrated_demo \
  --extract-features \
  --sample-id demo_sample
```

To additionally export the stable long-format characterization contract:

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

This writes:

- `characterization_features_long.csv`
- `characterization_manifest.json`

Raman writes its own long-format feature file and single-analysis manifest through `mca raman`.

## Demo Data Notice

All files under `data/demo/` are synthetic inputs created only to exercise the software:

- `synthetic_xrd.csv`: generated diffraction-like peaks;
- `synthetic_sem.png`: generated bright regions for thresholding;
- `synthetic_eds.csv`: generated composition values;
- `synthetic_raman.csv`: generated curved background and three Raman-like peaks.

They are not real measurements, vendor exports, or evidence for any material. See [`data/demo/README.md`](data/demo/README.md).

## Limitations

- The project does not automatically identify materials or confirm phases.
- XRD peak positions and FWHM require appropriate calibration and reference context.
- SEM segmentation is a transparent baseline, not validated universal particle segmentation.
- EDS composition depends on acquisition conditions, corrections, geometry, and sample preparation.
- Raman baseline, smoothing, prominence, and distance settings can alter extracted peaks.
- Raman FWHM and area are descriptive values, not fitted or deconvoluted line-shape parameters.
- Uncertainty propagation and vendor-specific raw-format import are not yet implemented.
- Passing tests confirms software behavior only; it does not establish scientific validity.

See [`docs/analysis_limitations.md`](docs/analysis_limitations.md) for the detailed scientific limitations.

## Testing

```bash
pytest -q
```

Pytest temporary files are written under the ignored `outputs/pytest-tmp` directory.

## Related Project

[`materials-data-analyzer`](https://github.com/jhin0410-lgtm/materials-data-analyzer) handles tabular experiment, process, battery, quality, reliability, and modeling workflows. This repository handles instrument-specific spectra, images, diffraction outputs, and characterization metadata.

The repositories remain independently installable and should exchange data through versioned contracts and stable sample/measurement identifiers rather than row order or inferred filenames.

## Next Development Order

1. Review and merge the provenance-aware result contract.
2. Stabilize the Raman baseline workflow on representative real or public spectra with complete metadata.
3. Add general TEM image validation and scale-aware measurement without copying SEM interpretation assumptions.
4. Add calibrated SAED as a separate diffraction workflow.
5. Add XPS, FTIR, and TGA/DSC only with instrument-specific metadata and limitations.
6. Extend the integrated report after individual analyzers and contracts are stable.
