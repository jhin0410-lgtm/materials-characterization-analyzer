# TEM External-Validation Candidate Registry

This case study records a dated public-source search for an untouched cobalt-oxide TEM/HRTEM segmentation evaluation set.

It deliberately separates:

- exact target training/source data, which cannot be reused as external validation;
- target-containing or related cobalt-phase images that still lack file-level provenance or independent labels;
- human-labeled HRTEM data from other materials, which can support only cross-material diagnostics;
- cobalt-oxide data from the wrong microscopy modality.

Run:

```bash
mca tem-candidates \
  --config case_studies/tem_external_validation_candidate_registry/case_config.json \
  --output outputs/tem_external_validation_candidate_registry
```

Outputs:

- `tem_external_validation_candidate_inventory.csv`
- `tem_external_validation_candidate_summary.json`
- `tem_external_validation_candidate_report.md`
- `tem_external_validation_annotation_protocol.json`
- `tem_external_validation_candidate_manifest.json`

## Source snapshot

The registry was assembled on 2026-08-01 from official repository records:

- Zenodo `10.5281/zenodo.14927582`: target cobalt-oxide TEM source and training files.
- Dryad `10.7941/D1SP93`: Au/Ag/CdSe HRTEM image-label pairs; single human labeler.
- Mendeley Data `10.17632/8w66synjmx.1`: raw TEM is reported for a CoP/Co2P/Co3O4 heterojunction, but the assessed landing page did not expose a file inventory.
- Zenodo `10.5281/zenodo.14868077`: three low-dose cobalt-hydroxide/ionomer cryo-TEM TIFF files with MD5 values; no segmentation labels.
- Zenodo `10.5281/zenodo.11161891`: cobalt-tungstate STEM/TEM files with MD5 values; not cobalt-oxide in-domain data.
- Zenodo `10.5281/zenodo.7941248`: Co3O4 SEM/XPS/HAXPES data; excluded for wrong modality.

This is a time-bounded and non-exhaustive search snapshot. Repository or author separation alone does not prove sample/acquisition independence.

## Current conclusion

No assessed public candidate is ready for in-domain external validation. The highest-priority unresolved lead is the Mendeley CoP/Co2P/Co3O4 dataset because it reports target-containing raw TEM data, but its exact TEM file inventory, checksums, sample identity, acquisition lineage, and independent labels must be resolved before use.

The emitted annotation protocol is a template only. It must not be frozen until candidate files and lineage have been audited.

## Readiness integration

After generating the registry, pass its summary to the consolidated readiness command:

```bash
mca tem-readiness \
  --training-summary path/to/training_data_readiness_summary.json \
  --parent-overlap-summary path/to/parent_overlap_audit_summary.json \
  --candidate-registry-summary outputs/tem_external_validation_candidate_registry/tem_external_validation_candidate_summary.json \
  --output outputs/tem_segmentation_readiness_with_registry
```

The registry refines the next action but cannot by itself grant scientific evaluation readiness. Image files, sample/acquisition lineage, independent labels, verified non-use, and content-overlap clearance still require separate evidence.
