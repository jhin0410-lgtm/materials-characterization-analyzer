# TEM independent validation source request

This case study converts the checksum-bound public TEM candidate registry into a send-ready, fail-closed request and response-assessment package for an independent cobalt-oxide TEM/HRTEM source.

## Why this exists

The current registry contains 11 assessed candidates and no source that is ready for independent in-domain external validation. Existing candidates remain blocked by one or more of the following: target-source reuse, wrong microscopy modality, rendered publication figures, processed single-particle data, missing immutable lineage, missing calibration, creator overlap, missing non-use evidence, or absent independent labels.

Searching indefinitely or retraining the U-Net does not resolve those evidence gaps. The narrow next action is to request authoritative source metadata and referrals using an explicit machine-readable contract.

## Build the correspondence package

First reproduce the registry:

```bash
mca tem-candidates \
  --config case_studies/tem_external_validation_candidate_registry/case_config.json \
  --output outputs/tem_external_validation_candidate_registry
```

Then build the request:

```bash
python scripts/tem_independent_validation_source_request.py build \
  --registry-output outputs/tem_external_validation_candidate_registry \
  --output outputs/tem_independent_validation_source_request
```

Generated files:

- `tem_independent_source_request.json`
- `tem_independent_source_author_response_template.json`
- `tem_independent_source_correspondence.md`
- `tem_independent_source_request_summary.json`
- `tem_independent_source_request_manifest.json`

The Markdown file contains a send-ready subject and message. The software does not send the message and does not hard-code private recipient information.

## Assess a completed response

```bash
python scripts/tem_independent_validation_source_request.py assess \
  --registry-output outputs/tem_external_validation_candidate_registry \
  --response completed_author_response.json \
  --output outputs/tem_independent_validation_source_response
```

A response may declare:

- `candidate_available`
- `referral_only`
- `not_available`

A candidate response must resolve source identity, reuse authorization, pure cobalt-oxide scope, TEM/HRTEM modality, raw/lossless representation, original detector intensity, at least two independent samples and acquisitions, source-assigned lineage, SHA-256 checksums, pixel calibration, creator disjointness, target-model non-use, and cross-dataset lineage independence.

Even a complete response produces only `candidate_response_ready_for_bounded_source_verification`. It does **not** authorize downloading files, running inference, retraining, creating performance claims, or declaring the TEM intake ready. Source bytes, image semantics, calibration, content disjointness, and labels must still be independently verified.

## Scientific boundary

Existing labels are requested but are not treated as verified merely because they are declared. External validation still requires checksum-bound source acquisition, content-overlap clearance, a separate TEM intake manifest, frozen evaluation rules, and independent blinded labels with adjudication.
