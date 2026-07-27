# Validation Record

This case was introduced in software version `0.8.4` and must satisfy both the general package CI and the dedicated public-data workflow.

## Required software evidence

- complete repository test suite passes;
- wheel and source distribution build successfully;
- built wheel installs and reports `materials-characterization-analyzer 0.8.4`;
- no local raw/private/output paths are packaged;
- public Zenodo files download and match the published MD5 checksums;
- downloaded files and selected sources retain SHA-256 provenance.

## Required case evidence

- the selected XRD source contains 4,401 rows from 2.01° to 90.01° at a constant 0.02° step;
- XRD adaptation does not sort, interpolate, remove rows, or modify numeric values;
- XRD phase assignment and Scherrer estimation remain disabled because required acquisition metadata are absent;
- SEM scale review reproduces `0.0769230769 µm/pixel` from the embedded 10 µm scale bar;
- SEM quantitative segmentation remains blocked and produces no particle-size or area-fraction feature;
- all seven source EDS rows are preserved;
- atomic percent is explicitly marked as derived from source-reported weight percent;
- `21.49 wt% Ni` remains an unresolved nominal-composition conflict;
- identical physical aliquots across XRD, SEM, and EDS remain unconfirmed;
- final evidence classification remains `Diagnostic`.

Passing these checks validates the software and evidence package. It does not validate phase identity, quantitative particle size, nominal catalyst composition, catalytic mechanism, or engineering-release readiness.
