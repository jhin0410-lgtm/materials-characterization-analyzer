# TEM and SAED Open-Data Validation Roadmap

Status date: **2026-08-06**

Machine-readable status:

`case_studies/open_tem_saed_candidates/audit_status_2026-08-06.json`

## Decision

Open TEM and SAED data exist. The limiting factor is not the number or prestige of repositories. The limiting factor is whether a source preserves enough task-matched evidence to support an independent scientific claim.

A DOI, repository record, checksum, and reuse licence may establish source identity and lawful reuse. They do not by themselves establish:

- detector-native or demonstrably lossless intensity provenance;
- immutable sample and acquisition identity;
- acquisition independence and non-use in analyzer development;
- independent TEM segmentation ground truth;
- static-SAED pattern identity;
- pattern centre, camera geometry, and traceable reciprocal calibration;
- comparability to the target material and acquisition domain;
- enough independent samples or acquisitions for generalization claims.

The repository distinguishes four levels:

1. **Public source:** a record can be located and its reuse basis can be assessed.
2. **Metadata-audited source:** record identity, version, licence, and file references are pinned.
3. **Bounded source-audited source:** exact source archives and selected member identities are verified under a frozen, fail-closed procedure.
4. **External-validation-ready source:** every task-specific scientific gate is satisfied before analyzer execution.

Four public sources have reached level 3. None has reached level 4.

## Current state

- Software baseline: `v0.11.0`.
- TEM implemented behavior and fail-closed intake: **Supported** as software validation.
- SAED implemented behavior and fail-closed intake: **Supported** as software validation.
- Bounded source audits completed for diagnostic use only: **4**.
- Sources blocked at access or file-inventory resolution: **3**.
- TEM independent in-domain external validation: **Inconclusive**.
- SAED calibrated external validation: **Inconclusive**.
- External-validation-ready analyzers: **0**.
- Engineering-decision-ready analyzers: **0**.

No analyzer weight, primary parameter, output schema, inclusion rule, or scientific evidence threshold was changed during these source audits.

## Completed bounded source audits

### 1. RepOD CoFeNi TEM/HRTEM/SAED

Record: `10.18150/SIOWH6`

Verified evidence:

- RepOD record and file identity;
- file-level CC BY 4.0 reuse terms;
- repository MD5 and computed SHA-256 for the selected files;
- safe ZIP integrity and member inventory;
- seven TIFF members, including three SAED-named members;
- no source archive or image retained in the evidence artifact.

Primary limitations:

- TIFF raster exports rather than native detector containers;
- immutable sample/acquisition identity and independence unresolved;
- independent TEM segmentation labels absent;
- static-SAED centre, reciprocal calibration, and source-bound assignments unresolved;
- CoFeNi is outside the cobalt-oxide target domain.

Verified snapshot:

`case_studies/repod_cofeni_tem_saed_source_audit/verified_snapshot.json`

### 2. Zenodo silver TEM/SAED

Record: `10.5281/zenodo.18942976`

Verified evidence:

- published record identity, CC BY 4.0 reuse terms, and three-file inventory;
- exact `TEM_SAED.zip` byte count, repository MD5, and computed SHA-256;
- safe archive integrity, CRC verification, and complete member hashing;
- 241 members, including 212 TIFF raster exports;
- two SAED result-text filename cues;
- no source archive or member retained in the evidence artifact.

Primary limitations:

- no native microscopy container;
- immutable sample/acquisition identity and independence unresolved;
- independent TEM labels absent;
- SAED result files are not unambiguously mapped to static diffraction-pattern images;
- centre, reciprocal calibration, acquisition conditions, and source-bound assignments unresolved;
- silver nanoparticles are outside the cobalt-oxide target domain;
- the future-dated API publication metadata remain a retained quality flag rather than being normalized away.

Verified snapshots:

- `case_studies/zenodo_silver_tem_saed_metadata_audit/verified_snapshot.json`
- `case_studies/zenodo_silver_tem_saed_archive_audit/verified_snapshot.json`

### 3. Zenodo W-Ta-Cr-V TEM/SAED

Parent record: `10.5281/zenodo.10512357`

Audited child record: `10.5281/zenodo.10512463`

Verified evidence:

- child record, DOI, ODbL licence, exact archive identity, MD5, and computed SHA-256;
- safe inventory of 48 members;
- five native DM3 or DM4 microscopy containers;
- three SAED filename cues;
- as-deposited and He-irradiated condition path cues;
- selected native-file header identity.

Primary limitations:

- native-container presence does not prove detector-native intensity preservation;
- source-assigned specimen pairing is unresolved;
- pattern centre and reciprocal calibration are unresolved;
- acquisition independence and analyzer-development non-use are unresolved;
- W-Ta-Cr-V is outside the cobalt-oxide target domain.

Verified snapshot:

`case_studies/zenodo_wtacrv_tem_saed_source_audit/verified_workflow_snapshot.json`

### 4. Zenodo Ge native-DM3 TEM/SAED

Record: `10.5281/zenodo.15082448`

Verified evidence:

- published record identity and CC BY 4.0 reuse terms;
- exact 7z archive identity, MD5, computed SHA-256, and integrity test;
- safe 92-member inventory;
- 15 native DM3 microscopy containers;
- record-declared same-location TEM/SAED pairs;
- selected DM3 header version and byte-order identity.

Primary limitations:

- the pinned ExifTool build classified the DM3 files as unknown and extracted no embedded microscopy metadata;
- sample/acquisition lineage remains unresolved;
- pattern centre and reciprocal calibration remain unresolved;
- independent TEM labels and analyzer-development non-use remain unresolved;
- Ge is outside the cobalt-oxide target domain.

Verified snapshot:

`case_studies/zenodo_ge_dm3_tem_saed_source_audit/verified_snapshot.json`

## Access or file-inventory blocked sources

### Mendeley lunar TEM/SAED registry

Seven version-pinned records have supported public landing-page identity, descriptions, and reuse terms. Documented metadata, file, folder, and ZIP endpoints consistently required OAuth authorization in the verified workflow.

Therefore, filenames, UUIDs, byte counts, hashes, formats, folders, detector provenance, and scientific lineage remain unresolved. Landing-page HTML hashes are observation snapshots, not immutable source-file checksums.

Verified snapshot:

`case_studies/mendeley_lunar_tem_saed_source_audit/verified_expanded_registry_snapshot.json`

### Dryad TiSe2 SAED

Record: `10.5061/dryad.6djh9w1hw`

The record and target file identities are supported. The official dataset-bundle route returned HTTP 401 and the individual-file route returned HTTP 403 from the verified GitHub workflow. Archive integrity, experiment/simulation partition, lossless measurement provenance, calibration, and acquisition independence therefore remain inconclusive.

Verified snapshot:

`case_studies/dryad_tise2_saed_source_audit/verified_snapshot.json`

### FHI Co3O4 TEM

Record: `D63268`; sample: `S32564`.

This is the most relevant exact-material source among the latest audits. Institutional record identity, RAW DATA classification, open-access marker, and Co3O4 context are supported. However, `TEM.zip` and `OTEM_2.zip` routes redirected to authentication, so archive/member identity, independent labels, calibration, and development non-use remain unresolved.

Verified snapshot:

`case_studies/fhi_co3o4_tem_saed_source_audit/verified_snapshot.json`

## Now

### 1. Preserve frozen contracts

Use:

- `case_studies/open_tem_saed_candidates/intake_runbook.md`
- `case_studies/open_tem_saed_candidates/evaluation_protocol.md`

Do not change model weights, primary parameters, inclusion rules, preprocessing, or claim thresholds based on any audited source.

### 2. Resolve evidence that can change readiness

For author or repository follow-up, request only evidence that closes a named gate:

- original native detector/container files, if retained;
- immutable sample and acquisition identifiers;
- repeated-field relationships and acquisition independence;
- accelerating voltage, detector, camera length, pixel geometry, and acquisition mode;
- explicit mapping from SAED result files to static pattern files;
- pattern centre and traceable reciprocal calibration;
- source-supported reflection assignments;
- independent TEM labels or permission for blinded annotation;
- explicit confirmation that the proposed evaluation data were not used for analyzer development or selection.

Do not request generic “more data.”

### 3. Prioritize the exact-material access path

The highest-value unresolved path is FHI Co3O4 because it addresses material-domain mismatch. Access alone will not make it validation-ready; the archive must still pass checksum, lineage, label, overlap, and frozen-protocol gates.

### 4. Preserve the contact timeline

- TEM requests sent: 2026-08-04.
- SAED request sent: 2026-08-05.
- First TEM follow-up target: 2026-08-11.
- First SAED follow-up target: 2026-08-12.
- Second follow-up or alternate-contact escalation: approximately 2026-08-18 to 2026-08-19.

No response is recorded as `access_path_unresolved`, not as evidence that the data do not exist.

## Next — only when sufficient metadata or in-domain data arrive

### TEM

1. Verify source, parent, sample, and acquisition disjointness.
2. Freeze the bounded material and acquisition domain.
3. Obtain at least two blinded independent annotations plus adjudication.
4. Freeze inclusion, exclusion, preprocessing, threshold, and metrics.
5. Run one blind external evaluation without parameter changes.
6. Report per-sample/acquisition performance and failure cases.
7. Close out as Supported, Diagnostic, Inconclusive, or Unsupported.

Cross-material data may support software and representation diagnostics. They cannot establish cobalt-oxide in-domain performance.

### SAED

1. Confirm static selected-area diffraction for each pattern.
2. Bind accelerating voltage, detector, pixel geometry, centre, and reciprocal calibration.
3. Freeze reference structures or source assignments.
4. Predeclare primary and sensitivity settings.
5. Use at least two independent patterns or acquisitions.
6. Preserve unmatched rings and every failure case.
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
- tune parameters on a candidate evaluation set;
- treat cross-material data as cobalt-oxide in-domain evidence;
- treat sequential filenames or folders as proof of independent acquisitions;
- silently crop, smooth, normalize, interpolate, or relabel source data;
- use checksum success, workflow success, or passing software tests as proof of scientific validity;
- retrain the U-Net before an untouched evaluation protocol and holdout are secured.

## Closeout criterion

The next major milestone is not another downloaded archive. It is:

> One checksum-bound, independently sourced, predeclared, reproducible TEM or SAED external-validation case with task-matched metadata, explicit limitations, and a defensible scientific closeout.
