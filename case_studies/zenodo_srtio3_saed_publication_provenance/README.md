# SrTiO3 SAED final-publication provenance audit

## Purpose

This case uses the final 2026 Nature article to resolve a specific provenance gap left by the earlier Zenodo, TIFF-header, pre-pixel metadata, and notebook audits for Zenodo record `10.5281/zenodo.20300700`.

The earlier source audits established three substantive TIFF members named `23K.tif`, `91K.tif`, and `172K.tif`, but correctly did not infer that `K` meant temperature. The accompanying `Kikuchi_COM.ipynb` did not mention SAED or those three labels and belongs to the separate 4D-STEM workflow.

The final article, `10.1038/s41586-026-10823-x`, now provides authoritative text that can address the temperature semantics without reading any diffraction pixel.

## Publication evidence

The final Nature article states that Figure 1d contains electron diffraction patterns collected at 23 K, 91 K, and 172 K. It also reports a 0.1 inverse-angstrom scale bar for those displayed patterns and identifies AFD superspots at half-integer positions. Extended Data Figure 2 contains electron diffraction patterns from 23 to 215 K.

Most importantly for source binding, the article's Data availability section points electron microscopy data corresponding to the figures to the same Zenodo DOI, `10.5281/zenodo.20300700`.

This allows the repository's `23K/91K/172K` labels to be interpreted as temperature labels with **Supported** evidence. It does not yet prove that each source TIFF is byte-for-byte the exact corresponding published panel.

## What this audit does

The audit:

1. rechecks the already pinned Zenodo/TIFF/pre-pixel/notebook evidence files;
2. downloads only the final article HTML from the pinned Nature URL under a 5 MB ceiling;
3. extracts visible text while ignoring script/style/noscript content;
4. verifies the final DOI/title context, the three temperature claims, the published reciprocal-space scale-bar statement, the AFD superspot assignment, the extended temperature-series statement, and the exact Zenodo DOI link;
5. records only hashes, bounded source metadata, supported facts, evidence classifications, and readiness flags;
6. retains neither publication HTML nor normalized publication text.

No Zenodo source archive, TIFF pixel, 4D-STEM array, or published figure image is downloaded by this audit.

## Scientific interpretation

After this audit:

- final publication identity: **Supported**;
- publication-to-Zenodo data binding: **Supported**;
- `23K/91K/172K` temperature semantics: **Supported**;
- published Figure 1d reciprocal-space scale bar: **Supported for the displayed figure**;
- source-author AFD superspot assignment: **Diagnostic reference evidence**;
- exact source-TIFF-to-figure-panel identity: **Diagnostic**;
- source-TIFF reciprocal calibration: **Inconclusive**;
- source-TIFF pattern centre: **Inconclusive**;
- SAED acquisition independence: **Inconclusive**;
- detector-native intensity provenance: **Inconclusive**;
- complete phase/reflection truth: **Inconclusive**;
- external-validation readiness: **Inconclusive**.

The 0.1 inverse-angstrom scale bar must not be silently copied into a pixel-to-reciprocal-space conversion for the raw TIFF. The published figure may be cropped, resized, rendered, contrast-adjusted, or otherwise transformed relative to the source TIFF.

Likewise, the article's statement that the sample location is realigned to the same region at each temperature step occurs in the 4D-STEM methods. It is not used to claim that the three SAED TIFFs are paired, repeated, or statistically independent acquisitions.

## Next bounded evidence action

The next useful action is a **separately predeclared source-TIFF-to-published-Figure-1d mapping audit**. That later contract may authorize only the minimum source TIFF and published figure pixels required to determine:

- whether each TIFF visually/structurally corresponds to the stated Figure 1d temperature panel;
- whether a reproducible figure-to-source scale transformation can be established;
- whether a source-TIFF reciprocal-space pixel scale can be supported without tuning an analyzer on the same patterns.

Until that separate contract exists, source TIFF pixel access and published figure-image access remain unauthorized.

## Reproduction

```powershell
python scripts/audit_zenodo_srtio3_saed_publication_provenance.py `
  --config case_studies/zenodo_srtio3_saed_publication_provenance/case_config.json `
  --output outputs/zenodo_srtio3_saed_publication_provenance/publication_provenance_snapshot.json
```

## Sources

- Final article: https://doi.org/10.1038/s41586-026-10823-x
- Source dataset: https://doi.org/10.5281/zenodo.20300700

## Scientific closeout

**Evidence level: Diagnostic.**

The temperature-label ambiguity is resolved. The strongest remaining blocker is quantitative source-TIFF calibration and exact source-to-published-panel identity. The next step is therefore not analyzer execution or unrestricted SAED pixel analysis; it is a narrowly predeclared figure/source mapping audit.
