# TGA and DSC Thermal Baseline Workflow

## Scope

The `mca thermal` command provides two explicit modes:

- `tga`: mass-retention and descriptive DTG-like mass-loss candidates;
- `dsc`: endotherm-oriented heat-flow processing and descriptive endothermic/exothermic candidates.

The workflow supports analysis review and provenance capture. It does not identify reactions, decomposition mechanisms, phases, melting, crystallization, glass transition, or quantitative composition.

## Input Contract

Accepted file types are `.csv`, `.txt`, and `.tsv`.

Headered files must contain:

- `temperature_c` or a supported temperature alias;
- one signal column;
- optional `time_s`.

Headerless files may contain either:

```text
temperature_c, signal
```

or:

```text
temperature_c, time_s, signal
```

This baseline accepts one strictly increasing temperature segment only. Cooling scans, isothermal holds, and multisegment programs require explicit segmentation and are rejected rather than silently reordered.

## Explicit Signal Types

### TGA

- `mass_percent`
- `mass_fraction`
- `mass_mg`

For `mass_mg`, an explicit `--initial-mass-mg` is preferred. When it is omitted, the first valid mass value is used as the reference and a warning is recorded.

### DSC

- `heat_flow_mw`
- `heat_flow_w_g`

For `heat_flow_mw`, `--sample-mass-mg` is required to derive `W/g`. Without sample mass, the raw mW signal remains usable for descriptive candidates, but normalized heat flow and J/g enthalpy are not reported.

## TGA Processing

1. validate one increasing temperature segment and optional increasing time axis;
2. convert the explicit mass signal to mass-retention percent;
3. optionally apply Savitzky–Golay smoothing;
4. calculate the negative temperature derivative as positive mass-loss rate;
5. detect descriptive positive mass-loss-rate candidates;
6. calculate candidate temperature, prominence, descriptive FWHM, and mass change within the FWHM interval.

The detected temperatures are not validated reaction onsets. The workflow does not implement extrapolated onset, kinetic models, or evolved-gas interpretation.

## DSC Processing

The user must specify whether endothermic heat flow is plotted `up` or `down`. The signal is converted internally to an endotherm-positive convention, and this choice is recorded.

The baseline methods are:

- `none`
- `linear`

After optional smoothing, the workflow detects positive endothermic and negative exothermic candidates separately. Candidate FWHM and area are descriptive and are not fitted component parameters.

## Enthalpy Rules

`enthalpy_within_fwhm_j_g` is generated only when:

1. the working heat-flow signal is mass-normalized in `W/g`; and
2. either a valid `time_s` axis or a positive `heating_rate_c_min` is available.

With time:

```text
enthalpy = integral(heat_flow_W_g dt)
```

With constant heating rate:

```text
enthalpy = integral(heat_flow_W_g dT) * 60 / heating_rate_C_min
```

This is a diagnostic within-FWHM value, not a validated total transition enthalpy. Calibration, baseline, transition boundaries, sample mass, pan matching, and thermal program must be independently validated.

## Recommended Metadata

- atmosphere;
- heating rate;
- gas flow;
- sample mass;
- crucible or pan material;
- instrument model;
- calibration reference;
- sample preparation and thermal history.

If a time axis is supplied, the workflow derives the median heating rate and warns when it differs from the supplied heating rate by more than 10%.

## Outputs

```text
thermal_processed_data.csv
thermal_event_candidates.csv
thermal_features_long.csv
thermal_curve_with_candidates.png
thermal_analysis_manifest.json
```

All automatic feature records use `quality_flag=review_required`.

## Example: TGA

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

## Example: DSC

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

The example data are synthetic software fixtures, not real instrument evidence.

## Scientific Limitations

- TGA mass gain can reflect oxidation, adsorption, buoyancy, drift, baseline error, or other effects; the software does not decide the cause.
- DTG-like candidates depend on smoothing, temperature spacing, derivative calculation, and prominence settings.
- DSC endotherm direction differs across instruments and exports and must be supplied explicitly.
- Linear baseline subtraction is not universally valid.
- Glass transition requires a different baseline and step-change analysis and is not detected here.
- Candidate peaks do not distinguish melting, crystallization, curing, oxidation, evaporation, decomposition, or solid-state transformation.
- Cooling, holds, cycling, modulated DSC, simultaneous TGA-DSC, and multisegment programs require dedicated contracts.
- Passing tests validates software behavior only, not experimental validity or scientific interpretation.
