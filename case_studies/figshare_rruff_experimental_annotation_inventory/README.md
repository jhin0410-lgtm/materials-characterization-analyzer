# Figshare RRUFF experimental annotation inventory

## Purpose

This case is the first payload access in the Raman reference-validation path. It
reads only the exact publication-frozen `Experimental Data.json` identified by
the preceding metadata audit.

Pinned source identity:

- Figshare item `7427393`, version `2`;
- file ID `13752833`;
- file name `Experimental Data.json`;
- size `24,595` bytes;
- MD5 `5397f81312a454f6255b65a1d6d9529e`;
- dataset license metadata `CC BY 4.0`.

The file is parsed only after byte-count and MD5 verification.

## What is inventoried

The audit discovers RRUFF experimental records without depending on a specific
container layout and summarizes:

- RRUFF IDs and duplicate IDs;
- record-key consistency and required-field missingness;
- peak counts per record;
- overall annotated Raman-shift range;
- peak/intensity length consistency;
- `noise` and `start` numeric coverage/ranges.

The raw annotation payload is not written to Git or uploaded as a workflow
artifact. Only the structured inventory is retained.

## Scientific boundary

The published peak locations remain **Diagnostic reference annotations**. This
stage does not claim that they are authoritative physical truth because the
reviewed paper does not fully specify the independent manual/algorithmic peak
extraction procedure.

This stage also does not authorize:

- downloading any RRUFF source spectrum;
- reading the 16.9 MB computational Raman JSON;
- reading either CIF archive;
- selecting the final validation subset;
- using Materials Project matches or computed modes for selection;
- running the MCA Raman analyzer;
- tuning baseline, smoothing, prominence or matching tolerance;
- fitting/training models;
- mineral or vibrational-mode claims;
- external-validation or engineering-readiness claims.

## Why subset selection waits

Once the annotation inventory is known, the next scientific risk is post-hoc
selection. The RRUFF IDs, inclusion/exclusion rules and peak-matching tolerance
must therefore be frozen in a separate target-blind contract **before** any
source spectrum or corresponding MCA peak output is viewed.

The first benchmark should use a small representative subset rather than the
entire reference collection. Selection should be justified from annotation and
source metadata, not from MCA performance.

## Reproduction

```powershell
python scripts/inventory_figshare_rruff_experimental_annotations.py `
  --config case_studies/figshare_rruff_experimental_annotation_inventory/evidence_contract.json `
  --output outputs/figshare_rruff_experimental_annotation_inventory/annotation_inventory.json
```

This command reads exactly one 24,595-byte Figshare file and no Raman source
spectrum.
