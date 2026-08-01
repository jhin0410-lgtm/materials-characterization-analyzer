# SAED External-Validation Candidate Registry

This directory records source-backed candidates for future external validation of the SAED analyzer. It is a search and intake artifact, not a validated dataset and not an analysis result.

## Current decision

The best current candidate is Indiana University DataCORE dataset `10.5967/ct7n-8275`, which reports chromium-telluride SAED patterns along `[001]` and `[112]` zone axes and supplies both TIFF images and original Gatan DM4 files under CC BY 4.0.

The candidate is **not yet eligible for external validation**. The public landing page does not establish the archive checksum, member inventory, accelerating voltage, camera calibration, detector metadata, immutable sample/acquisition identities, pattern-center provenance, or acquisition independence.

The existing FINDS SAED case remains useful for real-image software integration and sensitivity testing, but its lossy JPEG and unresolved material/acquisition provenance do not satisfy the raw calibrated validation contract.

## Required acquisition audit

1. Download `Diffraction_Pattern.zip` from the official DataCORE file panel without renaming or modifying the archive.
2. Record the source URL, DOI, download date, archive byte size, and SHA-256.
3. Extract into an immutable local data root and record every member path, byte size, and SHA-256.
4. Read DM4 metadata without altering image arrays. Preserve dtype, shape, intensity range, and all relevant acquisition tags.
5. Compare each TIFF with its corresponding DM4 representation. Determine whether the TIFF is a lossless export, a display conversion, or an independently processed image.
6. Resolve material, sample, acquisition, accelerating-voltage, camera-length or camera-constant, detector, pixel-size, center, and zone-axis provenance.
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
- accelerating voltage;
- camera length or a traceable camera constant;
- detector metadata when relevant;
- source-supported or reproducibly calibrated pattern center;
- frozen sensitivity and reference/indexing protocol.

## Scientific boundary

Reported `[001]` and `[112]` zone axes must not be used to tune center, smoothing, prominence, minimum distance, radius bounds, or candidate count. Until the raw-file audit passes, this registry supports only source triage. It does not support phase identification, reflection indexing, zone-axis accuracy, calibrated `d_nm` accuracy, generalization, or engineering release.

See `case_config.json` for the machine-readable search snapshot, confirmed evidence, unresolved fields, and next action.
