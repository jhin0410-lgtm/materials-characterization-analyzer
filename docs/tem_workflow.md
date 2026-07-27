# TEM Image Baseline Workflow

## Scope

The TEM baseline analyzes explicitly selected bright or dark image-contrast regions. It is a transparent image-measurement workflow, not an automatic particle, phase, pore, defect, or lattice-identification system.

Supported image containers are PNG, JPEG, TIFF, BMP, and PGM when OpenCV can decode them as 8-bit or 16-bit integer images.

This workflow does not perform:

- SAED ring or spot indexing;
- diffraction calibration or d-spacing calculation;
- HRTEM FFT interpretation;
- lattice-fringe spacing measurement;
- phase assignment;
- automatic distinction between mass-thickness, diffraction, phase, or Z contrast.

SAED and HRTEM analysis should be implemented as separate calibrated workflows.

## Required inputs

- source image;
- stable sample ID;
- user-verified `nm_per_pixel` scale;
- explicit `bright` or `dark` contrast target.

The scale is stored as user supplied. The tool does not infer calibration from a scale bar or filename.

## Optional acquisition metadata

- imaging mode: `bf_tem`, `df_tem`, `stem`, `haadf_stem`, `hrtem`, or `other`;
- accelerating voltage in kV;
- magnification;
- specimen thickness in nm;
- signed defocus in nm;
- explicit pixel ROI.

Missing metadata are recorded as warnings rather than reconstructed.

## Processing sequence

1. Decode the source image without changing an 8-bit or 16-bit stored pixel depth.
2. Convert BGR/BGRA input to grayscale while preserving integer dtype.
3. Apply an optional explicit ROI crop.
4. Apply no blur by default, or an explicitly requested Gaussian blur.
5. Apply Otsu thresholding to the selected bright or dark contrast.
6. Detect external contours above the configured minimum pixel area.
7. Optionally exclude border-touching regions and record the exclusion count.
8. Measure region area, equivalent diameter, perimeter, centroid, raw mean intensity, area fraction, and border contact.
9. Export provenance, preprocessing history, warnings, limitations, and long-format features.

## Output files

- `tem_measurements.csv`
- `tem_segmentation_mask.png`
- `tem_overlay.png`
- `tem_region_size_distribution.png`
- `tem_intensity_histogram.png`
- `tem_features_long.csv`
- `tem_analysis_manifest.json`

All automatically generated TEM feature records use `quality_flag=review_required`.

## Synthetic software demo

Generate a deterministic TEM-like 16-bit image:

```bash
python scripts/generate_synthetic_tem_demo.py \
  --output outputs/synthetic_tem_demo.png
```

Run the analyzer:

```bash
mca tem \
  --input outputs/synthetic_tem_demo.png \
  --output outputs/tem_demo \
  --sample-id synthetic_tem_demo \
  --nm-per-pixel 0.25 \
  --contrast-target bright \
  --min-area-pixels 20 \
  --imaging-mode bf_tem \
  --accelerating-voltage-kv 200
```

The supplied scale and acquisition settings in this demonstration are fabricated software-test metadata. The generated image is not experimental TEM data and is not evidence for any material.

## Scientific interpretation limits

A segmented bright or dark region can arise from multiple imaging and specimen effects. Equivalent diameter is a two-dimensional descriptor of the selected mask, not automatically a particle diameter. Comparisons require compatible imaging mode, scale calibration, specimen preparation, thickness, dose, focus, orientation, contrast mechanism, ROI selection, and segmentation settings.

Passing software tests demonstrates that files and calculations are generated as specified. It does not validate the physical meaning of the selected regions or establish representative sampling.
