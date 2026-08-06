# Dryad TiSe2 SAED/HRTEM source audit

This case audits Dryad dataset `10.5061/dryad.6djh9w1hw`, published for
*Revisiting the charge-density-wave superlattice of 1T-TiSe2*.

The source is useful because its repository README explicitly separates:

- `Fig2_Data`: experimental selected-area electron diffraction along `[1-10]`
  and `[001]`;
- `Fig3_Data`: simulated diffraction based on the Di Salvo structure;
- `Fig4_Data`: simulated diffraction for the proposed displacement model;
- supplementary folders containing additional diffraction, line-profile,
  real-space and DFT products.

That separation is scientifically important: simulated patterns must never be
pooled with experimental diffraction as independent ground truth.

## Current access result

The official Dryad API successfully binds file ID `4808550` to the expected
source version, dataset DOI, title, CC0 licence, filename and declared size of
`1,894,856,343` bytes.

However, three anonymous download forms tested from a GitHub-hosted runner did
not return those archive bytes:

- the API-declared endpoint required authorization;
- the legacy public file-stream endpoint rejected the automated runner;
- the `/stash/downloads/file_stream/` endpoint returned a small HTML response
  rather than the ZIP.

The audit therefore records **Supported source metadata**, **Unsupported
anonymous automated download in the current runner**, and **Inconclusive archive
integrity/member content**. It does not interpret HTML or access-control
responses as microscopy data and does not replay cookies or bypass access
controls.

## Bounded audit behavior

The workflow:

1. starts from Dryad file ID `4808550`;
2. follows the official file → version → dataset API links and verifies the DOI,
   title, licence and version file inventory;
3. attempts the pinned anonymous public stream;
4. when the declared ZIP is unavailable, probes the API and two public endpoint
   forms with a maximum 64 KiB response sample each;
5. records only status, trusted final host/path, content type, length and sample
   SHA-256—not response bodies;
6. publishes metadata-only access evidence;
7. runs the ZIP/member/TIFF-header audit only after the exact declared archive
   bytes become available.

## Run

```bash
python -m pip install pillow
python scripts/run_dryad_tise2_saed_hrtem_audit.py \
  --config case_studies/dryad_tise2_saed_hrtem_source_audit/case_config.json \
  --output outputs/dryad_tise2_saed_hrtem_source_audit
```

The output directory must be absent or empty.

## Scientific boundary

The dataset is TiSe2, not cobalt oxide. Dryad CC0 publication supports reuse,
but does not establish detector-native intensity preservation, sample or
acquisition independence, camera length, pattern centre, detector geometry or
reciprocal-space calibration.

Until a checksum-verifiable copy of `Data_TiSe2.zip` is obtained through an
authorized manual or repository-supported path, this case does not support
archive interoperability, experimental-versus-simulated member verification,
TIFF-header diagnostics, calibrated d-spacing validation, phase indexing,
model tuning, retraining, cobalt-oxide segmentation performance or engineering
decisions.
