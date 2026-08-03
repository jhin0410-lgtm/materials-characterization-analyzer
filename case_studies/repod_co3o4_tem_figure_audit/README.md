# RepOD Co3O4 TEM Figure Audit

This case study audits RepOD dataset `10.18150/SAU9QX`, which accompanies the paper *Hierarchical Co3O4 anode for high-performance Na-ion battery*.

The record is exact-material and CC0, but it deposits six publication-level JPEG figures rather than individual TEM detector files or demonstrably lossless micrographs. The two files whose official descriptions mention TEM are multi-panel figures:

- `Figure_2.jpg`: SEM panels `(a-c)`, TEM panels `(d-f)`, and SEM panels `(g-i)` in one 1430 x 1117 RGB JPEG.
- `Figure_6.jpg`: electrochemical, ToF-SIMS, one TEM panel, and elemental-map panels in one 925 x 614 RGB JPEG.

## Reproducibility contract

The audit:

1. retrieves official Dataverse version-1.0 metadata;
2. verifies the exact six-file inventory, immutable file IDs, byte counts, MD5 values, MIME types, public access and per-file CC0 licence;
3. downloads only `Figure_2.jpg` and `Figure_6.jpg`;
4. verifies their repository-declared bytes and MD5 values;
5. checks JPEG format, RGB mode, dimensions, frame count and DPI;
6. confirms from the official descriptions that each is a composite publication figure;
7. deletes downloaded source figures in a `finally` cleanup path;
8. verifies the registry classifies the record as a rendered-representation exclusion;
9. uploads metadata-only evidence.

## Scientific boundary

The audit does not crop panels, infer scale calibration, recover detector intensities, create labels, run segmentation, retrain a model or estimate performance. JPEG figure panels may be useful for visual literature review, but they cannot establish an independent raw/lossless Co3O4 TEM validation cohort.

Reconsider the record only if the authors deposit checksum-bound individual TEM micrographs or detector files with sample/acquisition lineage and target-model non-use evidence.
