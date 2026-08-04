# SAED independent source transfer verification

This case bridges an authoritative independent-source response into the existing fail-closed `mca saed-validation-intake` workflow.

It is used only after `scripts/saed_independent_validation_source_request.py assess` reports:

```text
candidate_response_ready_for_bounded_saed_source_verification
```

A response declaration alone is not enough. This stage requires separate human authorization for a narrowly scoped transfer, verifies the response evidence bundle, verifies the source collection manifest, verifies every declared file by byte count and SHA-256, and requires the metadata that the existing SAED intake contract cannot infer.

## Inputs

1. The complete response-assessment output directory containing:
   - `saed_independent_source_author_response_normalized.json`
   - `saed_independent_source_response_assessment.json`
   - `saed_independent_source_response_assessment.md`
   - `saed_bounded_source_verification_plan.json`
   - `saed_independent_source_response_manifest.json`
2. A local immutable data root containing only the explicitly authorized collection manifest and declared pattern files.
3. A completed transfer-verification record based on `verification_record.example.json`.

The verification record must explicitly provide information that is absent or not independently verified in the source response, including:

- authorization identity, basis, date, and bounded scope;
- the exact local collection-manifest identity;
- an intake-compatible source type and mapping basis;
- independently verified reuse authorization;
- material-identity provenance;
- creator overlap and cross-dataset lineage independence;
- the reference identifier selected from the declared frozen reference set;
- per-pattern file format, material ID, camera length when available, preprocessing, exclusion state, and parameter-selection reuse.

No field is inferred from filenames, extensions, image appearance, or analyzer output.

## Run

```bash
python scripts/verify_saed_independent_source_transfer.py \
  --response-bundle outputs/saed_independent_validation_source_response \
  --verification path/to/saed_transfer_verification.json \
  --data-root path/to/immutable_authorized_source \
  --output outputs/saed_independent_source_transfer_verification
```

Generated artifacts:

- `saed_verified_transfer_inventory.csv`
- `saed_external_validation_intake_draft.json`
- `saed_transfer_verification_summary.json`
- `saed_transfer_verification_report.md`
- `saed_transfer_verification_artifact_manifest.json`

A successful result is only:

```text
ready_to_run_saed_validation_intake
```

It does not mean that the dataset is ready for analyzer execution or external evaluation.

## Run the existing intake

```bash
mca saed-validation-intake \
  --manifest outputs/saed_independent_source_transfer_verification/saed_external_validation_intake_draft.json \
  --data-root path/to/immutable_authorized_source \
  --output outputs/saed_external_validation_intake
```

The generated draft deliberately leaves source review, file-content audit, calibration review, acquisition-independence review, content-overlap review, analysis parameters, indexing protocol, metrics, uncertainty, exclusions, and manifest freeze unresolved. The existing intake may therefore reach only `ready_to_freeze_saed_analysis_protocol` until those independent reviews are completed and the manifest is explicitly frozen.

## Source-type compatibility

The source-response contract predates the intake bridge and permits `private_transfer`, while the existing intake uses `private_acquisition`. The bridge does not silently reinterpret this value. A transfer-verification record must explicitly select `private_acquisition` and document the mapping basis. Directly compatible values (`external_public`, `new_acquisition`, and `private_acquisition`) must match exactly.

Reference values are mapped only through the documented semantic pairs:

- `source_assignments` → `source_author_assignments`
- `predeclared_reference_structures` → `curated_structures`

The selected intake reference identifier must be one of the identifiers declared in the authoritative response.

## Scientific boundary

This stage reads files only to calculate byte counts and SHA-256 digests. It does not:

- decode diffraction arrays;
- inspect image content;
- estimate or tune the pattern center;
- infer reciprocal calibration;
- select smoothing, prominence, radius bounds, or candidate counts;
- run the SAED analyzer;
- index reflections, phases, or zone axes;
- calculate analyzer performance;
- authorize engineering use.

Passing this stage is **Diagnostic** evidence of transfer identity and contract compatibility only.
