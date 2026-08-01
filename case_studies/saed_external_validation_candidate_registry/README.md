# SAED External-Validation Candidate Registry

This directory records source-backed candidates for future external validation of the SAED analyzer. It is a search and intake artifact, not a validated dataset and not an analysis result.

## Current decision

The best current candidate is Indiana University DataCORE dataset `10.5967/ct7n-8275`, which reports chromium-telluride SAED patterns along `[001]` and `[112]` zone axes and supplies TIFF images and original Gatan DM4 files under CC BY 4.0.

The related publication adds two useful facts: TEM was performed using a 120 kV JEOL JEM 1400plus, and the authors state that the main diffraction spots in both patterns can be indexed by `Cr1+deltaTe2` with `delta` approximately `0.5`. These are source claims, not analyzer ground truth, and they must not be used for parameter tuning.

The candidate is **not yet eligible for external validation**. The `Diffraction_Pattern.zip` file is currently archived. Its official file-set page exposes a retrieval form, and an anonymous request was attempted on 2026-08-01 through the published endpoint. The endpoint returned HTTP 200 but resolved back to the file-set page; a separate queue-acceptance message was not verified, and the direct download still returned HTML rather than a ZIP immediately afterward.

Because the archive is unavailable, camera length or a traceable camera constant, detector metadata, immutable sample/acquisition identities, pattern-center provenance, acquisition independence, archive/member checksums, and the relationship between each DM4 and TIFF representation remain unresolved.

The existing FINDS SAED case remains useful for real-image software integration and sensitivity testing, but its lossy JPEG and unresolved material/acquisition provenance do not satisfy the raw calibrated validation contract.

## Automated source audit

Run:

```bash
python scripts/audit_datacore_saed_candidate.py \
  --source-url "https://datacore.iu.edu/downloads/37720f05n?locale=en" \
  --output outputs/datacore-saed-source-audit
```

The audit:

1. requests the official DataCORE file endpoint;
2. records a checksum-bound, fail-closed diagnostic when the response is not a ZIP archive;
3. never persists HTML response text, authentication tokens, raw non-ZIP payloads, or signed query strings;
4. rejects unsafe, duplicate, encrypted, symbolic-link, or oversized ZIP members;
5. records archive/member SHA-256 values when the archive is available;
6. reads DM4 and TIFF arrays without changing pixels;
7. extracts only relevant instrument/acquisition metadata;
8. compares deterministically matched DM4/TIFF representations;
9. deletes downloaded source files before evidence upload.

The companion `scripts/probe_datacore_file_page.py` records only same-origin links, form actions, non-secret input names, response metadata, and HTML SHA-256. It does not persist the raw HTML or hidden form values.

Only inventory, summary/diagnostic, file-page probe, and artifact-manifest files may be persisted. Raw microscopy files remain external and untracked.

## Required acquisition audit

After the archive becomes available:

1. Download `Diffraction_Pattern.zip` from the official DataCORE file panel without renaming or modifying it.
2. Record the source URL, DOI, download date, archive byte size, and SHA-256.
3. Record every archive member path, byte size, and SHA-256.
4. Read DM4 metadata without altering image arrays. Preserve dtype, shape, intensity range, and relevant acquisition tags.
5. Compare each TIFF with its corresponding DM4 representation. Determine whether the TIFF is a lossless export, display conversion, or independently processed image.
6. Resolve material, sample, acquisition, camera-length or camera-constant, detector, pixel-size, center, and zone-axis provenance. The 120 kV microscope condition is supported at publication level but still needs file binding.
7. Verify that at least two patterns come from independent acquisitions rather than alternative exports of one pattern.
8. Freeze the primary center, smoothing, prominence, radius bounds, candidate matching, calibration, uncertainty, exclusion, and reference/indexing rules before inspecting analyzer agreement with source assignments.

## Minimum pass conditions

A later real-data case may proceed only when all of the following are supported by source files or traceable metadata:

- raw detector data or a demonstrably lossless representation;
- stable source version and valid reuse authorization;
- checksum-bound archive and member inventory;
- material and sample identity;
- immutable acquisition identity;
- at least two independent patterns or acquisitions;
- accelerating voltage bound to the audited files;
- camera length or a traceable camera constant;
- detector metadata when relevant;
- source-supported or reproducibly calibrated pattern center;
- frozen sensitivity and reference/indexing protocol.

## Scientific boundary

Reported `[001]` and `[112]` zone axes and the publication-level `Cr1+deltaTe2` indexing statement must not be used to tune center, smoothing, prominence, minimum distance, radius bounds, or candidate count. Until the raw-file audit, lineage audit, calibration verification, and protocol freeze pass, this registry supports only source triage. It does not support phase identification, reflection indexing, zone-axis accuracy, calibrated `d_nm` accuracy, generalization, or engineering release.

See `case_config.json` for the machine-readable search snapshot, confirmed evidence, unresolved fields, retrieval status, and next action.
