# TEM and SAED Source-Receipt Runbook

## Purpose

Preserve source identity and prevent accidental conversion of data acquisition into post hoc model development.

## 1. Register the source before download

Record:

- repository and DOI or persistent identifier;
- record version and access date;
- title, creators, licence, and related publication;
- expected filenames, sizes, and repository checksums;
- reason for selection;
- intended TEM, SAED, or diagnostic role;
- predeclared maximum download scope.

Do not select files after viewing analyzer output.

## 2. Preserve original bytes

Create separate locations:

```text
source_package/
  raw_immutable/
  metadata_snapshot/
  derived_inventory/
  intake_report/
```

Rules:

- place downloaded files in `raw_immutable/`;
- never overwrite or re-save source files;
- do not open and save proprietary microscopy files in vendor software;
- compute SHA-256 immediately;
- preserve repository MD5 or other published checksum separately;
- record download time and exact source URL;
- keep derived previews outside `raw_immutable/`.

## 3. Verify package identity

For every downloaded file:

1. compare size with the repository record;
2. verify the repository checksum when supplied;
3. compute SHA-256;
4. enumerate archive members without extracting over existing paths;
5. reject absolute paths, parent traversal, duplicate normalized paths, and symlinks;
6. compute member checksums after safe extraction;
7. preserve the archive and extracted members.

A checksum mismatch is fatal until resolved.

## 4. Build the member inventory

For each member, record:

- source archive;
- member path;
- byte size and SHA-256;
- format and bit depth;
- dimensions and frame count;
- compression;
- embedded instrument metadata;
- sample and acquisition identifiers;
- scale or calibration;
- whether the member is raw, processed, rendered, or unresolved;
- associated publication figure or table;
- proposed role.

Do not infer missing metadata from filenames unless it is explicitly documented as a source convention.

## 5. Establish legal and provenance boundaries

Confirm:

- data licence applies to the files, not only the article or software;
- attribution requirements;
- redistribution constraints;
- source creators and institutions;
- whether files may have been used in the target analyzer's development;
- whether repository, author, or acquisition overlap exists.

Repository separation alone does not prove scientific independence.

## 6. TEM-specific gate

Required before segmentation evaluation:

- task-matched TEM/HRTEM modality;
- raw or demonstrably lossless images;
- pixel calibration and acquisition conditions;
- at least two independent samples or acquisitions;
- content-disjointness from training and model selection;
- two blinded independent labelers;
- adjudicated consensus;
- frozen annotation definition;
- frozen preprocessing and metric contract.

Without independent labels, TEM files may support ingestion or qualitative diagnostics only.

## 7. SAED-specific gate

Required before calibrated evaluation:

- static selected-area diffraction confirmed;
- accelerating voltage;
- detector and pixel geometry;
- traceable pattern centre;
- traceable reciprocal calibration or source-bound calibration standard;
- at least two independent patterns/acquisitions;
- frozen reference structure or source assignment;
- frozen primary and sensitivity settings;
- analyzer-development non-use.

SPED, cRED, 3DED, FFTs, or rendered diffraction figures must not be silently treated as static raw SAED.

## 8. Intake decision

Allowed decisions:

- `accepted_for_frozen_external_evaluation`
- `accepted_for_bounded_diagnostic_only`
- `metadata_resolution_required`
- `rejected_wrong_modality_or_domain`
- `rejected_nonindependent`
- `rejected_integrity_failure`
- `rejected_licence_unresolved`

The default is fail-closed.

## 9. Stop conditions

Stop and report rather than proceeding when:

- checksums fail;
- raw status is unresolved;
- files are rendered panels;
- sample/acquisition identity cannot be bound;
- fewer than two independent acquisitions exist;
- labels or calibration are missing;
- candidate data influenced model or parameter selection;
- the requested claim exceeds the material or acquisition domain.

## 10. Completion report

The source-audit report must include:

- source and record version;
- files acquired and excluded;
- repository checksums and computed SHA-256;
- archive/member inventory;
- provenance and licence assessment;
- TEM and SAED gate results;
- fatal errors, warnings, and scientific limitations;
- allowed and prohibited uses;
- final intake decision;
- generated-artifact locations;
- `git status` when run from a repository checkout.
