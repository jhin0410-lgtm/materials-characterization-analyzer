# SAED Baseline Workflow

## Purpose

The SAED workflow extracts a radial mean-intensity profile and descriptive ring candidates from an 8-bit or 16-bit diffraction image. It records the selected center, processing parameters, source SHA-256, optional reciprocal calibration, generated artifacts, warnings, and scientific limitations.

It does **not** index diffraction patterns, assign reflections, identify phases, determine zone axes, or validate crystallography.

## Input

Supported image formats:

- `.png`
- `.tif`
- `.tiff`
- `.bmp`

Stored `uint8` and `uint16` grayscale intensity depth is preserved. Color images are converted to grayscale. Display overlays are normalized to 8-bit, but radial measurements use the preserved grayscale values.

## Center selection

A diffraction center may be supplied with both:

```text
--center-x-px
--center-y-px
```

If neither is supplied, the image midpoint is used and the manifest records:

```text
saed_center_assumed_image_midpoint
```

The workflow does not claim automatic transmitted-beam center estimation. A wrong center can broaden, split, shift, or suppress radial candidates.

## Radial profile

The workflow calculates mean intensity in complete annuli around the selected center. The default maximum radius is the largest complete annulus contained in the image. A requested radius exceeding that limit is rejected rather than silently using partial azimuthal coverage.

The following are configurable:

- radial bin width;
- minimum radius used for candidate detection;
- maximum complete-annulus radius;
- bright or dark ring contrast;
- optional Savitzky-Golay smoothing;
- prominence threshold;
- minimum candidate separation.

Radial averaging can hide diffraction spots, arcs, texture, ellipticity, astigmatism, and detector distortion.

## Calibration contract

Without explicit calibration, the workflow exports pixel radius only. It never derives d-spacing from accelerating voltage, camera length, magnification, filenames, or image metadata alone.

Exactly one calibration route may be supplied:

### Direct reciprocal calibration

```text
--reciprocal-nm-inv-per-pixel
```

This project defines:

```text
g = 1 / d
```

Therefore:

```text
g_nm_inv = radius_px * reciprocal_nm_inv_per_pixel
d_nm = 1 / g_nm_inv
```

The alternative convention `q = 2*pi/d` is not used.

### Calibrated camera constant

```text
--camera-constant-nm-pixel
```

The stored relationship is:

```text
d_nm = camera_constant_nm_pixel / radius_px
```

### Single reference ring

Supply both:

```text
--reference-d-nm
--reference-radius-px
```

The workflow derives:

```text
camera_constant_nm_pixel = reference_d_nm * reference_radius_px
```

A single reference ring does not validate linearity, distortion, center selection, or calibration transfer between acquisition conditions.

## Example

First generate an explicitly synthetic image:

```bash
python scripts/generate_synthetic_saed_demo.py \
  --output outputs/saed_demo/synthetic_saed.tif
```

Then run:

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

The reciprocal calibration above is synthetic demonstration metadata. It is not a real instrument calibration.

## Outputs

- `saed_radial_profile.csv`
- `saed_ring_candidates.csv`
- `saed_features_long.csv`
- `saed_radial_profile.png`
- `saed_ring_overlay.png`
- `saed_analysis_manifest.json`

All automatic candidate features use `quality_flag=review_required`.

## Scientific closeout

A detected radial candidate is **diagnostic** only. It becomes suitable for crystallographic interpretation only after center validation, reciprocal calibration validation, distortion review, acquisition metadata review, comparison with suitable references, and expert indexing. Passing software tests does not establish diffraction calibration or phase identification.
