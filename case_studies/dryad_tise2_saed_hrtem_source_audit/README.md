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

## Bounded live audit

The workflow:

1. starts from Dryad file ID `4808550`;
2. follows the official file → version → dataset API links and verifies the DOI,
   title, licence and version file inventory;
3. streams `Data_TiSe2.zip` into transient storage;
4. verifies the Dryad-declared byte count and any upstream digest exposed by the
   API, while recording an observed MD5 and SHA-256;
5. runs a fail-closed ZIP CRC and path-safety audit;
6. inventories all regular members without exporting image pixels;
7. reads bounded `ReadMe`/metadata text to classify supplementary folders;
8. inspects only a bounded sample of experimental TIFF headers without loading
   or exporting pixel arrays;
9. publishes metadata-only evidence and deletes the archive and extracted TIFF
   samples before artifact upload.

## Run

```bash
python -m pip install pillow
python scripts/audit_dryad_tise2_saed_hrtem.py \
  --config case_studies/dryad_tise2_saed_hrtem_source_audit/case_config.json \
  --output outputs/dryad_tise2_saed_hrtem_source_audit
```

The output directory must be absent or empty.

## Scientific boundary

The dataset is TiSe2, not cobalt oxide. Dryad CC0 publication supports reuse,
but does not establish detector-native intensity preservation, sample or
acquisition independence, camera length, pattern centre, detector geometry or
reciprocal-space calibration.

This case may support archive interoperability, TIFF-header diagnostics and
experimental-versus-simulated separation. It does not support calibrated
d-spacing validation, phase indexing, model tuning, retraining, cobalt-oxide
segmentation performance or engineering decisions.
