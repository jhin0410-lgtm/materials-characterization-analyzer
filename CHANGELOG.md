# Changelog

All notable user-facing changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses semantic versioning for public package versions.

## [Unreleased]

No unreleased changes are currently recorded.

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

Earlier iterations established the XRD/SEM/EDS baseline, the provenance-aware result contract, and standalone Raman, TEM, SAED, XPS, and FTIR workflows. Git history remains the authoritative detailed record for those changes.
