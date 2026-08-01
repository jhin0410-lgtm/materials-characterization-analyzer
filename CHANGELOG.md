# Changelog

All notable user-facing changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses semantic versioning for public package versions.

## [Unreleased]

### Fixed

- Dryad HRTEM pilot automatic acquisition now resolves the pinned file-linked source version and checksum inventory, authenticates binary downloads without exposing the token, preserves raw API responses separately from enriched evidence, and keeps readiness blocked unless processed metadata binding is exact and authoritative.
- The public Dryad pilot contract now pins the HDF5, training, overlap, notebook, source-version, and endpoint configuration; workflow evidence distinguishes a configured credential from a successfully verified authenticated download.
- TEM external-validation intake now keeps model inference blocked whenever any dataset or image gate fails, even if annotations and protocol fields are otherwise complete.
- Canonical manifest SHA-256 binding now detects post-freeze cohort or protocol mutation, and duplicate JSON object keys fail closed.
- Duplicate active-image detection ignores excluded archival copies, excluded-image annotations do not change active-cohort status, every active annotation must remain blinded and unused for model development, and annotation file paths must be unique.

## [0.10.0] - 2026-08-01

### Added

- A checksum-bound Mendeley CoP/Co2P/Co3O4 TEM source audit using the anonymous public API used by the landing page, including immutable file inventory, duplicate-record detection, safe RAR inventory, and selective microscopy-member inspection.
- A fail-closed `mca tem-validation-intake` command for future independent cobalt-oxide TEM datasets, with SHA-256, sample/acquisition lineage, non-use, blinded-label, content-overlap, and evaluation-freeze gates.
- A public Zr15Nb DSC real-data case using Zenodo record `17590045`, with exact three-row header binding, `mW/mg` to `W/g` identity conversion, 43,167-row monotonic heating validation, three predeclared smoothing runs, and candidate robustness review.
- A public FINDS SAED diagnostic case using Zenodo record `13748483`, with project-bound center and camera constant, decoded-pixel-equal JPEG-to-PNG adaptation, seven center/smoothing runs, and post-detection source d-value comparison.
- Dedicated real-data workflows, focused regression suites, deterministic evidence verifiers, checksum-bound manifests, and case-level scientific closeouts for the DSC and SAED cases.

### Changed

- The TEM external-validation registry now excludes the assessed Mendeley source as a rendered mixed-heterojunction figure representation instead of leaving it as a metadata-resolution candidate.
- The next TEM action now targets acquisition of independent raw cobalt-oxide TEM data rather than additional inspection of the rejected Mendeley source.
- SAED ZIP auditing distinguishes platform resource-fork metadata from measurement images and requires valid image references before accepting FINDS project files.

### Scientific status

- The Mendeley TEM source is **Diagnostic** and not suitable for independent segmentation validation: the inspected files are rendered RGB TIFF/BMP publication figures without immutable sample/acquisition IDs, Co3O4-region binding, detector-intensity provenance, or independent labels.
- The Zr15Nb DSC case is **Diagnostic**: five automatic event candidates persist across the three smoothing spans, but phase, reaction, mechanism, validated onset, quantitative enthalpy, and engineering claims remain unsupported.
- The FINDS SAED case is **Diagnostic**: four calibrated ring candidates persist across all seven runs, but the source is a lossy JPEG without material, acquisition, detector, raw-intensity, or crystallographic ground-truth provenance.
- Synthetic intake fixtures validate software behavior only and are not scientific evidence.

## [0.9.3] - 2026-07-29

### Added

- A pinned Dryad HRTEM pilot-pair contract for file IDs `2451485`, `2451482`, and `2451515` from dataset `10.7941/D1SP93`.
- Live resolution of the files' directly linked Dryad source version and paginated file inventory instead of rebinding them to the DOI's later metadata version.
- Source-declared SHA-256 validation, downloaded byte-size and hash verification, HDF5 image-label pairing checks, exact label-value inspection, patch provenance tables, and cobalt-training content-overlap screening.
- A credential-aware GitHub Actions workflow that records `blocked_missing_dryad_api_token` when authenticated file acquisition is unavailable and cannot be mistaken for a completed real-data audit.
- Separate provenance/I/O and scientific comparison modules while preserving the existing audit callable and CLI path.
- Regression coverage for MD5 and SHA-256 metadata, exact-overlap blocking, nonbinary-label rejection, checksum mismatch, overwrite refusal, and parent-image standardization before patching.

### Changed

- Dryad source standardization is represented correctly: the source reports standardizing each `4096 x 4096` parent image before `512 x 512` patching, so individual patch mean and standard deviation are diagnostic rather than required to equal zero and one.
- Per-patch standardization is applied only to content-identity comparison and is explicitly recorded as such.

### Scientific status

- Current live metadata and source-version evidence are verified, but the real Dryad HDF5 and cross-dataset content-overlap audits remain **Inconclusive** until repository secret `DRYAD_API_TOKEN` permits authenticated acquisition.
- The pilot material is Au rather than cobalt oxide, the labels were produced by one human, one creator overlaps with the cobalt-oxide source, and authoritative cross-dataset acquisition independence is unavailable.
- Even after authenticated audit, this case can support only a diagnostic cross-material stress-test protocol, not in-domain cobalt-oxide external-validation performance.
- No model training, inference, segmentation metric, label remapping, physical conversion, causal, optimization, or engineering-release claim is supported.

## [0.9.2] - 2026-07-28

### Added

- A checksum-bound audit comparing all fifty public cobalt-oxide TEM source frames with four reconstructed training-parent candidates.
- Exact aligned-tile identity testing using the pinned `8 x 8` tiling and per-tile standardization path, plus block-signature NCC diagnostics for review-required near matches.
- Frame-level and pairwise evidence tables, a scientific-readiness summary, a Markdown report, and a checksum-bound artifact manifest.
- A focused 64-tile pixel- and block-level similarity review for the single unresolved `co0_7:frame-0` versus reconstructed candidate-parent-3 pair.
- A dedicated real-data GitHub Actions workflow and focused fail-closed regression tests.

### Scientific status

- The audit is `Diagnostic`: the four training parents remain reconstructed candidates because authoritative patch-to-parent metadata are absent.
- The broad audit found zero exact content-equivalent overlaps, forty-nine no-overlap-detected frames, and one review-required frame under the aligned 64-tile fingerprint rule.
- The focused review found strong full-image correspondence for `co0_7:frame-0` versus reconstructed candidate parent 3: global pixel NCC `0.9990847724679279`, median tile NCC `0.9996866574918363`, minimum tile NCC `0.9941011260031625`, all 64 tiles at least `0.99`, and zero exact quantized tile hashes.
- `co0_7:frame-0` is conservatively excluded from the external-candidate pool as leakage control, but authoritative parent or acquisition identity is not confirmed.
- The other forty-nine frames remain image-only candidates, not external validation samples, because authoritative parent-disjoint provenance and independent labels are absent.
- No independent segmentation-performance, parent-disjoint generalization, physical-size, causal, optimization, or engineering-release claim is supported.

## [0.9.1] - 2026-07-28

### Added

- A checksum-bound pairing audit for the ten public cobalt-oxide TEM source-image HDF5 members and their ten source-predicted mask members.
- Fifty same-index frame-pair records with per-member and per-frame SHA-256 fingerprints, exact dataset/shape/dtype validation, and one-pair-at-a-time extraction.
- Explicit detection that all selected `/images` frames are already numerically standardized to approximately zero mean and unit standard deviation.
- Fail-closed checks for archive drift, unsafe ZIP entries, HDF5 schema or attribute drift, shape mismatch, nonfinite image arrays, nonbinary masks, standardization drift, and output overwrite.

### Scientific status

- Pairing is classified `source_asserted_structurally_consistent_not_independently_verified`: the Zenodo description, exact member prefixes, equal array shapes, equal frame counts, and same-index inventory agree, but no immutable source mapping manifest is embedded.
- The selected `/images` arrays are standardized representations and do not preserve original detector-intensity units.
- The publication's 86 pm context is not bound to individual public HDF5 members and is not used for physical conversion.
- No segmentation accuracy, nanometre-scale size, filename-derived synthesis condition, particle identity, phase, mechanism, causal, predictive, optimization, or engineering-release claim is supported.
- Synthetic fixtures are used only for software validation and do not contribute to real-data evidence.

## [0.9.0] - 2026-07-28

### Added

- A pinned public cobalt-oxide TEM case using source-predicted segmentation masks derived from real HRTEM images in Zenodo record `14927582`.
- Strict HDF5 import for ten source files and fifty `4096 x 4096` masks, including full finite/binary-value validation and one-file-at-a-time extraction.
- Pixel-domain foreground and unfiltered 8-connected-component descriptors with complete source-file SHA-256 and preprocessing provenance.
- Safe ZIP validation, exact MD5/SHA-256 archive binding, deterministic case outputs, and checksum-bound artifact manifests.
- Runtime HDF5 support through `h5py`.

### Scientific status

- The case is `Diagnostic` and treats the HDF5 arrays as source-predicted masks, not independent ground truth or predictions generated by this repository.
- The selected archive does not embed paired raw-image identity, pixel calibration, independent labels, or verified synthesis-condition mapping.
- No nanometre-scale dimensions, segmentation accuracy, particle identity, phase, mechanism, synthesis-response, causal, predictive, optimization, or engineering-release claim is supported.
- Synthetic HDF5 files are used only for software tests and are not scientific evidence.

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
