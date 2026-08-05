# TEM and SAED Open-Data Validation Roadmap

Status date: **2026-08-05**

## Decision

Open TEM and SAED data do exist. The limiting factor is not repository prestige by itself. The limiting factor is whether a record preserves enough task-matched evidence to support an independent scientific claim.

A DOI, institutional repository, checksum, and reuse licence can establish source identity and legal reuse. They do not by themselves establish:

- native raw-detector status;
- immutable sample and acquisition identity;
- independence from model development;
- TEM segmentation ground truth;
- static SAED acquisition and pattern identity;
- pattern centre and reciprocal calibration;
- comparability to the target material and instrument domain;
- enough independent samples or acquisitions for generalization claims.

The repository therefore distinguishes four levels:

1. **Public source:** files can be located and reused.
2. **Metadata-audited source:** record identity, licence, file inventory, and archive checksum are pinned.
3. **Bounded source-audited source:** the source archive and member identities are verified under a frozen, fail-closed procedure.
4. **External-validation-ready source:** every task-specific scientific gate is satisfied before analyzer execution.

Two public sources have now reached level 3. None has reached level 4.

## Current state

- Software baseline: `v0.11.0`.
- TEM software validation: **Supported** for implemented behavior and fail-closed intake.
- SAED software validation: **Supported** for implemented behavior and fail-closed intake.
- RepOD CoFeNi source identity and archive integrity: **Supported**.
- Zenodo silver source identity, archive integrity, and member hashing: **Supported**.
- TEM independent in-domain external validation: **Inconclusive**.
- SAED calibrated external validation: **Inconclusive**.
- External-validation-ready analyzers: **0**.
- Engineering-decision-ready analyzers: **0**.

No analyzer algorithm, segmentation weight, SAED primary parameter, output schema, or scientific evidence threshold was changed during source acquisition.

## Completed bounded audit 1 — RepOD CoFeNi TEM/HRTEM/SAED

Record: `10.18150/SIOWH6`

Verified on 2026-08-05:

- RepOD version 1.0 and 12-file record inventory;
- file-level CC BY 4.0 licence;
- three target files with repository MD5 and computed SHA-256;
- two valid ZIP archives and one standalone TIFF;
- seven decodable TIFF members;
- three SAED-named members, one HRTEM member, two BF/DF members, and one HAADF-STEM image;
- no source archive or image retained in evidence.

Scientific limitations:

- TIFF raster exports rather than native detector containers;
- basic raster metadata only;
- sample/acquisition identity and independence unresolved;
- independent TEM segmentation labels absent;
- member-level static-SAED acquisition, centre, reciprocal calibration, and reference assignments unresolved;
- CoFeNi is outside the current cobalt-oxide target domain.

Closeout:

- source identity and archive integrity: **Supported**;
- analyzer scientific evidence: **Inconclusive**;
- intake: `accepted_for_bounded_diagnostic_only`;
- external-validation ready: false;
- engineering-decision ready: false.

Verified snapshot:

`case_studies/repod_cofeni_tem_saed_source_audit/verified_snapshot.json`

## Completed bounded audit 2 — Zenodo silver TEM/SAED

Record: `10.5281/zenodo.18942976`

### Metadata gate

Verified:

- record ID `18942976`, DOI, and status `published`;
- API resource type `image`;
- licence `cc-by-4.0`;
- three-file record inventory;
- `TEM_SAED.zip` exact size `1,417,789,651` bytes;
- archive MD5 `c7bda9d495dd0fd657a8fe0332db4f9c`.

Quality flags retained without reinterpretation:

- API `publication_date` is `2027-05-10`, later than the 2026-08-05 audit date despite status `published`;
- the multi-file raw-experimental record is classified as resource type `image`.

Metadata snapshot:

`case_studies/zenodo_silver_tem_saed_metadata_audit/verified_snapshot.json`

### Archive gate

The 1.417 GB archive was downloaded transiently, verified, streamed member-by-member, and deleted before artifact upload.

Verified:

- archive SHA-256 `4569a878be7053c2e84867a5693e9483fd9b937b765ce5e3be15e3f154b5fa12`;
- 241 members;
- total uncompressed bytes `1,732,391,068`;
- complete member CRC and SHA-256 verification;
- no unsafe paths, duplicate normalized paths, symlinks, encryption, unsupported compression, or configured limit violations;
- no source member retained in evidence.

Archive composition:

- 212 TIFF raster exports;
- 19 text files;
- 9 DOCX files;
- 1 XLSX file;
- 0 native microscopy containers;
- 0 JPEG-like rendered rasters;
- all members under `MET/`.

Only two members have explicit SAED filename cues:

- `MET/Etanólico/ResultsSAED0016.txt`
- `MET/Etanólico/ResultsSAED0017.txt`

The inventory does not provide an unambiguous filename-level mapping from those result files to static diffraction-pattern images. No filename identifies a calibration file.

Scientific limitations:

- silver nanoparticles rather than cobalt oxide;
- TIFF exports with unresolved native raw status;
- folder and sequential filename conventions do not establish immutable sample/acquisition identity or independence;
- independent TEM segmentation labels absent;
- static SAED pattern identity, result-to-pattern mapping, acquisition conditions, centre, reciprocal calibration, and source-bound reflection assignments unresolved.

Closeout:

- source identity, archive integrity, and member hashing: **Supported**;
- representation and filename inventory: **Supported**;
- TEM external validation: **Inconclusive**;
- SAED external validation: **Inconclusive**;
- intake: `accepted_for_bounded_diagnostic_only`;
- external-validation ready: false;
- engineering-decision ready: false.

Verified snapshot:

`case_studies/zenodo_silver_tem_saed_archive_audit/verified_snapshot.json`

## Other candidates

### Zenodo W-Ta-Cr-V irradiation TEM/SAED

Record: `10.5281/zenodo.10512357`

Potential value:

- record description states raw TEM images and SAED patterns;
- as-deposited and He-irradiated conditions may support robustness diagnostics.

Current blockers:

- exact linked record versions, files, and checksums unresolved;
- member-level sample/acquisition lineage unresolved;
- TEM labels and SAED calibration evidence absent.

Action: resolve metadata before download. Do not add another large cross-material archive unless it addresses a specific unresolved limitation.

### NEMI 2026 workshop data

Useful for native HyperSpy and SPED format interoperability. SPED is not static SAED and must not be relabeled as such. Use only for a defined file-format gap.

### EMPIAR

A reputable CC0 electron-microscopy archive, but primarily biological cryo-EM and volume EM. Archive reputation does not remove target-domain mismatch. Do not bulk-download records without a task-matched inorganic TEM or static-SAED candidate.

## Now

### 1. Preserve the frozen source and evaluation contracts

Use:

- `case_studies/open_tem_saed_candidates/intake_runbook.md`
- `case_studies/open_tem_saed_candidates/evaluation_protocol.md`

Do not alter model weights, primary parameters, inclusion rules, or claim thresholds based on the audited public sources.

### 2. Convert confirmed gaps into author questions

For RepOD and Zenodo silver, request only evidence that can change readiness:

- original native detector/container files, if retained;
- immutable sample and acquisition identifiers;
- acquisition independence and repeated-field relationships;
- accelerating voltage, detector, camera length, pixel geometry, and acquisition mode;
- explicit mapping between SAED result files and static diffraction-pattern images;
- pattern centre and traceable reciprocal calibration;
- source-supported reflection assignments;
- independent TEM segmentation labels or permission to create blinded annotations.

Do not ask for generic “more data.”

### 3. Continue searching for task-matched in-domain data

Priority target:

- independent cobalt-oxide TEM/HRTEM images;
- at least two independent samples/acquisitions;
- raw or demonstrably lossless source files;
- acquisition metadata and scale calibration;
- no overlap with the current training source;
- annotation permission or existing labels.

For SAED, priority is not volume. It is a small set of static patterns with traceable centre, reciprocal calibration, acquisition identity, and reference assignments.

### 4. Preserve contact timeline

- TEM requests sent: 2026-08-04.
- SAED request sent: 2026-08-05.
- First TEM follow-up target: 2026-08-11.
- First SAED follow-up target: 2026-08-12.
- Second follow-up or alternate-contact escalation: approximately 2026-08-18 to 2026-08-19.

No response is recorded as `access_path_unresolved`, not as evidence that the data do not exist.

## Next — when sufficient metadata or in-domain data arrive

### TEM

1. Verify source, parent, sample, and acquisition disjointness.
2. Freeze the bounded material and acquisition domain.
3. Obtain at least two blinded independent annotations plus adjudication.
4. Freeze inclusion, exclusion, preprocessing, threshold, and metrics.
5. Run one blind external evaluation without parameter changes.
6. Report per-sample/acquisition performance and failure cases.
7. Close out as Supported, Diagnostic, Inconclusive, or Unsupported.

Cross-material data may support software robustness diagnostics. They cannot establish cobalt-oxide in-domain performance.

### SAED

1. Confirm static selected-area diffraction per pattern.
2. Bind accelerating voltage, detector, pixel geometry, centre, and reciprocal calibration.
3. Freeze reference structures or source assignments.
4. Predeclare primary and sensitivity settings.
5. Use at least two independent patterns/acquisitions.
6. Preserve unmatched rings and all failure cases.
7. Limit claims to the evidence actually supported.

## Later

Only after one credible external-validation case is complete:

- compare another instrument or laboratory;
- reserve a separate untouched holdout for post-improvement testing;
- evaluate uncertainty propagation;
- integrate validated characterization evidence with process and performance data;
- consider model retraining;
- consider additional analyzers or UI expansion.

## Prohibited shortcuts

Do not:

- use publication figures as external ground truth;
- infer SAED calibration from analyzer detections;
- tune parameters on the candidate evaluation set;
- treat silver or CoFeNi data as cobalt-oxide in-domain evidence;
- treat sequential filenames as proof of independent acquisitions;
- silently crop, smooth, normalize, interpolate, or relabel source data;
- use checksum or test success as proof of scientific validity;
- retrain the U-Net before an untouched evaluation protocol and holdout are secured.

## Closeout criterion

The next major milestone is not another downloaded archive. It is:

> One checksum-bound, independently sourced, predeclared, reproducible TEM or SAED external-validation case with task-matched metadata, explicit limitations, and a defensible scientific closeout.
