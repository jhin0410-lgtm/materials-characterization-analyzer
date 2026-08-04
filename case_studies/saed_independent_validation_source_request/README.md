# SAED independent validation source request

This case study converts the checksum-bound public SAED candidate registry into a send-ready, fail-closed request and response-assessment package for a raw or demonstrably lossless calibrated static SAED source.

## Why this exists

The pinned public registry currently has no candidate ready for predeclared external evaluation. Existing candidates remain blocked by unresolved sample or acquisition lineage, detector metadata, pattern centre, reciprocal calibration, file inventory, reuse rights, analyzer-development non-use, acquisition-mode mismatch, inaccessible source bytes, or rendered/software-example status.

Downloading large archives or running the SAED analyzer does not resolve those evidence gaps. The next bounded action is to request authoritative metadata, checksums, references and referrals using a machine-readable contract.

## Build the correspondence package

First reproduce the registry:

```bash
mca saed-candidates \
  --config case_studies/saed_public_candidate_registry/case_config.json \
  --output outputs/saed_public_candidate_registry
```

Then build the request:

```bash
python scripts/saed_independent_validation_source_request.py build \
  --registry-output outputs/saed_public_candidate_registry \
  --output outputs/saed_independent_validation_source_request
```

Generated files:

- `saed_independent_source_request.json`
- `saed_independent_source_author_response_template.json`
- `saed_independent_source_correspondence.md`
- `saed_independent_source_request_summary.json`
- `saed_independent_source_request_manifest.json`

The software does not send the message or hard-code private recipient information.

## Assess a completed response

```bash
python scripts/saed_independent_validation_source_request.py assess \
  --registry-output outputs/saed_public_candidate_registry \
  --response completed_author_response.json \
  --output outputs/saed_independent_validation_source_response
```

A response may declare:

- `candidate_available`
- `referral_only`
- `not_available`

A candidate declaration must resolve source identity, reuse authorization, static-SAED acquisition mode, material and composition identity, at least two independent acquisition IDs, raw/lossless representation, preserved original intensity, SHA-256 values, accelerating voltage, detector and pixel metadata, pattern centre, reciprocal calibration, a frozen reference protocol and analyzer-development non-use.

Even a complete response produces only `candidate_response_ready_for_bounded_saed_source_verification`. It does **not** authorize downloading files, running the analyzer, estimating centre or calibration, tuning parameters, indexing reflections, assigning phases or making performance claims.

## Scientific boundary

External validation still requires checksum-bound source acquisition, independent verification of sample/acquisition lineage, a completed `mca saed-validation-intake` manifest and a reference/analysis protocol frozen before analyzer execution. A structurally complete declaration is diagnostic evidence only.
