# Dryad TiSe2 SAED/HRTEM source audit

This case audits Dryad dataset `10.5061/dryad.6djh9w1hw`, published for *Revisiting the charge-density-wave superlattice of 1T-TiSe2*.

The source is useful because the repository description explicitly separates experimental diffraction patterns from simulated patterns:

- `Fig2_Data/`: experimental SAED along `[1-10]` and `[001]` zone axes;
- `Fig3_Data/`: simulations based on the Di Salvo et al. structure;
- `Fig4_Data/`: simulations for proposed displacement models;
- supplementary folders: additional diffraction, profiles, real-space imaging and calculations.

The dataset is a cross-material static-SAED diagnostic source. It is not cobalt oxide and cannot validate the current Co3O4 TEM segmentation model.

## Bounded live audit

The workflow:

1. resolves the DOI through the official Dryad API;
2. verifies the dataset title and required top-level files;
3. downloads `Data_TiSe2.zip` into transient storage;
4. computes observed MD5 and SHA-256 and runs ZIP CRC validation;
5. rejects unsafe paths, links, duplicates, oversized members and excessive compression ratios;
6. inventories members without exporting pixels;
7. classifies `Fig2_Data` as experimental and `Fig3_Data`/`Fig4_Data` as simulation;
8. verifies that both partitions contain raster images;
9. records unresolved calibration and acquisition-lineage requirements;
10. deletes the source archive and publishes only JSON, CSV, Markdown and a checksum manifest.

## Scientific boundary

A valid run supports archive identity, archive integrity and the repository-level experimental/simulation partition. It does not establish:

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
