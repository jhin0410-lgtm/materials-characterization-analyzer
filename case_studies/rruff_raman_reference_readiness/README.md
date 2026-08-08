# RRUFF Raman reference-source readiness

## Purpose

This case asks whether the RRUFF Raman library is ready to become the first
independent reference source for a narrow MCA Raman validation case.

The intended future claim is deliberately limited to **peak-localization
agreement against an independently declared reference**. This case does not
predeclare mineral classification, vibrational-mode assignment, defect or
crystallinity quantification, or general analyzer accuracy.

## Why RRUFF is scientifically promising

The RRUFF project describes a public Raman reference library built from
well-characterized mineral samples. Its project-method documentation describes
review before public release, supporting X-ray diffraction and chemical
composition characterization, and Raman measurements collected under multiple
laser wavelengths. NASA AHED also catalogs the RRUFF mineral database under DOI
`10.48667/pre9-s770`.

The current official RRUFF Raman bulk index exposes multiple downloadable ZIP
collections. `excellent_unoriented.zip` is the candidate retained for source
readiness because it represents the high-quality unoriented collection and
avoids introducing orientation as an uncontrolled requirement for the first
case.

## Why the archive is not downloaded here

Public or free access is not treated as an explicit redistribution or
derived-dataset license. During this audit, no explicit machine-readable RRUFF
dataset license or explicit redistribution/derived-dataset permission was
identified on the authoritative source pages reviewed. The Apache directory
listing also does not provide an immutable archive checksum or a versioned
archive identifier.

Those are provenance and reuse blockers, not reasons to silently download a
roughly hundreds-of-megabytes collection and decide later what it meant.

The official directory listing is therefore the only live network resource read
by this case. The audit records whether `excellent_unoriented.zip` is listed,
together with bounded index metadata and a checksum of the index response. It
reads **zero ZIP or spectrum payload bytes**.

## Current evidence decision

- RRUFF project identity: **Supported**;
- public reference-library access: **Supported**;
- reviewed mineral-reference context: **Diagnostic**;
- current `excellent_unoriented.zip` listing: live-audited;
- explicit reuse rights for automated acquisition/redistribution: **Inconclusive**;
- immutable archive version/checksum identity: **Inconclusive**;
- independent peak-position truth: **Inconclusive**;
- Raman external-validation readiness: **Inconclusive**.

RRUFF mineral identity is valuable but is not equivalent to an independent list
of expected Raman peak positions for testing MCA's peak detector. A later
validation protocol must specify how reference peaks are independently defined
before MCA outputs are viewed.

## Prohibited actions at this stage

This source-readiness case does not authorize:

- downloading `excellent_unoriented.zip`;
- extracting or retaining RRUFF spectra;
- running the MCA Raman analyzer on RRUFF data;
- tuning baseline, smoothing, prominence, or matching parameters;
- fitting or training a classifier/model;
- mineral or vibrational-mode assignment;
- external-validation or engineering-readiness claims.

## Next evidence requirement

Before any spectrum is downloaded, resolve both:

1. explicit RRUFF reuse/redistribution terms appropriate to repository-backed
   validation artifacts; and
2. a stable candidate-spectrum identity strategy, including source ID/version
   and an independent reference-peak definition.

Only after those are resolved should a **small, predeclared spectrum subset** be
selected. There is no scientific reason to ingest the entire bulk archive for a
first peak-localization benchmark.

## Reproduction

```powershell
python scripts/audit_rruff_raman_reference_readiness.py `
  --config case_studies/rruff_raman_reference_readiness/case_config.json `
  --output outputs/rruff_raman_reference_readiness/readiness_snapshot.json
```

The command requests only the official Raman directory index. It does not
request the candidate ZIP.

## Sources reviewed

- RRUFF project method reference: DOI `10.1515/9783110417104-003`
- RRUFF Raman bulk index: `https://www.rruff.net/zipped_data_files/raman/`
- NASA AHED RRUFF catalog record: DOI `10.48667/pre9-s770`
