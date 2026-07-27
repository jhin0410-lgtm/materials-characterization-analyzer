# Analysis Limitations

This project is a materials characterization support tool, not an automatic material identification system. The workflow organizes cautious XRD, SEM, EDS, Raman, TEM, SAED, XPS, and FTIR outputs while the result contract records provenance, preprocessing, warnings, and long-format features.

The included demo files and generated demo images or spectra are synthetic data. They are not real experimental measurements and should not be described as instrument output from an actual sample.

## XRD

- The XRD workflow detects peaks, estimates FWHM, and optionally calculates Scherrer crystallite size estimates when wavelength information is supplied.
- It does not use a reference database and does not assign phase labels.
- Detected peak positions are not enough to confirm a crystal phase.
- Peak detection depends on smoothing, prominence, noise, background, scan range, calibration, and acquisition conditions.
- Scherrer output is an approximate crystallite-size estimate, not particle size.
- When wavelength units are unresolved, exported Scherrer features retain unresolved units rather than being relabelled as nanometres.

## SEM

- The SEM workflow uses simple thresholding and external contour detection.
- Thresholding depends on image quality, contrast, noise, magnification, focus, preparation, scale, crop, and segmentation settings.
- The overlay is not a validated segmentation mask without manual review.
- Area fraction and equivalent diameter are threshold-derived descriptors.
- Long-format SEM features are flagged `review_required`.

## EDS

- EDS is used for elemental-composition summaries.
- EDS alone does not determine crystal structure, crystalline phase, bonding, or chemical state.
- Quantification depends on peak overlap, light elements, geometry, standards, corrections, voltage, detector settings, roughness, and preparation.
- A measured point or area may not represent the full sample.
- The current workflow does not process maps, uncertainty, background corrections, or multiple acquisitions.
- Long-format EDS features are flagged `review_required`.

## Raman

- The Raman workflow performs two-column import, optional asymmetric least-squares baseline correction, optional Savitzky–Golay smoothing, candidate detection, descriptive FWHM, and within-FWHM integration.
- Candidates do not identify compounds, phases, bonds, or vibrational modes.
- Baseline and smoothing can materially change height, position, width, area, and detectability.
- FWHM is descriptive and is not a fitted Gaussian, Lorentzian, Voigt, or asymmetric line-shape parameter.
- Area is limited to the FWHM interval and is not a deconvoluted full-peak area.
- Fluorescence, cosmic rays, saturation, overlap, calibration, polarization, laser heating, and acquisition settings require review.
- Long-format Raman features are flagged `review_required`.

## TEM

- The TEM workflow segments explicitly selected bright or dark contrast with Otsu thresholding and external contours.
- A detected region is not automatically a particle, pore, phase, defect, grain, precipitate, or lattice feature.
- Contrast depends on imaging mode, thickness, diffraction condition, focus, orientation, dose, drift, contamination, and preparation.
- `nm_per_pixel` is user supplied and is not inferred from scale bars, filenames, magnification labels, or embedded metadata.
- Equivalent diameter is a two-dimensional mask descriptor, not a validated particle-size distribution.
- ROI, blur, contrast direction, minimum area, and border exclusion can materially change outputs.
- Display normalization does not replace preserved 8/16-bit measurement data.
- Long-format TEM features are flagged `review_required`.

## SAED

- The SAED workflow calculates complete-annulus radial mean intensity around a selected center and detects descriptive radial candidates.
- A radial candidate is not an indexed reflection, phase, zone axis, structure, or validated diffraction ring.
- Image midpoint fallback is warned and is not automatic transmitted-beam center estimation.
- Radial averaging can hide spots, arcs, texture, ellipticity, astigmatism, distortion, beam-stop effects, and incomplete rings.
- Candidate radius and width depend on center, masking, smoothing, prominence, binning, saturation, and preprocessing.
- Without explicit reciprocal calibration, only pixel radius is exported.
- Calibrated outputs use `g = 1/d`, not `q = 2*pi/d`.
- A single reference ring does not validate detector linearity, distortion, center, or calibration transfer.
- Long-format SAED features are flagged `review_required`.

## XPS

- The XPS workflow imports a monotonic two-column binding-energy spectrum and records the original axis direction.
- No energy reference is inferred. A shift is applied only from explicit user input.
- The workflow does not assume adventitious carbon, a fixed C 1s value, a Fermi edge, or an internal standard.
- Charging and differential charging can invalidate a rigid energy shift.
- Shirley and linear backgrounds depend on endpoints and spectrum range.
- Candidates do not identify elements, orbitals, compounds, chemical states, oxidation states, satellites, multiplets, or spin-orbit components.
- FWHM is descriptive and is not a fitted line-shape parameter.
- Area within FWHM is not a full fitted component area, sensitivity-factor-corrected intensity, or atomic concentration.
- Acquisition settings, analyzer transmission, sputtering, contamination, and radiation damage require review.
- Long-format XPS features are flagged `review_required`.

## FTIR

- The FTIR workflow imports a monotonic two-column wavenumber spectrum and requires explicit signal semantics.
- Absorbance is preserved directly. Transmittance fraction is converted with `A = -log10(T)` and transmittance percent with `A = -log10(%T/100)`.
- Transmittance values less than or equal to zero are rejected. Values above the nominal physical range are preserved and warned rather than clipped.
- Header text is not used to infer whether the signal is absorbance or transmittance.
- The workflow does not infer or apply wavenumber calibration.
- Linear and asymmetric least-squares baselines are preprocessing choices and are not physical component models.
- Candidates do not identify functional groups, compounds, phases, bonds, polymers, oxides, carbonates, phosphates, or other material classes.
- FWHM and area are descriptive and are not fitted, deconvoluted, path-length-corrected, or quantitative concentration outputs.
- ATR, transmission, diffuse-reflectance, and specular-reflectance spectra are not directly interchangeable.
- Water vapor, carbon dioxide, detector response, apodization, resolution, purge, thickness, contact, path length, scattering, and preparation require review.
- The workflow does not apply atmospheric correction, ATR correction, normalization, derivatives, spectral subtraction, library matching, or quantitative concentration analysis.
- Long-format FTIR features are flagged `review_required`.

## Provenance and Result Contracts

- SHA-256 identifies exact file bytes. It does not prove sample identity or metadata correctness.
- A manifest records only known metadata and preprocessing. Missing information is warned rather than reconstructed.
- The feature contract standardizes storage but does not establish comparability across instruments, samples, preparation, calibration, or acquisition settings.
- A valid manifest and passing tests demonstrate software behavior only, not scientific validity.

## Integrated Interpretation

XRD, SEM, EDS, Raman, TEM, SAED, XPS, and FTIR should be interpreted with sample identity, composition, processing history, instrument settings, calibration, acquisition conditions, preprocessing, sampling design, references, and domain expertise.

SEM region size, TEM contrast-region size, and XRD crystallite-size estimates describe different measurement processes and are not interchangeable. EDS does not decide crystalline phase or chemical state. Raman and FTIR candidates do not identify materials without suitable references and validated acquisition context. TEM and SAED require validated contrast, center, scale, and diffraction interpretation. XPS requires independently justified energy reference, background, acquisition, fitting, and chemical-state assumptions.
