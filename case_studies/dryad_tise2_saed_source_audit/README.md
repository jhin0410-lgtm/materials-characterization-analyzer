# Dryad TiSe2 SAED/HRTEM source audit

This case audits Dryad dataset `10.5061/dryad.6djh9w1hw`, published for *Revisiting the charge-density-wave superlattice of 1T-TiSe2*.

The repository description declares a useful separation between experimental and simulated diffraction data:

- `Fig2_Data/`: experimental diffraction patterns along `[1-10]` and `[001]`;
- `Fig3_Data/`: simulations based on a published structure;
- `Fig4_Data/`: simulations for proposed displacement models;
- supplementary folders: additional diffraction, profiles, real-space imaging and calculations.

This is a cross-material static-SAED diagnostic candidate. It is not cobalt oxide and cannot validate the current Co3O4 TEM segmentation model.

## Verified live result

The verified GitHub Actions run established:

- official DOI, normalized title and top-level file identities: **Supported**;
- `Data_TiSe2.zip` file ID: `4808550`;
- `README.md` file ID: `4808551`;
- official dataset-bundle route without a token: HTTP `401 Unauthorized`;
- public individual-file route from the audited GitHub runner: HTTP `403 Forbidden`;
- anonymous source download in the audited runner: **Unsupported**;
- archive checksum, CRC and member inventory: **Inconclusive**;
- archive-level experimental/simulation separation: **Inconclusive**;
- external-validation and engineering-decision readiness: `false`.

The successful workflow means the access condition was reproduced and recorded safely. It does **not** mean that the 1.89 GB source archive was downloaded or validated.

The pinned evidence is stored in `verified_snapshot.json`. The workflow artifact contained only four small metadata files and no source ZIP, image, spreadsheet or pixel array.

## Bounded audit behavior

The audit:

1. resolves the DOI through the official Dryad API;
2. normalizes HTML and Unicode in the title before matching pinned identity tokens;
3. verifies required top-level filenames and file IDs;
4. first attempts the official DOI-level dataset-bundle route;
5. falls back to the public individual-file route only when the first route rejects access;
6. records HTTP access failures as evidence rather than treating missing archive inspection as success;
7. if either route later succeeds, transiently verifies archive hashes, ZIP CRC, path safety and member limits;
8. if source bytes become available, requires `Fig2_Data`, `Fig3_Data` and `Fig4_Data` before supporting experimental/simulation partition claims;
9. deletes all source bytes before publishing metadata evidence;
10. keeps inference, parameter tuning, model retraining and phase indexing disabled.

A controlled environment may provide `DRYAD_API_TOKEN` through an environment variable. Tokens must never be committed, logged or added to the case configuration.

## Scientific boundary

Even a future successful archive run would not establish:

- direct detector-export provenance of TIFF/BMP files;
- pattern centre, camera length, pixel geometry or reciprocal calibration;
- authoritative acquisition IDs and spatial pairing;
- complete preprocessing history for spreadsheets and line profiles;
- independence from analyzer development;
- calibrated d-spacing, phase or zone-axis indexing accuracy.

No analyzer inference, tuning, retraining, pixel export or phase indexing is authorized by this audit.

## Run

```bash
python scripts/audit_dryad_tise2_saed.py \
  --config case_studies/dryad_tise2_saed_source_audit/case_config.json \
  --output outputs/dryad_tise2_saed_source_audit
```

The output directory must be absent or empty.

Expected access-blocked evidence:

- `dryad_tise2_saed_audit_summary.json`
- `dryad_tise2_saed_access_attempts.csv`
- `dryad_tise2_saed_audit_report.md`
- `dryad_tise2_saed_audit_manifest.json`

If authenticated source access later succeeds, the access-attempt CSV is replaced by a member inventory while the same scientific limitations remain in force.
