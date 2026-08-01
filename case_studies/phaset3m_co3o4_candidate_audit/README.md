# PhaseT3M Co3O4 Tilt-Series Candidate Audit

This case audits the exact-material Co3O4 microscopy candidate in Zenodo record `10.5281/zenodo.17336678` without treating it as independent segmentation-validation evidence.

The source describes an approximately 7 nm Co3O4 nanoparticle on a carbon substrate. Its `raw_tilt_data.zip` archive is checksum-bound by the repository MD5 `efb1e487aedbafa7c0822e0d31968d05`. Despite the archive name, the source states that the released Co3O4 tilt series is motion-corrected, tilt-aligned, and denoised. The relevant member is `Co3O4_denoised_tilt_series.h5`.

## Why it is not external validation

The source currently fails the project contract because:

- it reports one Co3O4 nanoparticle rather than at least two independent samples and acquisitions;
- the released representation is processed and denoised, not established as raw detector data or a demonstrably lossless export;
- immutable sample and acquisition identifiers are not provided;
- independent blinded segmentation labels and adjudicated consensus are absent;
- target-model development non-use and content disjointness are not established;
- creator overlap exists with the target cobalt-oxide training source;
- the dataset record does not explicitly declare a data reuse licence; the stated GPL-3.0 applies to code.

The result is therefore **Diagnostic** for exact-material HDF5 ingestion and processed-representation robustness only. It is **Inconclusive** for independent segmentation performance.

## Run

Download the exact archive externally, then run:

```bash
python scripts/audit_phaset3m_co3o4_candidate.py \
  --config case_studies/phaset3m_co3o4_candidate_audit/case_config.json \
  --archive /path/to/raw_tilt_data.zip \
  --output outputs/phaset3m-co3o4-candidate-audit
```

The dedicated GitHub Actions workflow downloads the pinned archive, verifies its MD5, safely inventories the ZIP, extracts only the unique target HDF5 into a temporary directory, records HDF5 groups/datasets/attributes and deterministic numeric samples, deletes the raw archive and extraction, and uploads evidence files only.

## Outputs

- `phaset3m_archive_inventory.csv`
- `phaset3m_hdf5_inventory.json`
- `phaset3m_candidate_audit_summary.json`
- `phaset3m_candidate_audit_report.md`
- `phaset3m_candidate_audit_manifest.json`

No ZIP or HDF5 source file is included in the evidence package. No labels, model inference, segmentation metric, phase assignment, or physical conversion are produced.
