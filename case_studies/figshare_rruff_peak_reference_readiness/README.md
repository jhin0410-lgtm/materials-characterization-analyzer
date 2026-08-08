# Figshare RRUFF peak-reference readiness

## Purpose

This case evaluates the frozen Figshare data record associated with Liang,
Dwaraknath and Persson, *High-throughput computation and evaluation of Raman
spectra*, as a possible source for the first narrow MCA Raman validation case.

The Scientific Data paper states that its separate experimental JSON extracted
from RRUFF contains mineral metadata, `RRUFF_id`, background noise, acquisition
start, **peak locations**, peak intensities and a matched Materials Project ID.
The RRUFF spectra and CIF files used by the authors were also deposited in the
same Figshare record for reproducibility.

That makes this record materially more useful than downloading the current
RRUFF bulk collection blindly: it is a frozen publication dataset and may expose
explicit license, version and file-checksum metadata together with a compact
experimental peak-reference file.

## Scientific target

The only future claim considered here is:

`peak_localization_agreement_on_frozen_reference_spectra`

This is intentionally narrower than mineral identification or Raman assignment.
The following remain out of scope:

- mineral/compound classification;
- vibrational-mode or bond assignment;
- quantitative defect or crystallinity metrics;
- cross-instrument or acquisition generalization;
- model fitting or training;
- engineering decisions.

## Why metadata comes first

The article itself is CC BY 4.0, but the dataset license must be read from the
Figshare dataset metadata rather than inferred from the paper license. Likewise,
a public file link is not sufficient provenance: the validation source needs a
stable article/version identity and file ID/name/size/checksum metadata.

This stage therefore requests only:

`https://api.figshare.com/v2/articles/7427393`

It records the current item identity, version, DOI, dataset license metadata and
file inventory metadata. It does not follow any file `download_url`.

## Peak-reference limitation

The paper defines `wavenumbers` in the experimental JSON as the list of peak
locations, but the currently reviewed publication text does not establish a
sufficiently detailed independent manual or algorithmic protocol for how those
peak locations were extracted from the RRUFF spectra.

Therefore the peak list is currently a **Diagnostic reference annotation
candidate**, not authoritative physical truth. A later benchmark must resolve
that annotation provenance or explicitly scope the result as agreement with a
frozen published annotation set.

Materials Project matches and computed Raman modes in the publication dataset
must not be used to select spectra, tune MCA peak parameters or score MCA. That
would couple the validation target to the computational benchmark rather than
test the Raman detector independently.

## Fail-closed boundary

This metadata audit does not authorize:

- downloading any Figshare dataset file;
- reading the experimental JSON payload;
- downloading RRUFF spectrum payloads;
- running MCA Raman analysis;
- tuning baseline, smoothing, prominence or matching parameters;
- fitting/training a model;
- mineral or vibrational-mode assignment;
- external-validation or engineering claims.

## Next step

If the live Figshare metadata confirms an explicit suitable dataset license,
version 2, a checksum-bound experimental JSON candidate and stable file
identities, a **separate predeclared payload contract** may download only the
experimental JSON first. Even then, no RRUFF spectrum should be acquired until a
small target-blind spectrum subset and a peak-matching protocol are frozen.

The first benchmark should remain small and interpretable. There is no current
need to ingest all computational Raman data or the full modern RRUFF archive.

## Reproduction

```powershell
python scripts/audit_figshare_rruff_peak_reference_readiness.py `
  --config case_studies/figshare_rruff_peak_reference_readiness/case_config.json `
  --output outputs/figshare_rruff_peak_reference_readiness/readiness_snapshot.json
```

The command performs a Figshare metadata request only.

## Sources

- Scientific Data article: DOI `10.1038/s41597-019-0138-y`
- Figshare dataset: DOI `10.6084/m9.figshare.7427393`
