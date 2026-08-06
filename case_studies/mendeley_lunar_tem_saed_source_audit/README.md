# Mendeley lunar TEM/HRTEM/SAED source audit

This case tracks seven public Mendeley Data deposits that explicitly identify
lunar-material TEM or TEM/EELS content:

- `fcwyz3kv3k`, version 1 — Chang'E-5 water-bearing minerals, including
  bright-field TEM, HRTEM and SAED;
- `w5jjhfp7v3`, version 1 — D+ implantation, including TEM/HRTEM/SAED;
- `p8kpdbrhrg`, version 2 — Chang'E-5/6 regolith evolution TEM;
- `ckpdp5wz7m`, version 1 — Chang'E-6 meteoroid-flux TEM plus gardening
  simulations;
- `xn73vjk95x`, version 1 — Chang'E-5/6 solar-wind irradiation TEM;
- `g9rgyv53xt`, version 4 — lunar alpha-Fe TEM/EELS plus micromagnetic
  simulations;
- `c44477pxc7`, version 2 — Chang'E-5 nanophase-iron TEM/EELS.

Only records whose public title or description explicitly identifies TEM are
included in this registry. Generic “source data” deposits are not promoted to TEM
candidates merely because the associated paper may have used microscopy.

## Verified public metadata

For every configured source, the bounded live audit requires the public landing
page to expose:

- the exact configured DOI and version;
- the expected title and TEM/TEM-EELS description terms;
- a Files section and Download All control;
- a `CC BY 4.0` licence.

This supports repository identity and reuse terms. It does not identify individual
file formats, acquisition IDs or calibration.

## Current API-access result

The official Digital Commons Data API documentation marks the dataset, snapshot,
versions, public files, public folders, ZIP metadata and file/ZIP redirect
operations as OAuth2-authorized. Anonymous GitHub-runner requests to these
endpoints are therefore audited as access evidence rather than treated as source
files.

The registry distinguishes mixed evidence explicitly:

- `ckpdp5wz7m` combines original TEM with gardening simulations;
- `g9rgyv53xt` combines experimental TEM/EELS with micromagnetic simulations;
- `fcwyz3kv3k` and `w5jjhfp7v3` combine TEM products with other measurement
  modalities.

Experimental measurements, simulations and other instruments must remain separated
by stable file and folder identifiers once authorized inventory access is available.

The audit records:

- public landing metadata: **Supported**;
- anonymous documented API access in the current runner: **Unsupported** when the
  endpoints return OAuth authorization responses;
- file UUIDs, byte counts, SHA-256 values and folder inventory: **Inconclusive**;
- DM3/DM4 versus TIFF/BMP representation: **Inconclusive**;
- calibrated-SAED, external-validation and engineering readiness: **false**.

No OAuth token, browser cookie, session replay or access-control bypass is used.
Landing HTML and API response bodies are not retained; only bounded status,
content type, length and SHA-256 evidence is published.

## Bounded workflow

The workflow:

1. downloads each public landing page under a 2 MB bound;
2. extracts visible text while excluding script/style content;
3. verifies title, DOI, version, source-specific TEM terms and licence;
4. probes seven documented API endpoints per dataset with no credentials and a
   maximum 64 KiB response sample;
5. records only trusted final host/path, status, content type, length and sample
   SHA-256;
6. runs the existing file-inventory and magic-header path only after authorized
   metadata access becomes available.

## Scientific boundary

All seven sources concern lunar materials and are not cobalt-oxide validation
cohorts. Repository wording such as “original data” does not prove detector-native
intensities, unmodified contrast, energy or reciprocal calibration, sample lineage
or acquisition independence. Until file UUID/hash/header evidence is obtained,
even native-format interoperability remains unconfirmed.

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
