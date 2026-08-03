# BIR-MicroED 200 keV Metadata Resolution

This case converts the unresolved BIR-MicroED source gates into a strict,
machine-readable request and response contract. It consumes only the
checksum-bound output of `mca saed-bir-metadata-audit`.

## Generate the request package

```bash
mca saed-bir-metadata-resolution   --audit-output outputs/saed_bir_200kev_metadata_audit   --output outputs/saed_bir_metadata_resolution
```

The output includes a correspondence-ready Markdown request and a JSON response
template. The template requests authoritative representation, preprocessing,
member checksum, sample/acquisition lineage, centre, reciprocal calibration,
detector geometry, and analyzer-development non-use evidence.

## Assess a completed response

```bash
mca saed-bir-metadata-resolution   --audit-output outputs/saed_bir_200kev_metadata_audit   --response completed_author_response.json   --output outputs/saed_bir_author_response_assessment
```

A structurally valid unresolved or negative response is preserved as
`metadata_response_received_but_source_not_ready`. A complete positive response
reaches only `metadata_response_ready_for_bounded_download_verification` and
emits a draft `saed_validation_intake_handoff_template.json`.

## Scientific boundary

This command never downloads the archive, verifies member bytes, opens MRC
arrays, estimates a centre, infers calibration, runs the analyzer, or supports
crystallographic or engineering claims. Even a positive metadata response does
not set `archive_download_authorized`, `saed_validation_intake_ready`, or
`predeclared_external_evaluation_ready` to true. Synthetic positive fixtures
validate software behavior only.
