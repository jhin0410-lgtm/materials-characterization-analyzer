# Zenodo Ge native-DM3 TEM/SAED source audit

This case audits Zenodo record [`10.5281/zenodo.15082448`](https://doi.org/10.5281/zenodo.15082448), which deposits native DigitalMicrograph (`.dm3`) TEM, HRTEM and selected-area electron diffraction files for laser-processed germanium nanostructures.

It is a high-value **cross-material static-SAED interoperability source**, not an in-domain cobalt-oxide validation cohort.

## Why this source is useful

The public record explicitly declares:

- three low-resolution TEM images and corresponding SAED patterns collected at the same locations;
- one low-resolution TEM location paired with a SAED pattern and a related HRTEM series;
- native `.dm3` files rather than only rendered figures;
- a JEOL JEM-2200FS TEM/EDS context;
- a source-reported quality correction: the scale bar in `w0 diff.dm3` is mislabeled as `10 nm`; the correct value is `5 1/nm`.

The record does **not** expose a licence identifier. Sample/acquisition IDs, pattern centres, reciprocal calibration provenance, acquisition independence and analyzer-development non-use also remain unresolved.

## Bounded audit

The live workflow:

1. fetches the official Zenodo API record;
2. verifies record ID, DOI, title, publication state, resource type, missing licence state, target filename and repository MD5;
3. downloads the single `270.5 MB` `.7z` archive into a transient directory;
4. verifies the observed byte count, MD5 and SHA-256;
5. runs `7z t` and a fail-closed member inventory;
6. requires the record-declared central TEM/SAED DM3 basenames to occur exactly once;
7. extracts only bounded DM3 microscopy members into transient storage;
8. computes selected-member SHA-256 values and records metadata exposed by ExifTool;
9. deletes all source files before publishing metadata-only evidence.

The audit rejects unsafe or duplicate paths, encrypted or linked entries, excessive member counts, oversized members, excessive expanded size and excessive compression ratios.

## Run

Ubuntu/Debian requires `p7zip-full` and ExifTool:

```bash
sudo apt-get update
sudo apt-get install -y p7zip-full libimage-exiftool-perl

python scripts/audit_zenodo_ge_dm3_tem_saed.py \
  --config case_studies/zenodo_ge_dm3_tem_saed_source_audit/case_config.json \
  --output outputs/zenodo_ge_dm3_tem_saed_source_audit
```

The output directory must be absent or empty.

## Expected evidence

- `zenodo_ge_dm3_tem_saed_audit_summary.json`
- `zenodo_ge_dm3_tem_saed_member_inventory.csv`
- `zenodo_ge_dm3_selected_member_identity.csv`
- `zenodo_ge_dm3_selected_metadata.json`
- `zenodo_ge_dm3_tem_saed_audit_report.md`
- `zenodo_ge_dm3_tem_saed_audit_manifest.json`

No `.7z`, `.dm3`, raster image or pixel array is retained in the output.

## Scientific boundary

This case may support native-format parsing, source identity, same-location pairing diagnostics and metadata-gap analysis. It does not support:

- cobalt-oxide TEM segmentation performance;
- calibrated SAED d-spacing accuracy;
- phase, reflection or zone-axis indexing;
- analyzer parameter tuning;
- model retraining;
- engineering decisions.

Any later analyzer run must use frozen parameters and remain a cross-material software diagnostic unless authoritative licence, acquisition lineage, centre/calibration and reference metadata are resolved first.
