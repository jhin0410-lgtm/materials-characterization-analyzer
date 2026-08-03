# TEM External-Validation Candidate Registry

This case study records a dated public-source search for an untouched cobalt-oxide TEM/HRTEM segmentation evaluation set.

It separates target training data, exact-material processed diagnostics, rendered figures, cross-material/cross-phase microscopy, and wrong-modality records. Repository or author separation alone never proves acquisition independence.

Run:

```bash
mca tem-candidates \
  --config case_studies/tem_external_validation_candidate_registry/case_config.json \
  --output outputs/tem_external_validation_candidate_registry
```

Outputs are the candidate inventory, summary, report, annotation-protocol template, and checksum manifest.

## Source snapshot

The registry was refreshed on 2026-08-03 from official records and checksum-bound audits:

- Zenodo `10.5281/zenodo.14927582`: target cobalt-oxide TEM source and training files; excluded as the target source.
- Zenodo `10.5281/zenodo.17336678`: one Co3O4 nanoparticle tilt series in `Co3O4_denoised_tilt_series.h5`; exact-material but motion-corrected, tilt-aligned, denoised, single-particle, creator-overlapping, and not independently labeled.
- Dryad `10.7941/D1SP93`: Au/Ag/CdSe HRTEM image-label pairs; cross-material only.
- Mendeley Data `10.17632/8w66synjmx.1`: rendered RGB CoP/Co2P/Co3O4 publication figures, not raw detector data.
- Zenodo `10.5281/zenodo.14868077`: cobalt-hydroxide/ionomer cryo-TEM; cross-phase and unlabeled.
- Zenodo `10.5281/zenodo.11161891`: cobalt-tungstate STEM/TEM; cross-phase only.
- Zenodo `10.5281/zenodo.7941248`: Co3O4 SEM/XPS/HAXPES; wrong modality.
- Zenodo `10.5281/zenodo.14160831`: Co3O4/NiO TEM/STEM is reported in the publication, but the public record contains only `replication_package.xlsx`; wrong public modality.
- Mendeley Data `10.17632/kkk76z8g8z.1`: the checksum-bound current archive contains 760 members and only three SEM PNG images; no deposited TEM/HRTEM files.

## Current conclusion

No assessed public candidate is ready for in-domain external validation. PhaseT3M is the best exact-material processed diagnostic source, not an evaluation set. It may support checksum/HDF5 ingestion and processed-representation robustness checks only.

Readiness still requires raw or demonstrably lossless TEM/HRTEM from at least two independent samples/acquisitions, immutable lineage, explicit reuse terms, verified target-model non-use and content disjointness, and at least two blinded independent labels plus adjudication.

The annotation protocol remains a template and must not be frozen around PhaseT3M.
