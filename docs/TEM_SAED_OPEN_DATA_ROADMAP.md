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

### Priority 1 — RepOD CoFeNi TEM/HRTEM/SAED

Record: `10.18150/SIOWH6`

Why it is useful:

- public CC BY 4.0 data;
- explicit TEM, HRTEM, and SAED archives;
- repository checksums;
- stated S/TEM TITAN 80–300 instrument;
- two small archives suitable for a bounded audit.

Why it is not yet validation-ready:

- archive members have not been inventoried;
- raw detector versus exported image status is unresolved;
- pattern centre and reciprocal calibration are absent from the landing-page evidence;
- sample/acquisition independence is not yet established;
- it is CoFeNi, not cobalt oxide;
- no independent TEM segmentation labels are supplied.

Action: perform the first bounded source audit. Do not run the analyzer until the source audit freezes the usable members and scientific limits.

### Priority 2 — Zenodo silver nanoparticle TEM/SAED

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

Action: audit only after a bounded member-selection plan is written without looking at analyzer output.

### Priority 3 — Zenodo W-Ta-Cr-V irradiation TEM/SAED

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

### 1. Freeze the source-receipt procedure

Use `case_studies/open_tem_saed_candidates/intake_runbook.md`.

Every source must be:

- preserved byte-for-byte;
- checksum-bound;
- separated from derived files;
- accompanied by licence and source metadata;
- rejected from evaluation when identity, calibration, or independence is unresolved.

### 2. Freeze the evaluation protocol

Use `case_studies/open_tem_saed_candidates/evaluation_protocol.md`.

The protocol must be fixed before viewing analyzer results. Parameter adjustment after seeing candidate results converts validation into model development.

### 3. Execute one bounded source audit

Start with the small RepOD CoFeNi archives. The purpose is to determine whether the files are scientifically auditable, not to prove analyzer performance.

Stop conditions include:

- rendered multi-panel figures instead of source images;
- missing or conflicting checksums;
- fewer than two independent patterns/acquisitions;
- no traceable SAED centre or reciprocal calibration;
- no usable sample/acquisition binding;
- evidence that the files were used during analyzer development.

### 4. Preserve the release baseline

Do not modify segmentation weights, SAED primary parameters, output schemas, or scientific thresholds during source acquisition.

## Next

### TEM

1. Complete archive and metadata audit.
2. Verify content disjointness from the target training source.
3. Define the bounded material and acquisition domain.
4. Obtain at least two blinded independent annotations plus adjudication.
5. Freeze image inclusion, exclusion, preprocessing, threshold, and metrics.
6. Run one blind external evaluation.
7. Close out as Supported, Diagnostic, Inconclusive, or Unsupported.

Cross-material public datasets may test software robustness. They cannot establish cobalt-oxide in-domain performance.

### SAED

1. Complete archive and member inventory.
2. Confirm static selected-area acquisition.
3. Bind accelerating voltage, detector, pixel geometry, centre, and reciprocal calibration.
4. Freeze reference structures or source assignments.
5. Predeclare primary and sensitivity settings.
6. Use at least two independent patterns/acquisitions.
7. Preserve unmatched rings and all failure cases.
8. Close out without upgrading phase, zone-axis, or d-spacing claims beyond the evidence.

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
