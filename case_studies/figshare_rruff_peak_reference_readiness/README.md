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

## Live metadata result

The bounded Figshare API audit verified the publication-frozen source without
reading any dataset file payload:

- Figshare item: `7427393`;
- dataset DOI: `10.6084/m9.figshare.7427393.v2`;
- version: `2`;
- published/modified timestamp: `2018-12-05T20:08:06Z`;
- Figshare dataset license metadata: **CC BY 4.0**;
- file inventory: four files, all with matching supplied/computed MD5 metadata;
- experimental reference candidate: `Experimental Data.json`;
- Figshare file ID: `13752833`;
- size: `24,595` bytes;
- MD5: `5397f81312a454f6255b65a1d6d9529e`;
- dataset-file payload bytes read by this audit: `0`.

This resolves the source/version/license/file-identity questions that blocked use
of the current RRUFF bulk archive. There is no need to download the modern
229 MB RRUFF collection for the first benchmark.

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

## Peak-reference limitation

The paper defines `wavenumbers` in the experimental JSON as the list of peak
locations, but the currently reviewed publication text does not establish a
sufficiently detailed independent manual or algorithmic protocol for how those
peak locations were extracted from the RRUFF spectra.

Therefore the peak list remains a **Diagnostic published reference annotation**,
not authoritative physical truth. A later benchmark may either resolve the
annotation-generation provenance or explicitly scope its claim as agreement
with this frozen published annotation set.

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

The exact experimental JSON is now sufficiently identified for a separate
**annotation-payload inventory contract**. That next contract may download only
file `13752833` and must verify the 24,595-byte size and MD5 before parsing. It
should inventory RRUFF IDs, peak-list counts/ranges and metadata completeness
only; it still must not execute MCA Raman analysis.

After the annotation inventory is known, freeze a small target-blind spectrum
subset and a peak-matching/tolerance protocol **before** any corresponding MCA
peak output is viewed. Only then should exact source spectra be acquired for the
selected IDs.

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
