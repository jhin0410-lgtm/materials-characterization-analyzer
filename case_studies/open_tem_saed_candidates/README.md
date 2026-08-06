# Open TEM and SAED Candidate Addendum

This directory records public TEM and SAED sources, bounded source-audit evidence, and the procedures required before analyzer execution.

It is an addendum to the existing technique-specific registries:

- TEM: `case_studies/tem_external_validation_candidate_registry/`
- SAED: `case_studies/saed_public_candidate_registry/`

The technique-specific registries remain authoritative for analyzer-specific candidate classification. This addendum prevents mixed TEM/SAED sources from being duplicated or promoted inconsistently.

## Files

- `candidate_registry.json`: historical machine-readable source triage snapshot dated 2026-08-05.
- `audit_status_2026-08-06.json`: consolidated status after the completed RepOD, Zenodo, Mendeley, Dryad, and FHI audits.
- `intake_runbook.md`: byte-preserving acquisition and fail-closed intake procedure.
- `evaluation_protocol.md`: predeclared TEM and SAED evaluation contract.
- `docs/TEM_SAED_OPEN_DATA_ROADMAP.md`: project-level decisions and sequencing.

## Current decision

Four sources have completed a bounded, checksum-bound source audit and are usable only for diagnostic source, representation, metadata, or interoperability work:

1. RepOD CoFeNi TEM/HRTEM/SAED — `10.18150/SIOWH6`.
2. Zenodo silver TEM/SAED — `10.5281/zenodo.18942976`.
3. Zenodo W-Ta-Cr-V TEM/SAED — child record `10.5281/zenodo.10512463`, linked from `10.5281/zenodo.10512357`.
4. Zenodo Ge native-DM3 TEM/SAED — `10.5281/zenodo.15082448`.

Three additional source families remain blocked before bounded source-file auditing:

- Mendeley lunar TEM/SAED registry: public landing metadata are visible, but documented file APIs require OAuth authorization.
- Dryad TiSe2 SAED: record and file identity are visible, but anonymous bundle and individual-file acquisition returned authorization failures in the verified workflow.
- FHI Co3O4 TEM: exact-material institutional record identity is confirmed, but source-file routes redirect to authentication.

No candidate in this addendum is external-validation-ready. The current scientific evidence level remains **Inconclusive**.

## Interpretation

`bounded_source_audit_complete` means the exact source archive and selected member identities were inspected under a frozen, fail-closed procedure. It does not authorize analyzer inference, parameter selection, retraining, segmentation-performance claims, calibrated SAED claims, or engineering decisions.

A source remains blocked from external validation when any required gate is unresolved, including:

- raw or demonstrably lossless detector provenance;
- immutable sample and acquisition identity;
- acquisition independence and analyzer-development non-use;
- independent TEM labels;
- static-SAED pattern identity, centre, camera geometry, and reciprocal calibration;
- task-matched material and acquisition comparability.

The next useful action is not another generic archive download. It is obtaining authoritative metadata or reference evidence that closes one of those gates without exposing the evaluation set to tuning.
