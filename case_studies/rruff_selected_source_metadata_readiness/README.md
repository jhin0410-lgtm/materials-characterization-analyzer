# Selected RRUFF source metadata readiness

## Purpose

This case audits only the public RRUFF record pages for the 10 IDs frozen by the
target-blind selection. It asks whether Raman source data and acquisition context
are discoverable before any spectrum payload is downloaded.

The selected IDs are fixed upstream and cannot be changed here:

`R060247`, `R040073`, `R110214`, `R070417`, `R040078`, `R070307`,
`R040006`, `X050046`, `R060959`, `R040040`.

## Why page metadata comes first

A RRUFF mineral ID can expose multiple Raman records: oriented measurements,
unoriented broad scans, different wavelengths, and raw or processed data. The
published Figshare annotation contains one `RRUFF_id` plus peak annotations, but
does not uniquely identify which downloadable RRUFF spectrum generated those
annotations.

Therefore an ID-level page match is not enough to claim exact source identity.
This stage inventories only visible record-page evidence such as:

- Raman section presence;
- broad-scan section presence;
- visible processed/raw download labels;
- visible laser wavelengths and instrument-setting text;
- oriented/unoriented wording;
- response hash and final record-page URL.

## Scientific boundary

No Raman data download link is followed. Spectrum payload bytes read are zero.
The audit does not:

- choose one spectrum among multiple candidates;
- download raw or processed Raman arrays;
- infer the exact spectrum underlying the frozen Figshare peak annotations;
- replace any target-blind selected ID;
- run MCA Raman;
- tune baseline, smoothing, prominence or matching tolerance;
- claim authoritative peak truth, external validation or engineering readiness.

RRUFF project documentation describes the data as free/open access and available
for download, but the source review still lacks a formal machine-readable dataset
license that clearly authorizes repository redistribution. Raw RRUFF spectra are
therefore not committed or redistributed by this case.

## Next step

If selected pages confirm Raman availability, predeclare a separate
annotation-to-source binding rule before downloading any spectrum. The mapping
rule must preserve ambiguity when an ID exposes multiple orientations or
wavelengths and may use only source metadata plus the already frozen published
annotation fields. MCA output must remain unavailable during source binding.

Only after exact source identities are defensible should the matching protocol
and tolerance/sensitivity range be frozen.

## Reproduction

```powershell
python scripts/audit_rruff_selected_source_metadata.py `
  --config case_studies/rruff_selected_source_metadata_readiness/evidence_contract.json `
  --output outputs/rruff_selected_source_metadata_readiness/source_metadata_snapshot.json
```

The command requests HTML record pages only.
