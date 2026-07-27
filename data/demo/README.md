# Demo Data Notice

The files in this folder are demo/synthetic inputs for exercising the `materials-characterization-analyzer` workflow. They are not real XRD, SEM, EDS, or Raman instrument exports, and they should not be described as measurements from an actual material.

## Files

- `synthetic_xrd.csv`: artificial XRD-like two-column intensity data with generated peaks.
- `synthetic_sem.png`: generated image data with bright regions on a dark background for thresholding demonstrations.
- `synthetic_eds.csv`: synthetic elemental composition table for EDS summary and plotting tests.
- `synthetic_raman.csv`: synthetic Raman-like spectrum with a curved background and three generated peaks. It is designed only to exercise baseline correction, peak detection, FWHM, and output generation.

These files are used by documentation examples and automated tests. Peak locations or shapes in synthetic files are not evidence for any compound, phase, bond, or material.

## Real Data Guidance

Only include real instrument data in a public repository when the dataset is public, properly anonymized, and appropriate for GitHub.

Do not commit private experimental data, unpublished research data, institution-owned confidential data, customer/company data, or other sensitive instrument files.

Future real-data case studies should be documented separately, for example under `docs/case_studies/`, with the dataset source, license, sample context, acquisition metadata, commands used, generated outputs, engineering interpretation, and limitations clearly stated.
