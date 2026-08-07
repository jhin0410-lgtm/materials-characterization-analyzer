# BIR-MicroED 300 keV selected TVIPS header-prefix audit

## Question

The verified `AVAAGA_300kV_293K.zip` central directory contains four `.tvips`
members named `series1.tvips` through `series4.tvips`. Those names do not satisfy
the documented RosettaSciIO/HyperSpy `*_000.tvips` split-stream filename gate, but
filename incompatibility does not prove that the first member lacks an internal
TVIPS general header.

This stage asks one narrow question:

> Do the first 256 decompressed bytes of the selected `series1.tvips` member match
> the general-header structure used by the pinned RosettaSciIO TVIPS reader?

## Pinned parser contract

The contract is derived from:

- repository: `hyperspy/rosettasciio`;
- commit: `bc254db14cd7d4d23169b11aeb622a0a7eac1fbe`;
- source: `rsciio/tvips/_api.py`.

At that revision the reader defines a 256-byte general header containing thirteen
little-endian unsigned 32-bit fields followed by 204 dummy bytes. The fields are:

`size`, `version`, `dimx`, `dimy`, `bitsperpixel`, `offsetx`, `offsety`, `binx`,
`biny`, `pixelsize`, `ht`, `magtotal`, and `frameheaderbytes`.

The reader separately requires a filename ending in `_000.tvips` before reading
that header. This audit deliberately keeps **filename compatibility** and
**internal-header structural compatibility** as separate evidence.

## Bounded source access

The live audit rechecks the already verified remote ZIP central directory, then for
one exact member only:

1. reads the 30-byte ZIP local file header;
2. reads only the local filename/extra-field bytes;
3. reads at most 262,144 compressed member bytes;
4. decompresses at most the first 256 output bytes;
5. records parsed scalar header fields and hashes, not raw source bytes.

There is no full ZIP fallback and no full member download.

Unsupported ZIP compression is an **Inconclusive** format result, not a reason to
increase the transfer scope.

## Run

```bash
python scripts/audit_zenodo_bir_300kev_tvips_header_prefix.py \
  --config case_studies/zenodo_bir_300kev_saed_header_prefix/case_config.json \
  --output outputs/zenodo_bir_300kev_saed_header_prefix/header_prefix_snapshot.json
```

## Interpretation

A structural match can support only a **Diagnostic format claim**: the selected
member begins with bytes consistent with the pinned TVIPS general-header layout.

It does not establish:

- source-native `_000.tvips` split-stream naming;
- immutable sample or acquisition identity;
- detector-native intensity preservation;
- pattern centre;
- reciprocal calibration;
- phase/reflection truth;
- analyzer performance;
- external-validation readiness;
- engineering readiness.

Even if `ht`, `pixelsize`, `magtotal`, offsets, or binning are nonzero, their
scientific meaning must remain unpromoted until source metadata or an independently
justified calibration protocol establishes what those fields represent for this
acquisition.

No diffraction pixels or frame payloads are decoded at this stage.
