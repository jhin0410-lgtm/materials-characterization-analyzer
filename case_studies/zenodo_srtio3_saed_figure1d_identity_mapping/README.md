# SrTiO3 SAED Figure 1d identity-mapping stage

## Purpose

This case is the first authorized diffraction-pixel access for the SrTiO3 SAED source after the preceding provenance chain established:

- Zenodo record `10.5281/zenodo.20300700` and `SAED.zip` identity;
- three substantive TIFF members `23K.tif`, `91K.tif`, and `172K.tif`;
- 2048 × 2048, 64-bit floating-point TIFF storage with the first pixel strip at byte 272;
- pre-pixel `tifffile.py` serialization metadata;
- a separate 4D-STEM notebook that does not establish SAED preprocessing or calibration;
- final-publication evidence that `23K`, `91K`, and `172K` are diffraction-pattern temperatures and that the rendered Nature Figure 1d patterns carry a 0.1 Å⁻¹ scale bar.

The remaining question is whether the three source TIFF patterns actually correspond to the three diffraction panels shown in Nature Figure 1d. Temperature order alone is not sufficient evidence of identity.

## Predeclaration

`evidence_contract.json` was committed before any source TIFF or publication-figure pixel access for this stage. It fixes the exact Zenodo archive URL, byte count and MD5, the only three TIFF members that may be decoded, the exact Nature Figure 1 PNG URL, byte ceilings, allowed transformations, and prohibited stronger analyses.

This stage authorizes only:

- exact archive download and MD5 verification;
- decoding the three already verified TIFF pixel arrays;
- exact Figure 1 PNG download;
- source/figure hashes and array quality summaries;
- fixed display-only linear finite-minimum-to-finite-maximum previews;
- manual panel localization and descriptive identity review.

It does **not** authorize automatic registration, reciprocal-pixel-scale inference, pattern-centre inference, peak detection, phase indexing, analyzer execution, parameter tuning, 4D-STEM access, external-validation claims, or engineering decisions.

## Why calibration is not included yet

The public Figure 1 image used here is the Springer Nature `lw685` rendering. A displayed 0.1 Å⁻¹ scale bar is authoritative for the published panel, but a rendered low-resolution figure may be cropped, resized, rasterized, or otherwise transformed relative to the 2048 × 2048 source TIFF.

Therefore source-to-figure identity is evaluated first. Reciprocal-space calibration requires a later predeclared contract only if the identity relationship and rendering geometry are strong enough to support a defensible transformation and uncertainty bound.

## Pixel inventory output

The first live pixel run produces only temporary workflow artifacts:

- `pixel_access_inventory.json`;
- `source_23K_preview.png`;
- `source_91K_preview.png`;
- `source_172K_preview.png`;
- `publication_figure1.png`.

The source ZIP and raw TIFF payloads are not written to the output directory. These display artifacts are for bounded scientific review and must not be committed to Git.

The inventory explicitly records that identity mapping, automatic registration, reciprocal calibration, pattern-centre inference, peak detection, indexing, analyzer execution, and tuning have not yet been performed.

## Interpretation rules

A panel mapping can be promoted only from diffraction-pattern geometry, not from left-to-right temperature order alone. If the low-resolution publication rendering does not permit a robust correspondence, the correct closeout is `Inconclusive` and the next evidence requirement is a higher-resolution authoritative publication asset or author-provided mapping information.

Even a convincing source-to-panel identity does not by itself establish:

- reciprocal-space source-pixel calibration;
- pattern centre;
- independent acquisition count;
- detector-native intensity preservation;
- a complete phase/reflection truth set;
- external-validation readiness.

## Reproduction

After checking out the branch or merged main:

```powershell
python scripts/inspect_zenodo_srtio3_saed_figure1d_pixels.py `
  --config case_studies/zenodo_srtio3_saed_figure1d_identity_mapping/evidence_contract.json `
  --output outputs/zenodo_srtio3_saed_figure1d_identity_mapping
```

This command performs the specifically authorized pixel inventory. It is not a SAED analyzer run.
