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

## Confirmed metadata readiness

The live Zenodo metadata audit on 2026-08-09 confirmed the exact record and
candidate file without reading the NeXus payload:

- Zenodo DOI: `10.5281/zenodo.13387413`;
- resource type: `dataset`;
- title: `An analysis of peak fitting in reference material spectra for calibration of Raman spectroscopy instruments (Dataset)`;
- landing-page version claim: `v1`;
- Zenodo API version field: absent (`null`);
- license metadata: `cc-by-4.0`;
- file: `peak_fitting_spectra.nxs`;
- file size: `8,992,904` bytes;
- MD5: `88485671e56662b00aaad9303dc653d6`;
- trusted metadata content URL: `https://zenodo.org/api/records/13387413/files/peak_fitting_spectra.nxs/content`;
- NeXus payload bytes read: `0`.

The bounded live result is pinned in `metadata_readiness_snapshot.json`. It is a
metadata/provenance checkpoint, not a scientific validation result.

## Why metadata came first

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

- downloading `peak_fitting_spectra.nxs` under this contract;
- reading NeXus/HDF5 groups, arrays or attributes;
- selecting instruments or reference materials for validation;
- viewing MCA Raman output;
- tuning smoothing, prominence or peak fitting;
- choosing a peak-matching tolerance;
- claiming compound/phase identification, vibrational assignment, external
  validation or engineering readiness.

Current scientific evidence level: `Diagnostic`. The metadata identity and
interlaboratory reference-material context are supported, while NeXus internal
structure and exact reference-peak truth remain `Inconclusive`.

## Next step

Create a separate checksum-bound NeXus structure-inventory contract. That stage
may download the single `8,992,904` byte file, verify the pinned MD5, and use the
repository's existing `h5py` dependency only to inventory groups, datasets,
attributes, shapes and dtypes. It should still avoid MCA execution and should
not retain the raw NeXus file in Git.

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
