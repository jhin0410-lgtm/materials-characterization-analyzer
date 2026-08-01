# Public Zr15Nb DSC Real-Data Case

This case executes the repository's conservative DSC baseline on a real,
checksum-bound public measurement while preserving source structure, acquisition
context, unresolved metadata, and the distinction between event candidates and
phase or reaction assignments.

## Public source

- Repository: Zenodo
- Record: `17590045`
- DOI: `10.5281/zenodo.17590045`
- Dataset version: `v1`
- Licence: `CC-BY-4.0`
- Related article DOI: `10.1007/s10853-025-11846-x`
- Material context: metastable beta Zr-15Nb alloy after the source-reported
  solution-treatment route

The case downloads only these files at runtime:

- `DSC_ElResistance_ThExpansion.csv`
- `ReadMe.txt`

Both source MD5 values and downloaded SHA-256 values are pinned in
`case_config.json`. External raw files are downloaded transiently and are not
committed or uploaded in workflow evidence.

## Source-supported acquisition context

The related article reports:

- linear heating from room temperature to `800 °C`;
- heating rate `5 °C/min`;
- inert argon atmosphere;
- Netzsch DSC 404 C Pegasus;
- two specimens tested for each initial condition;
- plotted sign convention: exothermic positive and endothermic negative.

The public CSV contains one DSC curve. The file is not bound to a specific one
of the two reported replicates. Sample mass, crucible material, purge-flow rate,
and calibration reference are also unresolved and are not inferred.

## Exact adapter contract

The combined source table has three header rows and six columns. This case binds
only:

- column 0: DSC temperature, `°C`;
- column 1: DSC signal, `mW/mg`.

`1 mW/mg` is numerically identical to `1 W/g`, so the canonical conversion
factor is exactly `1.0`.

The verified DSC segment contains `43,167` finite rows from `80.005 °C` to
`799.99799 °C`. Temperature is strictly increasing across the entire selected
segment. The adapter performs no sorting, interpolation, trimming, row
exclusion, replicate aggregation, or cross-method alignment.

## Analysis contract

The primary run and two sensitivity runs share the same source, linear baseline,
endotherm-down source convention, prominence fraction, and minimum candidate
separation. Only the Savitzky-Golay temperature span changes:

| Run | Requested smoothing span |
|---|---:|
| `primary` | `2 °C` |
| `sensitivity_1c` | `1 °C` |
| `sensitivity_5c` | `5 °C` |

Temperature spans are converted deterministically to odd sample windows using
the median source temperature step. Candidate parameters were predeclared from
the source sampling contract and were not fitted to the publication's reported
event intervals.

## Candidate sensitivity review

The case-level review does not edit the three analyzer candidate tables. Each
primary candidate is matched one-to-one to the nearest same-direction candidate
from each sensitivity run within the configured `10 °C` tolerance.

The review records separately:

- whether a candidate is present in all three runs;
- maximum temperature spread across the runs;
- whether the diagnostic within-FWHM area has the sign expected from the
  candidate direction;
- unmatched sensitivity candidates.

A stable temperature is not a phase or reaction assignment. A directionally
inconsistent diagnostic area is retained as a review flag rather than silently
removed, relabelled, or corrected.

## Run

```bash
python scripts/audit_public_zr15nb_dsc_source.py \
  --config case_studies/public_zr15nb_dsc/case_config.json \
  --output outputs/public-zr15nb-dsc/source-audit

python scripts/run_public_zr15nb_dsc_case.py \
  --config case_studies/public_zr15nb_dsc/case_config.json \
  --output outputs/public-zr15nb-dsc/result

python scripts/review_public_zr15nb_dsc_candidates.py \
  --config case_studies/public_zr15nb_dsc/case_config.json \
  --result outputs/public-zr15nb-dsc/result
```

## Outputs

```text
outputs/public-zr15nb-dsc/
├── source-audit/
│   ├── source_audit_summary.json
│   ├── source_column_profile.csv
│   ├── source_audit_report.md
│   └── source_audit_manifest.json
└── result/
    ├── canonical/zr15nb_dsc_heating.csv
    ├── analyses/
    │   ├── primary/
    │   ├── sensitivity_1c/
    │   └── sensitivity_5c/
    ├── dsc_sensitivity_candidates.csv
    ├── dsc_candidate_robustness.csv
    ├── dsc_unmatched_sensitivity_candidates.csv
    ├── case_summary.json
    ├── case_validation_report.md
    └── case_artifact_manifest.json
```

Each analysis directory contains the existing thermal processed table, candidate
table, long-format features, diagnostic figure, and analysis manifest.

## Regression hardening

- The standalone source audit verifies both the repository MD5 and the pinned SHA-256 before reporting checksum success.
- Invalid, blank, nonnumeric, or nonfinite temperature cells terminate monotonic runs and retain source-row offsets.
- Candidate matching maximizes valid one-to-one matches before minimizing total temperature distance within each direction and sensitivity run.
- Re-running the review replaces its delimited report section rather than appending duplicate human-readable evidence.

## Scientific closeout

**Evidence level: Diagnostic**

- Supported: the source identity, checksums, exact table structure, units,
  complete monotonic heating segment, canonical conversion, analyzer execution,
  sensitivity-run provenance, and deterministic candidate matching.
- Diagnostic only: automatic endothermic and exothermic candidates, temperature
  stability across the three smoothing spans, and within-FWHM area-direction
  consistency.
- Unresolved: exact replicate identity, sample mass, crucible, purge flow,
  calibration reference, baseline validity, event onset protocol, and independent
  event review.
- Unsupported: phase confirmation, reaction or mechanism assignment, validated
  onset temperatures, quantitative enthalpy claims, causal interpretation, or
  engineering-release decisions.

The article's reported temperature intervals are retained as contextual
literature information only. They are not detection labels and are not used to
select, tune, accept, reject, or rename analyzer candidates.
