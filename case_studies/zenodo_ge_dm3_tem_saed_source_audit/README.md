# Zenodo Ge native-DM3 TEM/SAED source audit

This case audits Zenodo record [`10.5281/zenodo.15082448`](https://doi.org/10.5281/zenodo.15082448), which deposits DigitalMicrograph (`.dm3`) TEM, HRTEM and selected-area electron diffraction files for laser-processed germanium nanostructures.

It is a high-value **cross-material static-SAED interoperability source**, not an in-domain cobalt-oxide validation cohort.

## Why this source is useful

The current official Zenodo API declares:

- a `CC BY 4.0` licence;
- three low-resolution TEM images and corresponding SAED patterns collected at the same locations;
- one low-resolution TEM location paired with a SAED pattern and a related HRTEM series;
- `.dm3` source files rather than only rendered figures;
- a JEOL JEM-2200FS TEM/EDS context;
- a source-reported quality correction: the scale bar in `w0 diff.dm3` is mislabeled as `10 nm`; the correct value is `5 1/nm`.

Earlier landing-page parsing did not expose the licence field; the official API snapshot supersedes that incomplete observation. Sample/acquisition IDs, pattern centres, reciprocal calibration provenance, acquisition independence and analyzer-development non-use remain unresolved.

## Verified live snapshot

The bounded live audit verified:

- archive bytes: `270,536,309`;
- archive MD5: `535f513e05d88a9b14a3bc6fde8ae3bd`;
- archive SHA-256: `c4c95688a6a61d1b32aaab26ecd54a7da4b2240862dc28ec58a6d430ef855186`;
- `92` regular archive members and `519,636,951` uncompressed bytes;
- `15` microscopy members with a big-endian DM3 version marker of `3`;
- the eight record-declared central TEM/SAED basenames at unique archive paths;
- `4` diffraction-name cues, `4` TEM-name cues, `6` HRTEM-name cues and `8` EDS-name cues.

ExifTool `12.76` returned `Unknown file type` for all 15 selected DM3 members. It exposed system-level file information but **zero microscopy-specific embedded metadata fields**. The audit therefore supports DM3 header identity and source-file identity, not successful extraction of instrument, acquisition, centre, camera-length, pixel-geometry or reciprocal-calibration tags.

## Bounded audit

The live workflow:

1. fetches the official Zenodo API record;
2. verifies record ID, DOI, title, publication state, resource type, `CC BY 4.0` licence, target filename and repository MD5;
3. downloads the single `.7z` archive into a transient directory;
4. verifies byte count, MD5 and SHA-256;
5. runs `7z t` and a fail-closed member inventory;
6. requires the record-declared central TEM/SAED DM3 basenames to occur exactly once;
7. extracts only bounded DM3 microscopy members into transient storage;
8. computes selected-member SHA-256 values and verifies each 12-byte header carries the DM3 version marker `3`;
9. retains ExifTool system output, errors and stderr without presenting unsupported embedded-metadata extraction as success;
10. deletes all source files before publishing metadata-only evidence.

The audit rejects unsafe or duplicate paths, encrypted or linked entries, excessive member counts, oversized members, excessive expanded size, excessive compression ratios and non-DM3 version markers.

## Run

Ubuntu/Debian requires `p7zip-full` and ExifTool:

```bash
sudo apt-get update
sudo apt-get install -y p7zip-full libimage-exiftool-perl

python scripts/run_zenodo_ge_dm3_tem_saed_audit.py \
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

The `CC BY 4.0` licence supports reuse with attribution, but it does not establish scientific comparability, acquisition independence, calibration traceability or external-validation readiness.

This case may support native-format identity, archive integrity, same-location pairing diagnostics and metadata-gap analysis. It does not support:

- cobalt-oxide TEM segmentation performance;
- calibrated SAED d-spacing accuracy;
- phase, reflection or zone-axis indexing;
- analyzer parameter tuning;
- model retraining;
- engineering decisions.

Any later analyzer run must use frozen parameters and remain a cross-material software diagnostic unless authoritative acquisition lineage, a DM3-capable metadata path, centre/calibration and reference metadata are resolved first.
