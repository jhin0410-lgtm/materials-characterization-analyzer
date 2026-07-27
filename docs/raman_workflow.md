# Raman Baseline Workflow

## Scope

The Raman workflow reads a two-column spectrum, records preprocessing, extracts descriptive peaks, and writes provenance-aware outputs. It does not assign Raman bands, identify a material, confirm a phase, or infer a mechanism.

Supported source formats are `.csv`, `.txt`, and `.tsv`. The standardized columns are:

- `raman_shift_cm_1`
- `intensity`

Headerless numeric two-column files are also accepted. Duplicate Raman-shift values are rejected rather than averaged silently.

## Command

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

On Windows PowerShell:

```powershell
mca raman `
  --input data/demo/synthetic_raman.csv `
  --output outputs/raman_demo `
  --sample-id demo_raman `
  --laser-wavelength-nm 532 `
  --laser-power-mw 1 `
  --exposure-time-s 10 `
  --accumulation-count 3 `
  --spectral-resolution-cm-1 2
```

The acquisition metadata arguments are optional, but omitted values are recorded as warnings in the manifest. Values are not inferred from filenames or peak locations.

## Processing

The default processing sequence is:

1. validate and sort the Raman-shift axis;
2. asymmetric least-squares baseline estimation;
3. Savitzky-Golay smoothing of the baseline-corrected signal;
4. peak detection using relative prominence and minimum sample distance;
5. descriptive FWHM calculation;
6. trapezoidal integration of non-negative baseline-corrected intensity within each FWHM interval.

Baseline correction can be disabled with `--baseline-method none`. Smoothing can be disabled with `--smoothing-window 0`. Every requested processing parameter is stored in the analysis manifest.

## Outputs

- `raman_processed_spectrum.csv`: raw, baseline, corrected, and processed signals;
- `raman_peak_table.csv`: peak position, corrected intensity, prominence, FWHM bounds, and within-FWHM area;
- `raman_features_long.csv`: stable long-format feature records;
- `raman_spectrum_with_peaks.png`: raw/baseline and processed diagnostic plots;
- `raman_analysis_manifest.json`: source SHA-256, metadata, preprocessing, warnings, limitations, and generated artifacts.

## Scientific limitations

- Automatic peak detection does not identify compounds, bonds, phases, or vibrational modes.
- Peak height, FWHM, and area depend on baseline and smoothing choices.
- The reported FWHM is a descriptive width from the processed signal, not a fitted Gaussian, Lorentzian, or Voigt parameter.
- The reported area covers only the FWHM interval and is not a deconvoluted full-peak area.
- Fluorescence, cosmic rays, saturation, peak overlap, calibration error, focus, polarization, laser heating, acquisition time, laser power, and spectral resolution can materially affect results.
- Spectra should not be compared quantitatively unless sample preparation, acquisition conditions, calibration, preprocessing, and units are compatible.

The included Raman demo spectrum is synthetic and exists only to exercise the software workflow. It is not experimental evidence for any material.
