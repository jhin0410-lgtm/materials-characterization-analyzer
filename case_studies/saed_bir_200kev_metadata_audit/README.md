# BIR-MicroED 200 keV Metadata Audit

This case resolves the next source-triage step from the SAED public candidate registry without downloading the 36.9 GB diffraction corpus.

## Scope

The audit consumes the official Zenodo record JSON for `10.5281/zenodo.10999587` and verifies the four archive names and archive-level MD5 values against a pinned local contract. It combines those record facts with acquisition facts explicitly reported by the associated publication `10.1107/S2052252524012132`.

Run:

```bash
curl --fail --location --retry 5 \
  https://zenodo.org/api/records/10999587 \
  --output /tmp/zenodo-10999587.json

mca saed-bir-metadata-audit \
  --config case_studies/saed_bir_200kev_metadata_audit/case_config.json \
  --record-json /tmp/zenodo-10999587.json \
  --output outputs/saed_bir_200kev_metadata_audit
```

The source JSON is an input only. The workflow deletes it before artifact upload.

## Confirmed source facts

The official record exposes four checksum-bound ZIP archives containing MRC diffraction series for AVAAGA, thiostrepton, and proteinase K at 200 keV. The associated publication reports:

- Talos F200C TEM;
- DE Apollo direct electron detector at 60 Hz;
- integration of 30 native frames per released frame;
- effective 2 Hz output;
- spatial binning to 2048 × 2048 MRC arrays;
- parallel-beam microprobe diffraction;
- 100 µm selected-area aperture, projected to approximately 2 µm at the specimen;
- approximately 5 µm illuminated area;
- no stage rotation for the stationary diffraction series;
- 5 minute stationary series for small molecules and 2.5 minute series for AVAAGA, thiostrepton, and proteinase K.

These are publication-level acquisition facts. They are not yet bound to individual archive members.

## Current decision

The candidate remains **not ready** for bounded archive download or SAED validation intake. The live record explicitly declares `CC BY 4.0`, so reuse authorization is supported and is no longer a blocker.

The released MRC arrays are acquisition-derived outputs after native-frame integration and spatial binning. The record does not establish:

- native 60 Hz detector-frame availability;
- archive member inventory or independent series count;
- immutable crystal/sample and acquisition identifiers;
- direct-beam position or a reproducible pattern-centre procedure;
- camera length or another traceable reciprocal calibration for the released arrays;
- detector pixel geometry and coordinate transformations after binning;
- non-use of the proposed series during analyzer development or parameter selection.

The first archive proposed for a later bounded audit is `AVAAGA_200kV_293K.zip` because it is the smallest checksum-bound archive in the record. This is a planning result, not download authorization.

## Outputs

- `bir_archive_inventory.csv`
- `bir_metadata_gap_matrix.csv`
- `bir_metadata_audit_summary.json`
- `bir_bounded_subset_plan.json`
- `bir_author_metadata_request.md`
- `bir_metadata_audit_report.md`
- `bir_metadata_audit_manifest.json`

No ZIP, MRC, TVIPS, TIFF, or detector arrays are persisted.

## Scientific boundary

This audit supports source identity and metadata-gap resolution only. It does not inspect ZIP members, decode MRC arrays, estimate the pattern centre, infer reciprocal calibration, execute the SAED analyzer, select parameters, index reflections or phases, validate `d_nm`, or support engineering release.
