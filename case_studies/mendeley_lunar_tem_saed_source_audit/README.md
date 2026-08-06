# Mendeley lunar TEM/HRTEM/SAED source audit

This case audits two public Mendeley Data deposits that explicitly describe
original lunar-material TEM, HRTEM and selected-area electron diffraction data:

- `fcwyz3kv3k`, version 1 — Chang'E-5 lunar minerals;
- `w5jjhfp7v3`, version 1 — D+ implantation experiments on lunar materials.

## Objective

The immediate question is not whether the records mention TEM or SAED. It is
whether the deposited files are native microscopy containers such as DM3/DM4,
lossless raster exports such as TIFF/BMP, rendered figures, tables or documents.
That distinction matters for interoperability and detector-intensity claims.

## Bounded audit

The workflow:

1. fetches each official public dataset record and verifies the configured DOI,
   version, title, description terms and CC BY 4.0 licence;
2. requests the public file inventory and folder tree, preserving file UUID,
   folder identity, declared byte count, SHA-256 and content type when exposed;
3. reconstructs folder paths without joining by row order or inferred filenames;
4. classifies TEM/HRTEM/SAED, SEM/EDS and non-TEM measurement cues from stable
   paths while keeping the modalities separate;
5. selects at most 24 TEM/SAED-relevant files per dataset, prioritizing SAED and
   native microscopy containers;
6. downloads at most 64 KiB per selected file and classifies DM3, DM4, TIFF, BMP,
   PNG, JPEG, Office/ZIP or PDF magic without retaining the full file;
7. publishes metadata and header-hash evidence only.

The workflow does not retain source files or export pixel arrays. A server that
ignores the HTTP range request is still read only up to the configured header
limit before the connection is closed.

## Scientific boundary

The two sources are lunar-material datasets, not cobalt-oxide validation cohorts.
Repository wording such as “original data” does not prove detector-native
intensities, unmodified contrast, reciprocal calibration, sample lineage or
acquisition independence. Native DM3/DM4 presence supports file-format
interoperability only.

This case does not authorize image preprocessing, analyzer inference, annotation,
phase indexing, d-spacing validation, parameter tuning, model retraining,
external-validation claims or engineering decisions.

## Run

```bash
python -m scripts.audit_mendeley_lunar_tem_saed \
  --config case_studies/mendeley_lunar_tem_saed_source_audit/case_config.json \
  --output outputs/mendeley_lunar_tem_saed_source_audit
```

The output directory must be absent or empty.
