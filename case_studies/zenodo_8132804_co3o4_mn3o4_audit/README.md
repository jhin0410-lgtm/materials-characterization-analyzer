# Zenodo 8132804 Co3O4-Mn3O4 source audit

This case study audits Zenodo record `10.5281/zenodo.8132804` as a possible independent cobalt-oxide TEM/HRTEM segmentation-validation source.

## Why it is audited

The source is materially stronger than publication-figure candidates because the archive contains scientific HDF5 arrays named `raw_tilt_series.h5` and `Exp_1_coarse_tilt_series.h5`. The associated publication describes a Co3O4-Mn3O4 core-shell specimen acquired by HAADF-STEM and EELS tomography.

The target analyzer, however, requires independent raw or demonstrably lossless Co3O4 **TEM/HRTEM** images suitable for binary nanoparticle segmentation evaluation. A real electron-microscopy array is not automatically comparable to that target task.

## Bounded method

The audit deliberately avoids downloading the full 1,183,315,114-byte archive.

1. Verify the official Zenodo record, DOI, version, CC BY 4.0 licence, archive byte count and MD5.
2. Retrieve only the ZIP tail and central directory using HTTP Range.
3. Verify the exact 71-member inventory and pinned central-directory size.
4. Retrieve only two compressed HDF5 members, totaling about 66.1 MB.
5. Verify member path, compressed and uncompressed size, CRC32 and uncompressed SHA-256.
6. Inspect HDF5 group, dataset, shape, dtype and attributes without running an analyzer.
7. Delete the extracted HDF5 members before evidence packaging.

## Verified representation

The `raw_tilt_series.h5` member contains one source-assigned experiment, `Exp_1`:

- HAADF/MAADF arrays: `400 x 400 x 31`, `float32`
- EELS-derived arrays: `400 x 400 x 9`, `float32`
- HAADF tilt angles: 31
- EELS tilt angles: 9
- embedded root, group and dataset attributes: none

The coarse member contains the same experiment after spatial/angle selection, including a `345 x 345 x 39` HAADF tilt series and three `345 x 345 x 9` elemental arrays.

## Scientific disposition

Status: `raw_stem_tomography_verified_but_not_tem_segmentation_validation_ready`

Registry status: `excluded_wrong_microscopy_modality`

The source is excluded from target external validation because:

- it is a Co3O4-Mn3O4 mixed-material core-shell specimen rather than an isolated Co3O4 cohort;
- it is HAADF-STEM/EELS tomography rather than target TEM/HRTEM imaging;
- it exposes only one experiment and does not satisfy the minimum two-sample/two-acquisition requirement;
- no immutable sample or acquisition IDs are embedded;
- no pixel calibration or detector provenance is embedded in the audited HDF5 files;
- no independent segmentation labels are supplied;
- target-model development non-use is not established;
- Mary Scott overlaps the target training-source creator set.

The arrays remain useful for bounded HDF5 ingestion diagnostics and cross-modality tomography research. They are not evidence for Co3O4 TEM segmentation accuracy, model selection, retraining, or engineering release.

## Run

```bash
python scripts/audit_zenodo_8132804_co3o4_mn3o4.py \
  --config case_studies/zenodo_8132804_co3o4_mn3o4_audit/case_config.json \
  --output outputs/zenodo_8132804_co3o4_mn3o4_audit
```
