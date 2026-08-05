# TEM and SAED Open-Data Validation Roadmap

Status date: **2026-08-05**

## Decision

Open TEM and SAED data do exist. The limiting factor is not the prestige of the repository by itself. The limiting factor is whether a record preserves enough task-matched evidence to support an independent scientific claim.

A DOI, an institutional repository, or a CC licence can establish identity and reuse permission. It does not by itself establish:

- raw detector status;
- immutable sample and acquisition identity;
- independence from model development;
- TEM segmentation ground truth;
- SAED pattern centre and reciprocal calibration;
- comparability to the target material and acquisition domain;
- enough independent samples or acquisitions for generalization claims.

The repository therefore distinguishes three levels:

1. **Public source:** files can be located and reused.
2. **Bounded source-audit candidate:** a checksum-bound subset can be inspected without making performance claims.
3. **External-validation-ready source:** every task-specific scientific gate is satisfied before analyzer execution.

No newly identified record is at level 3.

## Current software and scientific state

- Software baseline: `v0.11.0`.
- TEM software validation: supported for the implemented pipeline and fail-closed intake.
- SAED software validation: supported for the implemented pipeline and fail-closed intake.
- TEM scientific evidence: **Inconclusive** for independent in-domain cobalt-oxide validation.
- SAED scientific evidence: **Inconclusive** for calibrated static-pattern validation.
- External-validation-ready analyzers: **0**.
- Engineering-decision-ready analyzers: **0**.

The software baseline remains frozen while source evidence is collected. A new training run is not justified merely because more public images have been found.

## Newly identified public candidates

The dated machine-readable snapshot is:

`case_studies/open_tem_saed_candidates/candidate_registry.json`

### Completed bounded audit — RepOD CoFeNi TEM/HRTEM/SAED

Record: `10.18150/SIOWH6`

The live audit completed on 2026-08-05 and verified:

- RepOD record version 1.0 and 12-file inventory;
- file-level CC BY 4.0 licence returned by the API;
- repository MD5 and computed SHA-256 for `TEM_SAED.zip`, `HRTEM_SAED.zip`, and `HAADF_STEM.tif`;
- two valid ZIP archives with safe member paths and matching CRC values;
- seven decodable TIFF members;
- three SAED-named members, one HRTEM member, two BF/DF TEM members, and one HAADF-STEM image;
- no source archive or image retained in the evidence artifact.

Scientific interpretation:

- the seven files are TIFF raster exports, not native detector containers;
- embedded metadata are limited to basic raster fields;
- raw-detector status, immutable sample/acquisition lineage, and acquisition independence remain unresolved;
- no independent TEM segmentation labels are supplied;
- static selected-area acquisition, pattern centre, reciprocal calibration, and member-level reference assignments remain unresolved;
- CoFeNi is outside the current cobalt-oxide target domain.

Closeout:

- source identity and archive integrity: **Supported**;
- analyzer scientific evidence: **Inconclusive**;
- intake: `accepted_for_bounded_diagnostic_only`;
- external-validation ready: false;
- engineering-decision ready: false.

The verified snapshot is stored at:

`case_studies/repod_cofeni_tem_saed_source_audit/verified_snapshot.json`

Action: retain this source as a checksum-bound format and metadata diagnostic. Do not run performance validation or tune the analyzer on it. Seek author-provided acquisition metadata/native files or a task-matched independent cobalt-oxide source.

### Next bounded candidate — Zenodo silver nanoparticle TEM/SAED

Record: `10.5281/zenodo.18942976`

Why it is useful:

- the record states that it contains original experimental TEM and SAED outputs;
- `TEM_SAED.zip` is public, checksum-listed, and CC BY 4.0;
- the same archive can exercise both TEM and SAED intake.

Why it is not yet validation-ready:

- the archive is 1.4 GB and its member inventory is unresolved;
- static-SAED acquisition mode is not yet confirmed;
- calibration, centre, sample identity, and acquisition identity are unresolved;
- it contains silver nanoparticles rather than cobalt oxide;
- no independent segmentation labels are reported.

Action: audit only after a bounded member-selection plan is written without looking at analyzer output. Do not download the entire archive merely to increase dataset volume.

### Metadata-resolution candidate — Zenodo W-Ta-Cr-V irradiation TEM/SAED

Record: `10.5281/zenodo.10512357`

Why it is useful:

- the record explicitly describes raw TEM images and SAED patterns;
- as-deposited and He-irradiated conditions could support condition-aware robustness testing;
- it is a materials-science rather than biological microscopy source.

Why it is not yet ready:

- exact file inventory and checksums were not resolved in this snapshot;
- member-level calibration and lineage are unresolved;
- no independent segmentation labels are reported.

Action: resolve linked record versions and file inventory before any download.

### Diagnostic-only candidates

The 2026 NEMI workshop data provide useful native TEM/STEM/HyperSpy/SPED formats. They are appropriate only when a specific format-interoperability gap exists. SPED is not static SAED and must not be relabeled as such.

EMPIAR is a reputable CC0 raw electron-microscopy archive, but it is primarily oriented toward biological cryo-EM and volume EM. Archive reputation does not remove target-domain mismatch. Do not bulk-download EMPIAR records without a specific task-matched candidate.

## Now

### 1. Preserve the source-receipt procedure

Use `case_studies/open_tem_saed_candidates/intake_runbook.md`.

Every source must be:

- preserved byte-for-byte during intake;
- checksum-bound;
- separated from derived files;
- accompanied by licence and source metadata;
- rejected from evaluation when identity, calibration, or independence is unresolved.

### 2. Preserve the frozen evaluation protocol

Use `case_studies/open_tem_saed_candidates/evaluation_protocol.md`.

The protocol must be fixed before viewing analyzer results. Parameter adjustment after seeing candidate results converts validation into model development.

### 3. Resolve the RepOD scientific gaps without analyzer execution

The archive audit is complete. Remaining work is metadata resolution, not algorithm work:

- confirm whether original native detector files still exist;
- obtain sample and acquisition identifiers;
- bind accelerating voltage, camera length, detector, and pixel geometry to each SAED pattern;
- obtain a traceable pattern centre and reciprocal calibration;
- establish whether the three SAED-named TIFFs are independent acquisitions;
- obtain source-supported reflection assignments where available.

### 4. Prepare the silver-archive bounded plan

Before downloading the 1.4 GB Zenodo archive, predeclare:

- exact archive version and checksum;
- maximum files and bytes to inspect;
- member-selection rule independent of analyzer output;
- stop conditions;
- metadata-only artifact policy;
- allowed diagnostic claims.

### 5. Preserve the release baseline

Do not modify segmentation weights, SAED primary parameters, output schemas, or scientific thresholds during source acquisition.

## Next

### TEM

1. Verify content disjointness from the target training source.
2. Define the bounded material and acquisition domain.
3. Obtain at least two blinded independent annotations plus adjudication.
4. Freeze image inclusion, exclusion, preprocessing, threshold, and metrics.
5. Run one blind external evaluation.
6. Close out as Supported, Diagnostic, Inconclusive, or Unsupported.

Cross-material public datasets may test software robustness. They cannot establish cobalt-oxide in-domain performance.

### SAED

1. Confirm static selected-area acquisition.
2. Bind accelerating voltage, detector, pixel geometry, centre, and reciprocal calibration.
3. Freeze reference structures or source assignments.
4. Predeclare primary and sensitivity settings.
5. Use at least two independent patterns/acquisitions.
6. Preserve unmatched rings and all failure cases.
7. Close out without upgrading phase, zone-axis, or d-spacing claims beyond the evidence.

## Later

Only after one credible external-validation case is complete:

- compare another instrument or laboratory;
- add a separate untouched holdout for post-improvement testing;
- evaluate uncertainty propagation;
- integrate validated characterization evidence with process and performance data;
- consider model retraining;
- consider UI expansion or additional analyzers.

## Contact timeline

- TEM requests were sent on 2026-08-04.
- SAED request was sent on 2026-08-05.
- First TEM follow-up target: 2026-08-11.
- First SAED follow-up target: 2026-08-12.
- Second follow-up or alternate-contact escalation: approximately 2026-08-18 to 2026-08-19.

No response should be recorded as `access_path_unresolved`, not as evidence that the data do not exist.

## Prohibited shortcuts

Do not:

- use publication figures as external ground truth;
- estimate SAED calibration from analyzer detections;
- tune parameters on the candidate evaluation set;
- treat a different material as in-domain evidence;
- treat one sample or one acquisition as generalization evidence;
- silently crop, smooth, normalize, interpolate, or relabel source data;
- use test success as proof of scientific validity;
- retrain the U-Net before an untouched evaluation protocol and holdout are secured.

## Closeout criterion

The next major milestone is not “more data downloaded.” It is:

> One checksum-bound, independently sourced, predeclared, reproducible TEM or SAED external-validation case with explicit limitations and a defensible scientific closeout.
