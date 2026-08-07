# SrTiO3 SAED pre-pixel TIFF metadata audit

## Purpose

Read only the two out-of-line TIFF text tags that the verified first-IFD audit
located entirely before the first pixel strip in all three substantive SrTiO3 SAED
TIFFs.

Verified TIFF layout:

```text
0..7      classic TIFF header
8..193    first IFD
194..217  ImageDescription (24 bytes)
250..261  Software (12 bytes)
272..     first and only pixel strip
```

The audit decompresses at most bytes `0..261`. Byte 272 and all subsequent pixel
bytes remain untouched.

## Why this is useful

The three TIFFs are 2048×2048, one-channel, 64-bit floating-point rasters. TIFF
format alone cannot tell whether values are detector-native counts, converted
counts, or a processed/exported representation.

`ImageDescription` and `Software` may identify the export tool or representation
context at negligible evidence cost. They cannot by themselves establish physical
calibration or detector-native intensity preservation.

## Scientific boundary

Only `ImageDescription` and `Software` are authorized. No other out-of-line TIFF
tag is followed. No pixel array, full TIFF member, full ZIP, or 4D-STEM data is
accessed.

The following remain separate evidence requirements regardless of the text result:

- meaning of filename suffixes `23K`, `91K`, `172K`;
- acquisition/sample independence;
- detector-native intensity preservation;
- pattern centre;
- reciprocal calibration;
- reflection/phase truth;
- external-validation readiness.
