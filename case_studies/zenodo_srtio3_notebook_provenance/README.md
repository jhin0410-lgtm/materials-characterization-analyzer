# SrTiO3 notebook provenance audit

## Purpose

Audit the verified 1.71 MB `Kikuchi_COM.ipynb` source for textual evidence that can
clarify the SrTiO3 SAED representation before any diffraction pixels are opened.

The notebook is downloaded only after exact Zenodo byte-count/MD5 binding. The full
notebook is not retained in audit output.

## Search scope

Only markdown and code-cell **source text** is searched. Notebook outputs are ignored.
The predeclared search categories cover:

- SAED and `23K` / `91K` / `172K` identity terms;
- TIFF/export representation terms;
- preprocessing terms;
- calibration / camera-length / reciprocal-scale / centre terms;
- diffraction / Kikuchi / centre-of-mass context.

The audit writes hit counts and short bounded source-line excerpts with cell hashes.

## Interpretation boundary

A keyword hit is a Diagnostic lead, not proof that a preprocessing or calibration
step applies to the three SAED TIFF files. An absent hit is likewise not evidence
that the underlying experiment lacked that property.

The notebook cannot authorize SAED pixel access, 4D-STEM downloads, phase indexing,
parameter tuning or external-validation claims by itself.
