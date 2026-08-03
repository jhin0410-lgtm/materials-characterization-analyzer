# Co3O4 Public TEM Candidate Audit

This case study verifies two public records that appear relevant to independent cobalt-oxide TEM validation but do not expose usable TEM/HRTEM source arrays.

## Sources

- Zenodo `10.5281/zenodo.14160831`: the associated study reports cross-sectional TEM/STEM for Co3O4/NiO bilayers, but the public record contains only `replication_package.xlsx`.
- Mendeley Data `10.17632/kkk76z8g8z.1`: the article reports TEM observations for Co3O4-containing samples, but the checksum-bound current `Data.rar` contains 760 members and only three decodable images, all under `Data/SEM/`.

The audit distinguishes microscopy described in a publication from microscopy arrays actually deposited in the public data record.

Mendeley file UUIDs are treated as mutable download-routing metadata, not scientific source identity. Reproducible source identity is bound to the versioned dataset, archive filename, byte count, SHA-256, and extracted representation.

## Reproducibility contract

`case_config.json` pins the source records, archive content identity, expected archive-member count, and the three observed SEM image paths. The GitHub workflow:

1. retrieves official Zenodo and Mendeley metadata;
2. fails if the record, licence, archive filename, byte count, SHA-256, or extracted representation changes;
3. downloads only the bounded 16.25 MB Mendeley archive;
4. verifies its SHA-256 before extraction;
5. checks the member count and image representation;
6. confirms that no deposited TEM/HRTEM image is present;
7. deletes the archive and extracted files;
8. runs the public TEM candidate registry and verifies both records remain wrong-modality exclusions;
9. uploads metadata-only evidence.

## Scientific boundary

This audit does not run segmentation inference, create labels, estimate model accuracy, or authorize retraining. It supports only the conclusion that the assessed public snapshots do not provide an independent cobalt-oxide TEM/HRTEM validation cohort.

The records should be reconsidered only if a new immutable release deposits checksum-bound detector or demonstrably lossless TEM/HRTEM files with sample/acquisition lineage and target-model non-use evidence.
