# SAED Public Candidate Registry

This case is a dated, fail-closed triage of public diffraction repositories for issue #36. It complements the detailed DataCORE candidate dossier in `case_studies/saed_external_validation_candidate_registry/`; it does not replace that source-specific audit.

## Command

```bash
mca saed-candidates \
  --config case_studies/saed_public_candidate_registry/case_config.json \
  --output outputs/saed_public_candidate_registry
```

The command reads the pinned JSON snapshot and writes:

- `saed_candidate_inventory.csv`
- `saed_candidate_summary.json`
- `saed_candidate_report.md`
- `saed_source_audit_protocol.json`
- `saed_candidate_artifact_manifest.json`

It performs no network requests and does not download, inspect, or copy source arrays.

## Current result

No candidate is ready for predeclared static-SAED evaluation.

The highest-priority records are the BIR-MicroED static selected-area diffraction deposits at 200 and 300 keV. They expose large MRC or TVIPS archives with archive-level checksums and compound/voltage/temperature/series naming. The public record snapshot does not yet bind immutable sample identity, detector and pixel metadata, pattern centre, reciprocal calibration, reuse terms, or analyzer-development non-use. Their size also requires a bounded subset plan before download.

The Mendeley lunar-mineral record states that its TEM file contains original SAED patterns and is CC BY 4.0, but the public landing page does not expose the exact member inventory, checksums, acquisition identities, detector, centre, or reciprocal calibration.

The L-histidine and carmine Zenodo records contain useful raw continuous-rotation 3DED data and instrument/log metadata. They are retained as acquisition-mode and format diagnostics, not as static-SAED performance evidence.

The DataCORE chromium-telluride candidate remains the strongest material-aware static-SAED dossier because it reports original DM4/TIFF patterns, two zone axes, publication-level indexing, 120 kV microscopy, and CC BY 4.0. Its archive is still unavailable as binary ZIP bytes, so the existing source audit remains blocked.

FINDS remains a software-integration control rather than raw calibrated validation data.

## Status meanings

- `ready_for_dedicated_saed_source_audit`: metadata is sufficient to begin a bounded checksum-bound source audit, not analyzer evaluation.
- `calibration_or_center_resolution_required`: the source is static and raw/lossless, but centre, reciprocal calibration, detector, or lineage evidence is unresolved.
- `metadata_or_file_inventory_resolution_required`: exact files, checksums, sample/acquisition identities, or related metadata are unresolved.
- `diagnostic_3ded_or_microed_mode_shift`: useful raw diffraction data were collected under continuous-rotation or other non-static acquisition.
- `source_unavailable_or_archived`: binary source data cannot currently be retrieved.
- `excluded_rendered_or_software_example`: the record is software, documentation, or rendered imagery rather than raw/lossless diffraction evidence.

## Scientific boundary

A registry recommendation is only a source-acquisition recommendation. It does not authorize downloading an unbounded multi-gigabyte archive, selecting frames after viewing analyzer output, estimating centre or calibration from detections, treating 3DED frames as static SAED, or making phase, reflection, zone-axis, d-spacing, performance, or engineering claims.

Before analyzer execution, a candidate must pass the existing `mca saed-validation-intake` contract using a checksum-bound local subset with at least two independent patterns or acquisitions and a frozen analysis/reference protocol.
