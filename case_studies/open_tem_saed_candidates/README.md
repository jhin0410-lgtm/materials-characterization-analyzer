# Open TEM and SAED Candidate Addendum

This directory records public TEM and SAED sources identified on 2026-08-05 and the procedures required before using any of them.

It is an addendum to the existing technique-specific registries:

- TEM: `case_studies/tem_external_validation_candidate_registry/`
- SAED: `case_studies/saed_public_candidate_registry/`

The existing registries remain authoritative for analyzer-specific candidate classification. This addendum prevents newly identified mixed TEM/SAED sources from being duplicated inconsistently across the two registries.

## Files

- `candidate_registry.json`: dated machine-readable source triage.
- `intake_runbook.md`: byte-preserving acquisition and fail-closed intake procedure.
- `evaluation_protocol.md`: predeclared TEM and SAED evaluation contract.
- `docs/TEM_SAED_OPEN_DATA_ROADMAP.md`: project-level decisions and sequencing.

## Current decision

- First bounded source audit: RepOD `10.18150/SIOWH6`.
- Second bounded source audit: Zenodo `10.5281/zenodo.18942976`, only after a member-selection plan.
- Metadata resolution before download: Zenodo `10.5281/zenodo.10512357`.
- Diagnostic-only unless a concrete format gap exists: NEMI workshop SPED/TEM files.
- Not selected as a generic bulk source: EMPIAR.

No candidate in this addendum is external-validation-ready. The current scientific evidence level remains **Inconclusive**.

## Interpretation

`ready_for_bounded_source_audit` means the repository record is sufficiently concrete to inspect a limited, checksum-bound source package. It does not authorize analyzer execution or scientific performance claims.

The audit must stop before evaluation if raw/lossless status, sample identity, acquisition identity, independence, TEM labels, SAED centre, or reciprocal calibration cannot be established.
