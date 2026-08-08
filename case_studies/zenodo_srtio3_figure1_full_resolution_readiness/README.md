# SrTiO3 Figure 1 full-resolution readiness probe

## Purpose

The preceding Figure 1d identity-mapping case closed at **Diagnostic** because the pinned Springer Nature `lw685` rendering is only 685 × 398 pixels and each diffraction panel is roughly 79 × 79 rendered pixels. That resolution is sufficient to establish qualitative diffraction-family consistency, but not label-independent individual TIFF-to-panel identity or source-TIFF reciprocal calibration.

The next evidence requirement is therefore an authoritative higher-resolution Figure 1d asset or explicit source-to-panel mapping.

Springer Nature commonly exposes a `/full/` media path in addition to `lw685`, but the existence and dimensions of the exact SrTiO3 Figure 1 `/full/` candidate are not assumed. This case probes only the PNG file header to determine whether such an asset exists and is materially larger.

## Predeclaration

`evidence_contract.json` is committed before the candidate full-size asset is contacted. The contract fixes:

- the exact final-publication DOI and Figure 1 identity;
- the already verified `lw685` URL, raster shape, and SHA-256;
- the exact candidate `/full/` URL;
- a strict HTTP Range request for bytes 0 through 32 only;
- an expected HTTP 206 response;
- PNG signature and IHDR-only parsing;
- zero authorization for full-image download or pixel decoding.

If the server ignores Range and returns HTTP 200, the response body must not be read and no full-download fallback is allowed.

## Why 33 bytes are sufficient

A PNG begins with an 8-byte signature followed by the IHDR chunk. Bytes 0–32 contain:

- the PNG signature;
- the first chunk length and `IHDR` type;
- image width and height;
- bit depth, color type, compression, filter, and interlace flags;
- the IHDR CRC bytes.

No image pixel raster is needed to decide whether the candidate has greater dimensions than the verified 685 × 398 rendering.

## Decision rule

The candidate is considered materially higher resolution only when **both** width and height exceed the `lw685` dimensions.

A successful header probe does not authorize the full image. It only justifies a separate, later contract that can decide whether downloading the higher-resolution figure is worth the scientific cost and how identity review will be performed without post-hoc tuning.

A failed probe, HTTP 200 response, non-PNG response, or non-improved dimensions closes this candidate without fallback.

## Scientific boundaries

This readiness probe does not:

- download the full publication image;
- decode any publication pixel raster;
- access SAED TIFFs or 4D-STEM data;
- register images;
- infer reciprocal-space scale or pattern centre;
- detect peaks or index phases;
- execute or tune an analyzer;
- establish external-validation or engineering evidence.

## Reproduction

```powershell
python scripts/probe_srtio3_figure1_full_resolution.py `
  --config case_studies/zenodo_srtio3_figure1_full_resolution_readiness/evidence_contract.json `
  --output outputs/zenodo_srtio3_figure1_full_resolution_readiness/full_resolution_readiness.json
```

The command reads at most 33 response-body bytes when the server honors the predeclared Range request.
