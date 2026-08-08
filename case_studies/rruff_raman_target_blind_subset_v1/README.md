# RRUFF Raman target-blind subset v1

## Purpose

This case freezes the first reference subset **before** any selected RRUFF source
spectrum or MCA Raman output is viewed.

The upstream publication-frozen annotation inventory contains 55 unique RRUFF
IDs and 205 published peak annotations. That cohort is structurally clean, but
manual selection based on peak count, spectrum appearance, mineral identity or
expected analyzer difficulty would create selection bias.

## Selection rule

Only the exact pinned RRUFF ID strings are permitted as selection inputs.

For each ID:

```text
SHA256("mca-rruff-peak-localization-v1:" + RRUFF_ID)
```

The 55 IDs are sorted by the hexadecimal SHA-256 digest ascending, with RRUFF ID
ascending as a deterministic tie breaker. The first 10 IDs become the v1
reference subset. The remaining 45 IDs define a frozen replacement order.

If a selected ID later fails source-readiness requirements, the replacement is
the next unused ID in this frozen ranking. A sample must never be replaced
because MCA performs poorly on it.

## Inputs explicitly not used

Selection does not use:

- published peak counts or wavenumbers;
- peak intensities;
- `noise` or `start`;
- formula, mineral name/type or crystal system;
- Materials Project IDs;
- computed Raman modes;
- source spectrum data or appearance;
- MCA Raman outputs;
- manual preference.

## Scientific boundary

This selection is not a validation result and does not establish source
availability. It only prevents target leakage and post-hoc cherry-picking.

No RRUFF spectrum is downloaded here. No acquisition metadata is inspected. No
MCA Raman analysis, parameter tuning, matching-tolerance selection, scoring,
mineral identification, external-validation claim or engineering decision is
authorized.

## Next step

After the deterministic 10-ID subset is frozen, audit source-spectrum
availability and acquisition metadata **in the frozen ranking order**. For each
ID, determine whether an exact RRUFF spectrum can be identified with adequate
wavelength/orientation/processing provenance and reproducible access.

If a selected ID is unavailable or scientifically unsuitable, use the next ID
in the frozen replacement order. Do not inspect MCA performance before making
that replacement.

Only after source identities are resolved should a peak-matching protocol and
scientifically motivated tolerance/sensitivity range be predeclared.

## Reproduction

```powershell
python scripts/select_rruff_raman_target_blind_subset.py `
  --config case_studies/rruff_raman_target_blind_subset_v1/selection_contract.json `
  --output outputs/rruff_raman_target_blind_subset_v1/selection.json
```

The command is deterministic and performs no network access.
