# TM-Fe-Si public XRD descriptive handoff

Status: `producer_implementation_ready_for_source_replay`

This case converts the exact public `Fig.2-XRD data.xlsx` workbook from the
TM-Fe-Si Data in Brief / Mendeley Data dataset into a checksum-bound MCA handoff
for `materials-data-analyzer`.

## Source identity

- Publication DOI: `10.1016/j.dib.2022.108868`
- Dataset DOI: `10.17632/gp8rkw2k6v.2`
- Dataset version: `2`
- License: `CC BY 4.0`
- Workbook: `Fig.2-XRD data.xlsx`
- Size: `218303` bytes
- SHA-256: `7138e2e2d6dbf422c7b534af38810bfe963969cd3f8e8b3a7e8daf7ddb17ac20`

The raw workbook is not committed to this repository. The producer refuses any
source whose filename, byte count, digest, headers, row count, or 2theta grid
differs from the frozen source audit.

## Explicit trace identity

The workbook itself identifies the six traces:

| Workbook header | Stable handoff sample ID |
|---|---|
| `Fig. 2(a) Ti7Fe52Si41` | `tm-fe-si-ti7fe52si41-1050c-1d` |
| `Fig. 2(b) Zr7Fe52Si41` | `tm-fe-si-zr7fe52si41-1050c-1d` |
| `Fig. 2(c) Hf7Fe52Si41` | `tm-fe-si-hf7fe52si41-1050c-1d` |
| `Fig. 2(d) V7Fe52Si41` | `tm-fe-si-v7fe52si41-1050c-1d` |
| `Fig. 2(e) Nb7Fe52Si41` | `tm-fe-si-nb7fe52si41-1050c-1d` |
| `Fig. 2(f) Ta7Fe52Si41` | `tm-fe-si-ta7fe52si41-1050c-1d` |

These IDs mean **nominal composition + preparation-family identity**, not an
identical physical aliquot across XRD and magnetometry.

## Frozen analysis contract

Each trace must contain exactly 3501 finite points from 20 to 90 degrees 2theta
at 0.02 degree spacing. The producer uses the existing MCA XRD defaults without
tuning to published peak labels or magnetic outcomes:

- Savitzky-Golay smoothing: window `11`, polynomial order `3`
- peak prominence: `0.05 * trace dynamic range`
- minimum peak distance: `3` samples
- edge margin: `3` samples
- FWHM: scipy half-height peak widths

No interpolation, outlier deletion, intensity normalization, or plotting-offset
correction is performed.

Only the following derived XRD features are exported:

- `detected_peak_count`
- `main_peak_two_theta`
- `mean_fwhm`
- `median_fwhm`
- `minimum_two_theta`
- `maximum_two_theta`

`main_peak_intensity` is explicitly excluded because the publication data use
integer vertical plotting offsets. Scherrer size is also excluded because this
handoff does not establish the instrumental-broadening/calibration evidence
needed for a defensible size claim.

## Run

From the MCA repository root:

```powershell
$python = (Resolve-Path ".\.venv313\Scripts\python.exe").Path

& $python .\scripts\build_tm_fe_si_xrd_handoff.py `
  --workbook "C:\Users\USER\Desktop\Datasets on materials research of hard ferromagnet in TM-Fe-Si (TM=Ti, Zr, Hf, V, Nb, and Ta) ternary systems\Fig.2-XRD data.xlsx" `
  --output ".\outputs\tm_fe_si_xrd_descriptive_handoff"
```

The output is transactional and includes source/analysis evidence, per-trace
peak tables, the portable `handoff_bundle/`, and a case summary. Existing output
directories are never overwritten.

## Scientific closeout

**Diagnostic.** The handoff supports descriptive peak-location/width summaries
and cross-repository provenance validation. It does not independently validate
peak truth or phase identity.

Primary limitations:

- absolute XRD intensity is not comparable across the six traces because of
  publication plotting offsets;
- exact XRD/VSM physical specimen identity is unconfirmed;
- the uploaded 13-workbook subset omits the SEM/EDS evidence used by the
  publication;
- no phase assignment, phase fraction, Scherrer-size, association, prediction,
  causality, or engineering claim is authorized.

The downstream policy is therefore capped at `descriptive` even though the case
is useful Diagnostic evidence.
