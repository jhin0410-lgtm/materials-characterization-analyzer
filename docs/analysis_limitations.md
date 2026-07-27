# Analysis Limitations

This project is a materials characterization support tool, not an automatic material identification system. The workflow organizes cautious XRD, SEM, EDS, Raman, and TEM outputs while the result contract records provenance, preprocessing, warnings, and long-format features.

The included demo files and generated demo images are synthetic data. They are not real experimental measurements and should not be described as instrument output from an actual sample.

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

## Raman

- The Raman workflow performs two-column import, optional asymmetric least-squares baseline correction, optional Savitzky-Golay smoothing, automatic peak detection, descriptive FWHM calculation, and within-FWHM integration.
- Automatically detected peaks do not identify a compound, phase, bond, or vibrational mode. No band assignment is generated.
- Baseline and smoothing parameters can materially change peak height, position, width, area, and detectability. Raw, baseline, corrected, and processed signals are therefore saved together.
- The reported FWHM is calculated from the processed signal and is not a fitted Gaussian, Lorentzian, Voigt, or asymmetric line-shape parameter.
- The reported area is limited to the FWHM interval and is not a deconvoluted full-peak area.
- Fluorescence, cosmic rays, detector saturation, peak overlap, calibration, polarization, focus, laser heating, acquisition time, laser power, and spectral resolution can affect the result.
- Missing recommended acquisition metadata are recorded as warnings rather than inferred.
- Long-format Raman features are flagged `review_required`.

## TEM

- The TEM workflow segments explicitly selected bright or dark contrast with Otsu thresholding and external contours.
- A detected contrast region is not automatically a particle, pore, phase, defect, grain, precipitate, or lattice feature.
- TEM contrast depends on imaging mode, specimen thickness, diffraction condition, focus and defocus, orientation, detector geometry, dose, drift, contamination, sample preparation, and post-processing.
- The `nm_per_pixel` scale is supplied by the user. The workflow does not infer or verify calibration from a scale bar, filename, magnification label, or embedded metadata.
- Equivalent diameter is a two-dimensional mask descriptor. It is not a validated particle-size distribution without representative fields of view, sampling design, scale validation, segmentation validation, and expert review.
- Optional ROI cropping, blur, contrast direction, minimum-area filtering, and border exclusion can materially change the outputs and are recorded in preprocessing history.
- Display overlays may be normalized to 8-bit for visualization, but segmentation and raw-intensity measurements use the preserved 8-bit or 16-bit grayscale data.
- The workflow does not perform SAED indexing, calibrated diffraction spacing, HRTEM lattice-fringe measurement, FFT interpretation, or phase assignment.
- Long-format TEM features are flagged `review_required`.

## Provenance and Result Contracts

- SHA-256 identifies exact file bytes. It does not prove that a file belongs to the declared sample or that acquisition metadata are correct.
- A result manifest records only metadata and preprocessing known to the workflow. Missing source files or unknown preprocessing histories are reported as warnings rather than reconstructed.
- The feature contract standardizes storage; it does not establish comparability between different instruments, samples, preparation conditions, calibrations, or acquisition settings.
- A valid JSON manifest and passing software tests demonstrate software behavior only. They do not validate the scientific interpretation or experimental design.

## Integrated Interpretation

XRD, SEM, EDS, Raman, and TEM should be interpreted together with sample identity, composition, processing history, instrument settings, calibration information, acquisition conditions, preprocessing choices, sampling design, and domain expertise.

SEM region size, TEM contrast-region size, and XRD crystallite-size estimates describe different measurement processes and cannot be treated as interchangeable. EDS supports elemental composition review but does not decide crystalline phases or chemical states. Raman peaks support spectral comparison but do not identify a material without appropriate references and validated measurement context. TEM contrast can support morphology or microstructure review only after the imaging mode and contrast mechanism are scientifically justified.
