# Public Real-Data Validation Cases

The case studies in this directory validate software integration, provenance, source adaptation, method suitability, and scientific-boundary handling on public datasets.

A successful case-study workflow does not automatically validate a scientific interpretation. Each case records its own comparability limits and evidence classification.

## DWCNT multimodal case

Path: [`public_carbon_multimodal/`](public_carbon_multimodal/)

- Public source: Recherche Data Gouv carbon-nanomaterial dataset
- Executed modalities: Raman, FTIR, XPS, and TGA
- TEM: source available, but quantitative segmentation blocked
- SAED and DSC: not provided and not substituted
- Evidence level: `Diagnostic`

The case emphasizes cross-technique provenance, explicit unavailable-modality handling, TEM method-suitability blocking, and case-level TGA boundary-artifact review.

## RWGS 5 wt% Cu/Al2O3 XRD–SEM–EDS case

Path: [`public_rwgs_xrd_sem_eds/`](public_rwgs_xrd_sem_eds/)

- Public source: Zenodo RWGS catalyst-characterization dataset
- XRD: executed with value-preserving ASC adaptation
- SEM: source and scale reviewed; quantitative segmentation blocked
- EDS: all source wt% rows preserved; atomic% explicitly derived
- Key quality conflict: source EDS reports 21.49 wt% Ni despite the nominal Cu/gamma-Al2O3 synthesis description
- Evidence level: `Diagnostic`

The case demonstrates why an integrated workflow must support partial execution and scientific gates rather than forcing every available file through an unsuitable analyzer.

## Shared rules

- Raw public source files are fetched at runtime rather than vendored.
- Published checksums and downloaded SHA-256 values are recorded when available.
- Identical physical aliquots are not inferred from matching sample names alone.
- Missing metadata are recorded, not invented.
- Preprocessing and source adaptation are explicit.
- Automatic candidates remain review-required and do not establish phases, compounds, chemical states, functional groups, mechanisms, or quantitative composition.
- Synthetic fixtures test software behavior only.
