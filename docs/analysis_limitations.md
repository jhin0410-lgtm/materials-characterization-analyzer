# Analysis Limitations

This project is a materials characterization support tool, not an automatic material identification system. The `v0.1` workflow is designed to organize basic outputs and make cautious summaries from XRD, SEM, and EDS inputs.

The included demo files are synthetic/demo data. They are not real experimental measurements and should not be described as instrument output from an actual sample.

## XRD

- The `v0.1` XRD workflow detects peaks, estimates FWHM, and optionally calculates Scherrer crystallite size estimates when wavelength information is supplied.
- It does not use a reference database and does not assign phase labels.
- Detected peak positions are not enough to confirm a crystal phase. Phase interpretation requires suitable reference patterns, calibration awareness, sample context, and expert review.
- Peak detection can change with smoothing, prominence, noise, background shape, scan range, and instrument/sample conditions.
- Scherrer equation output is an approximate crystallite size estimate, not a particle size measurement. It is sensitive to peak broadening, instrumental broadening correction, strain, peak overlap, shape factor assumptions, and wavelength choice.

## SEM

- The `v0.1` SEM workflow uses simple thresholding and external contour detection.
- Thresholding results depend strongly on image quality, contrast, brightness, noise, threshold conditions, preprocessing choices, magnification, focus, sample preparation, and the supplied `microns-per-pixel` scale.
- The overlay shows regions selected by the thresholding workflow; it should not be treated as a validated segmentation mask without manual review.
- Area fraction and equivalent diameter values are estimates derived from detected image regions. They can change if the image crop, scale, threshold direction, or minimum-area setting changes.
- Manual review is required before using size or area fraction values in a formal technical report.

## EDS

- EDS is used here for elemental composition summaries.
- EDS alone does not determine crystal structure and does not confirm crystalline phases.
- Quantification can be affected by light elements, peak overlap, surface roughness, accelerating voltage, detector settings, working distance, standards or standardless correction assumptions, and sample preparation.
- EDS composition can be local to the measured point or area. It may not represent the full sample unless the acquisition plan supports that interpretation.
- The current workflow does not process EDS maps, uncertainty estimates, background corrections, or multiple acquisition points.

## Integrated Interpretation

XRD, SEM, and EDS should be interpreted together with sample history, instrument settings, calibration information, and domain expertise.

SEM particle size and XRD crystallite size estimates can differ because they describe different physical length scales. EDS can support elemental composition review, but it should not be used by itself to decide crystal phases. XRD peak features can support structural review, but this project does not claim phase confirmation.

