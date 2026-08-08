# SrTiO3 SAED Figure 1d identity-mapping stage

## Purpose

This case is the first authorized diffraction-pixel access for the SrTiO3 SAED source after the preceding provenance chain established:

- Zenodo record `10.5281/zenodo.20300700` and `SAED.zip` identity;
- three substantive TIFF members `23K.tif`, `91K.tif`, and `172K.tif`;
- 2048 × 2048, 64-bit floating-point TIFF storage with the first pixel strip at byte 272;
- pre-pixel `tifffile.py` serialization metadata;
- a separate 4D-STEM notebook that does not establish SAED preprocessing or calibration;
- final-publication evidence that `23K`, `91K`, and `172K` are diffraction-pattern temperatures and that the rendered Nature Figure 1d patterns carry a 0.1 Å⁻¹ scale bar.

The remaining question was whether the three source TIFF patterns can be independently linked to the three diffraction panels shown in Nature Figure 1d without using temperature order as the answer.

## Predeclaration

`evidence_contract.json` was committed before any source TIFF or publication-figure pixel access for this stage. It fixes the exact Zenodo archive URL, byte count and MD5, the only three TIFF members that may be decoded, the exact Nature Figure 1 PNG URL, byte ceilings, allowed transformations, and prohibited stronger analyses.

The contract commit precedes the decoder, tests, live workflow, pixel-source snapshot, and manual review in Git history.

This stage authorizes only:

- exact archive download and MD5 verification;
- decoding the three already verified TIFF pixel arrays;
- exact Figure 1 PNG download;
- source/figure hashes and array quality summaries;
- fixed display-only linear finite-minimum-to-finite-maximum previews;
- manual panel localization and descriptive identity review.

It does **not** authorize automatic registration, reciprocal-pixel-scale inference, pattern-centre inference, peak detection, phase indexing, analyzer execution, parameter tuning, 4D-STEM access, external-validation claims, or engineering decisions.

## Verified live pixel result

The predeclared live run succeeded.

- `SAED.zip`: 25,850,906 bytes, MD5 `0c830a9b276a491e91037872891cb440`, SHA-256 pinned in `verified_pixel_source_snapshot.json`;
- all three TIFFs remained exactly 2048 × 2048 `float64` with 4,194,304 finite pixels and zero non-finite pixels;
- exact member SHA-256 values are pinned for `23K`, `91K`, and `172K`;
- the exact Springer Nature Figure 1 `lw685` PNG was 129,447 bytes and decoded as 398 × 685 × 4 `uint8`; its SHA-256 is pinned;
- the source archive and raw TIFF payloads were not retained in the workflow output or Git.

The live workflow now requires those exact source/member/figure identities, so source drift fails before scientific review is reused.

## Manual identity review

The fixed source previews and pinned publication figure were reviewed manually under the predeclared descriptive-only rule. Manual panel boxes were recorded only as layout annotations, not registration or calibration results.

Observed evidence:

- all three source TIFF previews and all three Figure 1d diffraction panels share the same qualitative oblique two-axis reciprocal-lattice family and orientation;
- strong fundamental reflections and weaker interstitial reflections are qualitatively compatible with the publication's half-integer AFD superspot assignment;
- the low-temperature source preview shows stronger weak interstitial reflections than the high-temperature preview, qualitatively consistent with the publication's temperature-dependent diffraction behavior, but this is not used as an independent label decoder;
- the published `lw685` panels are only about 79 × 79 rendered pixels each and show a narrow cropped reciprocal-space region, whereas each source TIFF is 2048 × 2048;
- publication polarity, contrast, crop, resize, rasterization, and annotation transformations are not reconstructed in this stage;
- no unique label-independent defect or asymmetric reflection fingerprint is sufficiently resolved to prove that one particular source TIFF is the exact source of one particular rendered panel.

Therefore the closeout is deliberately conservative:

- overall source-pattern-family ↔ Figure 1d correspondence: **Diagnostic**;
- individual `23K.tif` ↔ left panel identity: **Inconclusive**;
- individual `91K.tif` ↔ middle panel identity: **Inconclusive**;
- individual `172K.tif` ↔ right panel identity: **Inconclusive**;
- temperature semantics: **Supported**;
- source-TIFF reciprocal calibration: **Inconclusive**;
- source-TIFF pattern centre: **Inconclusive**;
- SAED acquisition independence: **Inconclusive**;
- complete indexing truth: **Inconclusive**;
- external-validation readiness: **Inconclusive**.

The complete structured review is preserved in `manual_identity_review.json`.

## Why calibration is still not authorized

The public Figure 1 image is the Springer Nature `lw685` rendering. A displayed 0.1 Å⁻¹ scale bar is authoritative for the published panel, but the rendered image is too coarse to establish a defensible source-TIFF-to-panel transformation and uncertainty bound.

Automatic registration against this image would risk choosing a crop/transform after seeing the answer and would create false precision. The current evidence therefore does not justify reciprocal-pixel-scale inference.

## Next evidence requirement

Do **not** download more SAED source bytes or 4D-STEM arrays. The exact SAED source bytes are already available and verified.

Restart quantitative mapping only if an authoritative higher-resolution Figure 1d asset or explicit source-to-panel mapping becomes available. That evidence must permit a new predeclared registration/calibration contract before any automatic transform search or reciprocal-scale inference.

If no higher-resolution or explicit mapping evidence is available, this case remains a useful Diagnostic characterization benchmark rather than being forced into quantitative SAED external validation.

## Pixel inventory artifacts

A live workflow temporarily emits only:

- `pixel_access_inventory.json`;
- `source_23K_preview.png`;
- `source_91K_preview.png`;
- `source_172K_preview.png`;
- `publication_figure1.png`.

These are short-lived review artifacts and are not committed to Git. The immutable scientific record in Git is the evidence contract, exact source hashes/quality summary, and manual review decision.

## Reproduction

```powershell
python scripts/inspect_zenodo_srtio3_saed_figure1d_pixels.py `
  --config case_studies/zenodo_srtio3_saed_figure1d_identity_mapping/evidence_contract.json `
  --output outputs/zenodo_srtio3_saed_figure1d_identity_mapping
```

This command performs the specifically authorized pixel inventory. It is not a SAED analyzer run.

## Scientific closeout

**Evidence level: Diagnostic.**

The source data are real, provenance-bound, and physically plausible diffraction arrays, and they are qualitatively consistent with the published diffraction pattern family. The principal limitation is the low-resolution rendered publication image, which prevents label-independent individual panel identity and source-pixel calibration. The result is suitable for provenance/representation diagnostics, not quantitative analyzer validation, phase-indexing claims, or engineering decisions.
