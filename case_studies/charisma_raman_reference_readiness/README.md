# CHARISMA interlaboratory Raman reference readiness

## Purpose

This case evaluates the interlaboratory Raman calibration dataset associated
with *Interlaboratory Study to Minimize Wavelength Calibration Uncertainty Due
to Peak Fitting of Reference Material Spectra in Raman Spectroscopy* as the
leading candidate for MCA's first scientifically credible Raman peak-position
validation case.

The intended future claim is deliberately narrow:

`reference_material_peak_position_localization_and_wavelength_calibration_support`

It is not a mineral/phase classifier, vibrational-mode assignment benchmark,
defect/crystallinity metric, or universal cross-instrument generalization test.

## Why this source is stronger than the current RRUFF path

The interlaboratory study directly addresses peak-position fitting and wavelength
calibration uncertainty using spectra from multiple Raman instruments and
reference materials including neon emission, silicon, calcite and polystyrene.
That question aligns directly with MCA's current Raman baseline, which emits
candidate peak positions but is not scientifically validated for material
identification.

The linked Zenodo record `10.5281/zenodo.13387413` exposes a single NeXus file,
`peak_fitting_spectra.nxs`, with repository MD5
`88485671e56662b00aaad9303dc653d6`. The public landing page identifies the
record as version `v1`.

## Why metadata comes first

This stage requests only the Zenodo API record. It verifies:

- record identity, DOI, status and resource type;
- dataset license metadata exactly as returned by Zenodo;
- API/landing-page version information;
- exact file key, byte count, MD5 and trusted content URL.

The NeXus payload is not downloaded. This avoids selecting datasets, peak truth,
fit results or tolerances after seeing MCA behavior.

## Scientific boundary

A strong publication and checksum-bound file do not prove that the NeXus file
contains the exact raw spectra, reference peak positions and instrument metadata
needed for MCA validation. Those questions remain `Inconclusive` until the file
structure is inspected under a separate predeclared contract.

This metadata-readiness stage does not authorize:

- downloading `peak_fitting_spectra.nxs`;
- reading NeXus/HDF5 groups, arrays or attributes;
- selecting instruments or reference materials for validation;
- viewing MCA Raman output;
- tuning smoothing, prominence or peak fitting;
- choosing a peak-matching tolerance;
- claiming compound/phase identification, vibrational assignment, external
  validation or engineering readiness.

## Next step

If the live Zenodo metadata confirms a suitable license, version and exact
NeXus file identity, create a separate checksum-bound NeXus structure inventory.
That next stage may download the single file and use the repository's existing
`h5py` dependency to inventory groups, datasets, attributes, shapes and dtypes.
It should still avoid MCA execution and should not retain the raw NeXus file in
Git.

Only after the structure shows where raw/reference spectra, instrument identity,
reference materials and fitted/reference peak results live should a validation
subset and peak-truth definition be frozen.

## Reproduction

```powershell
python scripts/audit_zenodo_charisma_raman_reference_readiness.py `
  --config case_studies/charisma_raman_reference_readiness/case_config.json `
  --output outputs/charisma_raman_reference_readiness/readiness_snapshot.json
```

The command performs a metadata request only and reads zero NeXus payload bytes.

## Sources

- Interlaboratory Raman study: DOI `10.1177/00037028251330654`
- Zenodo dataset: DOI `10.5281/zenodo.13387413`
