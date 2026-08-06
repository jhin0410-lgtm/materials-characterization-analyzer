# Mendeley lunar TEM/HRTEM/SAED source audit

This case audits two public Mendeley Data deposits that explicitly describe
original lunar-material TEM, HRTEM and selected-area electron diffraction data:

- `fcwyz3kv3k`, version 1 — Chang'E-5 lunar minerals;
- `w5jjhfp7v3`, version 1 — D+ implantation experiments on lunar materials.

## Verified public metadata

Both public landing pages expose:

- the configured title, DOI and version;
- TEM bright-field, high-resolution and SAED description terms;
- a Files section and Download All control;
- a `CC BY 4.0` licence.

This supports the repository record and reuse terms. It does not identify the
individual deposited file formats.

## Current API-access result

The current official Digital Commons Data API documentation marks the dataset,
snapshot, versions, public files, public folders, ZIP metadata and file/ZIP
redirect endpoints as OAuth2-authorized operations. Anonymous GitHub-runner
requests to the documented endpoints return authorization responses.

The audit therefore records:

- public landing metadata: **Supported**;
- anonymous documented API access in the current runner: **Unsupported**;
- file UUIDs, byte counts, SHA-256 values and folder inventory: **Inconclusive**;
- DM3/DM4 versus TIFF/BMP representation: **Inconclusive**;
- calibrated-SAED and external-validation readiness: **false**.

No OAuth token, browser cookie, session replay or access-control bypass is used.
Response bodies are not retained; only bounded status, content type, length and
SHA-256 evidence is published.

## Bounded workflow

The workflow:

1. downloads each public landing page under a 2 MB bound;
2. extracts visible text while excluding script/style content;
3. verifies title, DOI, version, TEM/HRTEM/SAED terms and licence;
4. probes seven documented API endpoints per dataset with no credentials and a
   maximum 64 KiB response sample;
5. records only trusted final host/path, status, content type, length and sample
   SHA-256;
6. runs the existing file-inventory and magic-header path only after authorized
   metadata access becomes available.

## Scientific boundary

The two sources are lunar-material datasets, not cobalt-oxide validation cohorts.
Repository wording such as “original data” does not prove detector-native
intensities, unmodified contrast, reciprocal calibration, sample lineage or
acquisition independence. Until file UUID/hash/header evidence is obtained, even
native-format interoperability remains unconfirmed.

This case does not authorize image preprocessing, analyzer inference, annotation,
phase indexing, d-spacing validation, parameter tuning, model retraining,
external-validation claims or engineering decisions.

## Run

```bash
python -m scripts.run_mendeley_lunar_tem_saed_audit \
  --config case_studies/mendeley_lunar_tem_saed_source_audit/case_config.json \
  --output outputs/mendeley_lunar_tem_saed_source_audit
```

The output directory must be absent or empty.
