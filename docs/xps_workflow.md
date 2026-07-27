# XPS Spectrum Baseline Workflow

## Purpose

The XPS workflow provides a reproducible software baseline for two-column binding-energy spectra. It records source identity, energy referencing, background selection, optional smoothing, descriptive candidate extraction, generated artifacts, warnings, and scientific limitations.

It does not identify elements, assign orbitals, determine oxidation states, fit chemical components, calculate atomic percentages, or confirm compounds.

## Input contract

Supported files:

- `.csv`
- `.txt`
- `.tsv`

Required numeric columns:

- binding energy in eV;
- intensity.

Recognized binding-energy aliases include `binding_energy_ev`, `Binding Energy (eV)`, `binding energy`, `be`, and `energy_ev`. Recognized intensity aliases include `intensity`, `counts`, `cps`, and `signal`.

The binding-energy axis must be strictly monotonic. Descending input is common in XPS and is accepted. The workflow records the original direction and stores the processed table in ascending order for deterministic numerical operations. Duplicate or nonmonotonic energies are rejected rather than silently averaged or reordered.

## Energy referencing

No binding-energy reference is inferred automatically.

The user may select exactly one route:

1. direct shift:

```bash
--energy-shift-ev 0.6
```

2. observed-to-target reference:

```bash
--reference-observed-ev 284.2 \
--reference-target-ev 284.8
```

The second route applies:

```text
energy_shift_ev = reference_target_ev - reference_observed_ev
corrected_binding_energy_ev = raw_binding_energy_ev + energy_shift_ev
```

The workflow does not automatically assume a C 1s reference, adventitious carbon value, Fermi edge, internal standard, or instrument calibration state. An explicit reference can still be scientifically wrong if the reference feature is misidentified, shifted, overlapped, differentially charged, or unsuitable for the sample.

If no reference is provided, raw and corrected binding energies remain numerically equal and the manifest records `energy_reference_not_provided`.

## Background choices

Available methods:

- `none`;
- `linear`;
- `shirley`.

The linear background connects the first and final intensity values over the selected input spectrum.

The iterative Shirley implementation:

- operates on the ascending binding-energy axis;
- anchors the background at the first and final intensity values;
- clips negative residuals to zero during the iterative integral;
- records convergence, iteration count, tolerance, and maximum iterations.

A Shirley background is not universally valid. Endpoint selection, inelastic-loss structure, overlapping peaks, sloped continua, satellites, and spectrum truncation can materially change the result. This baseline does not implement Tougaard backgrounds or user-defined local fitting windows.

## Smoothing

Savitzky-Golay smoothing is optional and disabled by default:

```bash
--smoothing-window 0
```

A positive odd-compatible window applies smoothing to the background-corrected signal. The requested window and polynomial order are recorded. Smoothing can change candidate height, width, prominence, area, and detectability.

## Candidate detection

The workflow uses `scipy.signal.find_peaks` on the processed background-corrected signal.

For each candidate it records:

- raw binding energy;
- corrected binding energy;
- raw intensity;
- selected background intensity;
- background-corrected intensity;
- processed intensity;
- prominence;
- descriptive FWHM;
- left and right FWHM bounds;
- non-negative background-corrected area within the FWHM interval.

These are descriptive candidates, not fitted peak components. FWHM is not a Gaussian, Lorentzian, Voigt, Doniach-Sunjic, asymmetric, multiplet, satellite, or spin-orbit fit parameter. Within-FWHM area is not a full peak area and must not be used as quantitative composition.

## Acquisition metadata

Optional metadata fields include:

- spectrum type: `survey`, `high_resolution`, or `unknown`;
- user-supplied region label;
- X-ray source;
- photon energy;
- pass energy;
- energy step size;
- dwell time;
- scan count;
- takeoff angle;
- charge-neutralization state.

Missing recommended metadata are warnings, not inferred values. A reported step size that differs materially from the numerical axis spacing is also warned.

## CLI example

Generate an explicit synthetic fixture:

```bash
python scripts/generate_synthetic_xps_demo.py \
  --output outputs/xps_demo/synthetic_xps.csv
```

Run the baseline:

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

The metadata above are synthetic demonstration values. They are not recovered from a real instrument export and are not evidence for a material.

## Outputs

- `xps_processed_spectrum.csv`
- `xps_peak_candidates.csv`
- `xps_features_long.csv`
- `xps_spectrum_with_candidates.png`
- `xps_analysis_manifest.json`

The processed table keeps raw and corrected binding-energy axes and raw, background, corrected, and processed intensity values together.

## Scientific closeout

The software implementation can be validated with synthetic fixtures and automated tests. Scientific use additionally requires suitable energy calibration, sample history, charge-control assessment, acquisition settings, background justification, representative regions, reference spectra or databases, peak-model justification, uncertainty assessment, and expert interpretation.

Until those conditions are met, automatic XPS outputs should be treated as diagnostic and exploratory rather than chemical-state or quantitative claims.
