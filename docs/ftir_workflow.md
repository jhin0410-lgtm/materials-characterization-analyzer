# FTIR Baseline Workflow

## Scope

The FTIR workflow accepts a monotonic two-column spectrum containing wavenumber in `cm^-1` and one explicitly declared signal column.

Supported signal types:

- `absorbance`
- `transmittance_percent`
- `transmittance_fraction`

The workflow can convert transmittance to absorbance, apply an optional baseline, optionally smooth the baseline-corrected absorbance, detect descriptive band candidates, and export provenance-aware tables, figures, features, and a manifest.

It does not assign functional groups, compounds, phases, bonding mechanisms, or concentrations.

## Signal semantics

Signal type must be provided explicitly. Header text is not used to decide the physical meaning of the signal.

For transmittance fraction `T`:

```text
A = -log10(T)
```

For transmittance percent `%T`:

```text
A = -log10(%T / 100)
```

Transmittance values less than or equal to zero are rejected because logarithmic conversion is undefined. Values above 100% or above a fraction of 1 are not clipped; they are preserved and warned because they can arise from reference mismatch or other acquisition artifacts.

## Wavenumber axis

Strictly increasing and strictly decreasing axes are accepted. The original axis direction is recorded. Numerical processing tables are stored in ascending wavenumber order for deterministic calculations.

Diagnostic plots use the conventional FTIR presentation with high wavenumber on the left.

Duplicate, nonpositive, nonfinite, or nonmonotonic wavenumber values are rejected. The workflow does not infer or apply wavenumber calibration shifts.

## Baseline methods

Available methods:

- `none`
- `linear`
- `asls`

`none` preserves converted absorbance without baseline subtraction.

`linear` connects the first and final absorbance values.

`asls` applies asymmetric least-squares baseline estimation with recorded smoothness, asymmetry, and iteration parameters.

A selected baseline is a preprocessing choice. It is not a physical component model and can change candidate height, position, width, area, and detectability.

## Smoothing

Savitzky–Golay smoothing is optional. A smoothing window of zero disables it.

The requested window and polynomial order are recorded. The raw signal, converted absorbance, selected baseline, baseline-corrected absorbance, and processed absorbance are stored separately.

The workflow does not silently apply atmospheric correction, ATR correction, normalization, derivatives, spectral subtraction, or denoising beyond the explicitly selected Savitzky–Golay operation.

## Band candidates

Candidate detection uses `scipy.signal.find_peaks` on processed absorbance.

For each candidate, the workflow reports:

- wavenumber;
- raw input signal;
- converted absorbance;
- baseline and baseline-corrected absorbance;
- processed absorbance;
- prominence;
- descriptive FWHM;
- nonnegative baseline-corrected area within the FWHM interval.

These outputs are descriptive candidates, not fitted Gaussian, Lorentzian, Voigt, asymmetric, or deconvoluted bands.

Candidate positions do not establish an O-H, C-H, C=O, Si-O, phosphate, carbonate, polymer, oxide, or other functional-group or material assignment. Appropriate references, acquisition context, sampling-mode corrections, and expert review remain necessary.

## Sampling modes

The following sampling-mode labels can be recorded:

- `transmission`
- `atr`
- `diffuse_reflectance`
- `specular_reflectance`
- `unknown`

The workflow does not make these modes quantitatively comparable.

ATR spectra can depend on crystal material, contact, penetration depth, refractive indices, angle, and ATR correction. Transmission spectra can depend on path length, thickness, concentration, scattering, and reference quality. Diffuse- and specular-reflectance spectra require their own optical interpretation.

## Acquisition metadata

Optional metadata include:

- sampling mode;
- spectral resolution;
- scan count;
- detector;
- beamsplitter;
- apodization;
- ATR crystal;
- path length;
- background acquisition description;
- sample preparation.

Missing recommended metadata are warned rather than invented.

## Outputs

```text
ftir_processed_spectrum.csv
ftir_band_candidates.csv
ftir_features_long.csv
ftir_spectrum_with_candidates.png
ftir_analysis_manifest.json
```

All long-format FTIR features use `quality_flag=review_required`.

## Example

Generate a deterministic synthetic transmittance spectrum:

```bash
python scripts/generate_synthetic_ftir_demo.py \
  --output outputs/ftir_demo/synthetic_ftir.csv
```

Run the baseline:

```bash
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

The generated spectrum and metadata are synthetic software fixtures. They are not experimental evidence or a validated instrument export.

## Scientific validation

Passing tests confirms software behavior only.

Scientific use requires, at minimum:

- verified sample identity and preparation;
- correct signal semantics and units;
- suitable background/reference acquisition;
- validated sampling mode and optical geometry;
- spectral calibration and resolution information;
- evaluation of water-vapor and carbon-dioxide interference;
- review of saturation, scattering, contact, thickness, and path-length effects;
- preprocessing sensitivity checks;
- reference spectra or literature suitable for the actual material system;
- uncertainty and replicate assessment when quantitative comparison is intended.
