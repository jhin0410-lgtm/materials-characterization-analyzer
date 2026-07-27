# Changelog

All notable user-facing changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses semantic versioning for public package versions.

## [Unreleased]

No unreleased changes are currently recorded.

## [0.8.6] - 2026-07-27

### Added

- A NIST AM-Bench 2018-02 optical-metrology producer bundle containing ten explicit AMMT trace IDs and forty source-reported melt-pool width/depth feature records.
- A checksum-bound schema `1.0` handoff package that keeps optical characterization evidence in this repository while leaving process conditions to `materials-data-analyzer`.

### Fixed

- Four-material case sample IDs are now path-safe and constrained to the exact DWCNT, MWCNT, FLG, and GNP identity contract before any network or filesystem work.
- Supplied Dataverse checksums now fail closed when the algorithm is unsupported, incomplete, or mismatched; invalid sources are not written to disk.
- The configured Dataverse dataset version is verified against returned metadata before source selection.
- Per-sample reports and TEM limitations are generated from each material's resolved configuration instead of reusing DWCNT-specific scientific language.
- The dedicated real-data workflow now runs when any exercised Raman, FTIR, XPS, thermal, provenance, feature, contract, or handoff module changes.

### Scientific status

- The four-material case remains `Diagnostic` and compares distinct material classes, not controlled process levels.
- The NIST optical-metrology bundle preserves source-reported table values and does not independently remeasure raw microscopy images or include process variables.
- No phase, chemical-state, functional-group, mechanism, causal process-response, prediction, optimization, or engineering-release claim is supported by either case.

## [0.8.5] - 2026-07-27

### Added

- A checksum-bound schema `1.0` handoff exporter for the public RWGS XRD/SEM/EDS diagnostic case.
- An isolated `handoff_bundle/` output that preserves the existing case-level feature artifact while packaging XRD and EDS features, sample context, and copied evidence references for `materials-data-analyzer`.
- Regression coverage for explicit `sample_id` identity, source/preprocessing provenance, SEM method-mismatch preservation, unresolved Ni context, scientific claim boundaries, and overwrite refusal.
- Public workflow execution of the RWGS producer case and handoff export.

### Scientific status

- The exported bundle remains `Diagnostic` and contains no SEM numeric feature rows because quantitative segmentation is blocked.
- The bundle does not establish identical physical aliquots, nominal composition, phase identity, particle size, process-response relationships, catalyst mechanism, or engineering-release readiness.

## [0.8.4] - 2026-07-27

### Added

- A provenance-first public XRD/SEM/EDS diagnostic case using the Zenodo RWGS catalyst-characterization dataset.
- Runtime verification of published MD5 checksums, downloaded SHA-256 provenance, safe ZIP extraction, and synthesis-protocol DOCX text extraction.
- A value-preserving adapter for the selected 4,401-row `5%Cu/Al2O3` XRD source pattern.
- Standard-library extraction of source-reported EDS weight percent from XLSX, with all seven source rows preserved and atomic percent explicitly derived from configured atomic weights.
- A SEM suitability record with embedded-footer metadata, reviewed scale calibration, qualitative crop, and an explicit quantitative-segmentation block.
- Cross-technique comparability, long-format feature, manifest, validation-report, and case-summary outputs for the selected nominal sample label.

### Scientific status

- The case is classified as `Diagnostic`.
- XRD peak candidates are not phase assignments, and Scherrer estimates are not generated because radiation and instrumental-broadening metadata are absent.
- SEM particle-size and area-fraction results are blocked because ESB compositional contrast is not a validated particle-boundary signal for the existing Otsu method.
- The source EDS table reports `21.49 wt% Ni`, which conflicts with the nominal Cu/gamma-Al2O3 synthesis description; nominal composition is therefore not confirmed.
- The same nominal sample label is documented, but identical physical aliquots across XRD, SEM, and EDS are not confirmed.

## [0.8.3] - 2026-07-27

### Added

- Machine-readable software citation metadata in `CITATION.cff`.
- A release checklist for version, provenance, build, test, artifact, and scientific-boundary review.
- `mca --version` and `mca -V` command-line output.
- Automated version-consistency checks across package metadata, runtime metadata, citation metadata, and this changelog.
- CI construction of both wheel and source distributions with a wheel smoke test.

### Changed

- Development dependencies now include the standard Python `build` frontend.

## [0.8.2] - 2026-07-27

### Added

- BSD 3-Clause license, security policy, contribution guide, Dependabot configuration, and issue/pull-request templates.
- Expanded public-repository protection for credentials, local/private data, generated artifacts, caches, and development files.
- Read-only GitHub Actions permissions and workflow concurrency controls.

### Changed

- `pyproject.toml` became the single dependency source; the duplicate `requirements.txt` was removed.
- Public DWCNT and general CI workflows were repaired and validated with 128 passing tests.

## [0.8.1] - 2026-07-27

### Added

- A provenance-first public DWCNT case using Recherche Data Gouv source files.
- Cross-technique comparability classification for Raman, FTIR, XPS, TGA, TEM, SAED, and DSC availability.
- Explicit TEM method-suitability blocking and separate TGA startup-boundary candidate review.

### Scientific status

- The public case remains `Diagnostic`, not a confirmed material, phase, chemical-state, functional-group, reaction, or mechanism determination.

## [0.8.0] - 2026-07-27

### Added

- Provenance-aware TGA and DSC baseline workflows with explicit signal semantics, metadata, candidates, features, manifests, and scientific limitations.

## Earlier development

Earlier iterations established the XRD/SEM/EDS baseline, the provenance-aware result contract, and standalone Raman, TEM, SAED, XPS, FTIR, and thermal workflows. Git history remains the authoritative detailed record for those changes.
