# SrTiO3 SAED TIFF metadata audit

## Purpose

Inspect only classic-TIFF header and first-IFD metadata for the three substantive
members previously verified inside Zenodo `SAED.zip`:

- `SAED/23K.tif`;
- `SAED/91K.tif`;
- `SAED/172K.tif`.

No TIFF pixel array, full TIFF member, full ZIP, or 4D-STEM array is decoded or
retained.

## Why this comes next

The remote ZIP inventory established three same-size substantive TIFF members, but
file size and filename are not enough to establish dimensions, bit depth, TIFF
sample representation, or acquisition semantics.

This stage replaces size-based guesses with source-embedded TIFF metadata while
keeping the scientific claim boundary narrow.

## Pixel-free read contract

For each target TIFF, the audit:

1. rechecks the pinned `SAED.zip` central directory;
2. reads the selected ZIP local header and filename/extra metadata;
3. reads at most 262,144 compressed bytes from the start of the member;
4. decompresses exactly 8 bytes for the classic TIFF header;
5. proceeds only if the first IFD offset is exactly byte 8;
6. decompresses only enough bytes to obtain the first-IFD entry count and complete
   first IFD;
7. records selected TIFF tags when their values are inline in the IFD;
8. never follows out-of-line TIFF value offsets.

If the first IFD is not immediately after the TIFF header, the audit stops instead
of decompressing through an unknown region that might contain pixels.

## Recorded tags

The bounded parser recognizes common structural tags including:

- ImageWidth / ImageLength;
- BitsPerSample;
- TIFF Compression and PhotometricInterpretation;
- SamplesPerPixel / RowsPerStrip;
- StripOffsets / StripByteCounts;
- tile dimensions/offsets/counts when present;
- PlanarConfiguration and SampleFormat;
- Software and ImageDescription.

Out-of-line values such as long descriptions or offset arrays are recorded only as
unfollowed pointers.

## Scientific boundary

Even if all three TIFFs have identical dimensions and bit depth, this does not prove:

- detector-native intensity preservation;
- the meaning of `23K`, `91K`, or `172K`;
- independent acquisition/sample identity;
- pattern centre;
- reciprocal calibration;
- reflection/phase truth;
- analyzer or external-validation readiness.

The output is **Diagnostic format evidence** only.
