# Analysis Limitations

This project is a materials characterization support tool, not an automatic material identification system. The workflow organizes basic outputs and cautious summaries from XRD, SEM, and EDS inputs while the v0.2 contract adds provenance-aware manifests and long-format feature records.

The included demo files are synthetic/demo data. They are not real experimental measurements and should not be described as instrument output from an actual sample.

## XRD

- The XRD workflow detects peaks, estimates FWHM, and optionally calculates Scherrer crystallite size estimates when wavelength information is supplied.
- It does not use a reference database and does not assign phase labels.
- Detected peak positions are not enough to confirm a crystal phase. Phase interpretation requires suitable reference patterns, calibration awareness, sample context, and expert review.
- Peak detection can change with smoothing, prominence, noise, background shape, scan range, and instrument/sample conditions.
- Scherrer equation output is an approximate crystallite size estimate, not a particle size measurement. It is sensitive to peak broadening, instrumental broadening correction, strain, peak overlap, shape factor assumptions, and wavelength choice.
- When the wavelength unit is not recorded, long-format Scherrer features retain `unit=same_as_wavelength` and are flagged `unit_unresolved`; they are not silently presented as nanometres.

## SEM

- The SEM workflow uses simple thresholding and external contour detection.
- Thresholding results depend strongly on image quality, contrast, brightness, noise, threshold conditions, preprocessing choices, magnification, focus, sample preparation, and the supplied `microns-per-pixel` scale.
- The overlay shows regions selected by the thresholding workflow; it should not be treated as a validated segmentation mask without manual review.
- Area fraction and equivalent diameter values are estimates derived from detected image regions. They can change if the image crop, scale, threshold direction, or minimum-area setting changes.
- Long-format SEM features are flagged `review_required`.
- Manual review is required before using size or area fraction values in a formal technical report.

## EDS

- EDS is used here for elemental composition summaries.
- EDS alone does not determine crystal structure and does not confirm crystalline phases or chemical states.
- Quantification can be affected by light elements, peak overlap, surface roughness, accelerating voltage, detector settings, working distance, standards or standardless correction assumptions, and sample preparation.
- EDS composition can be local to the measured point or area. It may not represent the full sample unless the acquisition plan supports that interpretation.
- The current workflow does not process EDS maps, uncertainty estimates, background corrections, or multiple acquisition points.
- Long-format EDS composition features are flagged `review_required` because the current importer does not carry a complete acquisition and quantification metadata package.

## Provenance and Result Contracts

- SHA-256 identifies exact file bytes. It does not prove that a file belongs to the declared sample or that acquisition metadata are correct.
- A result manifest records only metadata and preprocessing known to the workflow. Missing source files or unknown preprocessing histories are reported as warnings rather than reconstructed.
- The feature contract standardizes storage; it does not establish comparability between different instruments, samples, preparation conditions, calibrations, or acquisition settings.
- A valid JSON manifest and passing software tests demonstrate software behavior only. They do not validate the scientific interpretation or experimental design.

## Integrated Interpretation

XRD, SEM, and EDS should be interpreted together with sample history, instrument settings, calibration information, and domain expertise.

SEM particle size and XRD crystallite size estimates can differ because they describe different physical length scales. EDS can support elemental composition review, but it should not be used by itself to decide crystal phases. XRD peak features can support structural review, but this project does not claim phase confirmation.
