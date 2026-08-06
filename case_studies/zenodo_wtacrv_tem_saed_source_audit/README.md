# Zenodo W-Ta-Cr-V TEM/SAED source audit

This case audits Zenodo record `10.5281/zenodo.10512463`, which describes raw
cross-sectional TEM images, selected-area electron diffraction patterns and EDS
elemental maps for a W-Ta-Cr-V refractory high-entropy alloy in as-deposited and
He-irradiated conditions.

## Bounded audit

The workflow:

1. verifies the official Zenodo API record, DOI, resource type, licence, title and
   description terms;
2. binds the target file `D_Kalita_NME.zip` to repository MD5
   `2d3db56126bb936844c9d817b0a01f4c`;
3. downloads the archive into transient storage and records its observed SHA-256;
4. performs a fail-closed `7z` integrity and member-safety audit;
5. inventories all regular members and preserves SEM/TEM, SAED/EDS and
   as-deposited/irradiated filename cues;
6. extracts only a bounded set of TEM-folder files for identity hashing and file-
   header inspection;
7. deletes all source bytes before publishing metadata-only evidence.

## Scientific boundary

The deposit is valuable for cross-material static-SAED and radiation-damage
software diagnostics, but it is not a cobalt-oxide validation cohort. Filename and
folder cues do not establish specimen or acquisition identity. A native container
or TIFF file does not by itself prove detector-native intensity preservation,
calibrated reciprocal spacing or acquisition independence.

The audit does not export pixels, preprocess images, run the analyzer, annotate,
phase-index, tune parameters, retrain models or support engineering decisions.

## Run

```bash
sudo apt-get update
sudo apt-get install -y p7zip-full
python -m pip install pillow

python scripts/audit_zenodo_wtacrv_tem_saed.py \
  --config case_studies/zenodo_wtacrv_tem_saed_source_audit/case_config.json \
  --output outputs/zenodo_wtacrv_tem_saed_source_audit
```

The output directory must be absent or empty.
