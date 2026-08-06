# Zenodo W-Ta-Cr-V TEM/SAED source audit

This case audits Zenodo record `10.5281/zenodo.10512463`, which describes raw
cross-sectional TEM images, selected-area electron diffraction patterns and EDS
elemental maps for a W-Ta-Cr-V refractory high-entropy alloy in as-deposited and
He-irradiated conditions.

## Verified source snapshot

The live audit verified:

- official Zenodo licence identifier: `odc-odbl`;
- archive: `D_Kalita_NME.zip`;
- archive bytes: `729,576,221`;
- repository MD5: `2d3db56126bb936844c9d817b0a01f4c`;
- observed SHA-256: `4f05691c5a2abb51cb6bba91fbeeecec5faffa22cd6d937d0f459eb419533bad`;
- 48 regular members and `729,566,169` uncompressed bytes;
- 27 TIFF, 13 BMP, 2 DM3, 3 DM4, 2 XLSX and 1 DOCX files;
- 39 TEM-folder and 6 SEM-folder members;
- 3 SAED-name and 17 EDS-name cues;
- 18 as-deposited/unirradiated and 7 irradiated-condition cues, classified
  mutually exclusively;
- five native DigitalMicrograph containers with version-specific headers:
  two DM3 version-3 and three DM4 version-4 files, all with byte-order marker `1`;
- no camera-length, reciprocal-calibration or pattern-centre evidence in the
  bounded raster-header sample.

The three native SAED-bearing files are:

- `TEM/SAED_HF_irradiated area.dm4`;
- `TEM/SAED_HF_unirradiated area.dm4`;
- `TEM/TEM_SAED_as-deposited.dm3`.

## Bounded audit

The workflow:

1. verifies the official Zenodo API record, DOI, resource type, licence, title and
   description terms;
2. binds the target file to the repository MD5;
3. downloads the archive into transient storage and records its observed SHA-256;
4. performs a fail-closed `7z` integrity and member-safety audit;
5. inventories all regular members and preserves SEM/TEM, SAED/EDS and
   as-deposited/irradiated filename cues without joining files by row order;
6. extracts only a bounded set of TEM-folder files for streaming identity hashing
   and at-most-32-byte file-header inspection;
7. applies separate DM3 and DM4 header layouts and prevents `unirradiated` paths
   from being double-classified as irradiated;
8. deletes all source bytes before publishing metadata-only evidence.

## Scientific boundary

The deposit is valuable for cross-material static-SAED, native-format and
radiation-damage software diagnostics, but it is not a cobalt-oxide validation
cohort. Filename and folder cues do not establish specimen or acquisition identity.
A native container or TIFF file does not by itself prove detector-native intensity
preservation, calibrated reciprocal spacing, acquisition independence or complete
as-deposited-to-irradiated specimen pairing.

The audit does not export pixels, preprocess images, run the analyzer, annotate,
phase-index, tune parameters, retrain models or support engineering decisions.
Calibrated-SAED validation and external scientific validation remain false.

## Run

```bash
sudo apt-get update
sudo apt-get install -y p7zip-full
python -m pip install pillow

python -m scripts.run_zenodo_wtacrv_tem_saed_audit \
  --config case_studies/zenodo_wtacrv_tem_saed_source_audit/case_config.json \
  --output outputs/zenodo_wtacrv_tem_saed_source_audit
```

The output directory must be absent or empty.
