# Demo Data Notice

The files in this folder are demo/synthetic inputs for exercising the `materials-characterization-analyzer` workflow. They are not real XRD, SEM, or EDS instrument exports, and they should not be described as measurements from an actual material.

## Files

- `synthetic_xrd.csv`: artificial XRD-like two-column intensity data with generated peaks.
- `synthetic_sem.png`: generated image data with bright regions on a dark background for thresholding demonstrations.
- `synthetic_eds.csv`: synthetic elemental composition table for EDS summary and plotting tests.

These files are used by README demo commands and automated tests.

## Real Data Guidance

Only include real instrument data in a public repository when the dataset is public, properly anonymized, and appropriate for GitHub.

Do not commit private experimental data, unpublished research data, institution-owned confidential data, customer/company data, or other sensitive instrument files.

Future real-data case studies should be documented separately, for example under `docs/case_studies/`, with the dataset source, commands used, generated outputs, engineering interpretation, and limitations clearly stated.
