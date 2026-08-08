from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ARTICLE_DOI = "10.1038/s41586-026-10823-x"
ARTICLE_TITLE = "Imaging of nanoscale polar textures in quantum paraelectric SrTiO3"
ARTICLE_URL = "https://www.nature.com/articles/s41586-026-10823-x"
ZENODO_DOI = "10.5281/zenodo.20300700"


class SrTiO3PublicationProvenanceError(RuntimeError):
    """Raised when the SrTiO3 publication-provenance contract is violated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SrTiO3PublicationProvenanceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise SrTiO3PublicationProvenanceError(f"invalid JSON: {resolved}") from exc
    if not isinstance(payload, dict):
        raise SrTiO3PublicationProvenanceError(f"JSON root must be an object: {resolved}")
    return payload


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_repo_path(value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise SrTiO3PublicationProvenanceError("repository evidence path must be a string")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise SrTiO3PublicationProvenanceError("configured repository evidence path is unsafe")
    resolved = (PROJECT_ROOT / candidate).resolve(strict=True)
    if PROJECT_ROOT not in resolved.parents:
        raise SrTiO3PublicationProvenanceError("repository evidence resolved outside project root")
    return resolved


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "case_id",
        "audit_date",
        "publication",
        "repository_evidence",
        "expected_saed_members",
        "scientific_boundary",
        "decision_rules",
    }
    if set(config) != required or config.get("schema_version") != "1.0":
        raise SrTiO3PublicationProvenanceError(
            "publication provenance config keys/schema do not match contract"
        )

    publication = config.get("publication")
    if not isinstance(publication, dict) or set(publication) != {
        "doi",
        "title",
        "url",
        "evidence_snapshot",
    }:
        raise SrTiO3PublicationProvenanceError("publication contract is invalid")
    if publication.get("doi") != ARTICLE_DOI:
        raise SrTiO3PublicationProvenanceError("publication DOI drifted")
    if publication.get("title") != ARTICLE_TITLE:
        raise SrTiO3PublicationProvenanceError("publication title drifted")
    if publication.get("url") != ARTICLE_URL:
        raise SrTiO3PublicationProvenanceError("publication URL drifted")
    _resolve_repo_path(publication.get("evidence_snapshot"))

    evidence = config.get("repository_evidence")
    expected_evidence_keys = {
        "metadata_snapshot",
        "remote_inventory_snapshot",
        "tiff_metadata_snapshot",
        "prepixel_metadata_snapshot",
        "notebook_provenance_snapshot",
    }
    if not isinstance(evidence, dict) or set(evidence) != expected_evidence_keys:
        raise SrTiO3PublicationProvenanceError("repository_evidence contract is invalid")
    for path in evidence.values():
        _resolve_repo_path(path)

    members = config.get("expected_saed_members")
    expected_members = {
        "SAED/23K.tif": 23,
        "SAED/91K.tif": 91,
        "SAED/172K.tif": 172,
    }
    if not isinstance(members, list) or len(members) != 3:
        raise SrTiO3PublicationProvenanceError("expected_saed_members must contain three entries")
    observed_members: dict[str, int] = {}
    for item in members:
        if not isinstance(item, dict) or set(item) != {"path", "temperature_k"}:
            raise SrTiO3PublicationProvenanceError("expected SAED member entry is invalid")
        path = item.get("path")
        temperature = item.get("temperature_k")
        if not isinstance(path, str) or not isinstance(temperature, int):
            raise SrTiO3PublicationProvenanceError("expected SAED member types are invalid")
        observed_members[path] = temperature
    if observed_members != expected_members:
        raise SrTiO3PublicationProvenanceError("expected SAED member/temperature mapping drifted")

    boundary = config.get("scientific_boundary")
    if not isinstance(boundary, dict) or not boundary:
        raise SrTiO3PublicationProvenanceError("scientific_boundary must be a non-empty object")
    if any(value is not False for value in boundary.values()):
        raise SrTiO3PublicationProvenanceError(
            "network/pixel/analyzer/figure-image actions must remain disabled"
        )
    rules = config.get("decision_rules")
    if not isinstance(rules, dict) or not rules or any(value is not True for value in rules.values()):
        raise SrTiO3PublicationProvenanceError("all fail-closed publication rules must be enabled")
    return config


def _validate_publication_snapshot(path: Path) -> dict[str, Any]:
    snapshot = _load_json(path)
    expected_fields = {
        "schema_version",
        "snapshot_id",
        "captured_at",
        "capture_method",
        "raw_publication_html_retained",
        "raw_publication_pdf_retained",
        "published_figure_image_retained",
        "source",
        "claims",
        "interpretation",
        "scientific_boundaries",
        "restart_or_recheck_conditions",
    }
    if set(snapshot) != expected_fields or snapshot.get("schema_version") != "1.0":
        raise SrTiO3PublicationProvenanceError("publication evidence snapshot schema drifted")
    if snapshot.get("capture_method") != "manual_authoritative_publication_review":
        raise SrTiO3PublicationProvenanceError("publication capture method is not authoritative manual review")
    for field in (
        "raw_publication_html_retained",
        "raw_publication_pdf_retained",
        "published_figure_image_retained",
    ):
        if snapshot.get(field) is not False:
            raise SrTiO3PublicationProvenanceError(f"publication snapshot retained prohibited raw source: {field}")

    source = snapshot.get("source")
    if not isinstance(source, Mapping):
        raise SrTiO3PublicationProvenanceError("publication source record is invalid")
    if source.get("doi") != ARTICLE_DOI or source.get("title") != ARTICLE_TITLE:
        raise SrTiO3PublicationProvenanceError("publication identity in snapshot drifted")
    if source.get("article_url") != ARTICLE_URL:
        raise SrTiO3PublicationProvenanceError("publication article URL in snapshot drifted")
    if source.get("publication_date") != "2026-07-22" or source.get("journal") != "Nature":
        raise SrTiO3PublicationProvenanceError("publication date/journal in snapshot drifted")

    claims = snapshot.get("claims")
    expected_claims = {
        "figure_1d_temperatures_k": [23, 91, 172],
        "figure_1d_reciprocal_scale_bar_inv_angstrom": 0.1,
        "figure_1d_afd_superspot_assignment": "half-integer positions",
        "extended_data_diffraction_temperature_range_k": [23, 215],
        "data_availability_zenodo_doi": ZENODO_DOI,
    }
    if claims != expected_claims:
        raise SrTiO3PublicationProvenanceError("publication scientific claims drifted")

    interpretation = snapshot.get("interpretation")
    expected_interpretation = {
        "publication_identity": "Supported",
        "publication_to_zenodo_record_binding": "Supported",
        "saed_temperature_label_semantics": "Supported",
        "published_figure_scale_bar": "Supported",
        "source_author_afd_assignment": "Diagnostic",
        "exact_source_tiff_to_figure_panel_identity": "Diagnostic",
        "source_tiff_reciprocal_calibration": "Inconclusive",
        "source_tiff_pattern_center": "Inconclusive",
        "saed_acquisition_independence": "Inconclusive",
        "detector_native_intensity_provenance": "Inconclusive",
        "complete_phase_indexing_truth": "Inconclusive",
        "external_validation_readiness": "Inconclusive",
    }
    if interpretation != expected_interpretation:
        raise SrTiO3PublicationProvenanceError("publication evidence interpretation drifted")
    if not isinstance(snapshot.get("scientific_boundaries"), list) or not snapshot["scientific_boundaries"]:
        raise SrTiO3PublicationProvenanceError("publication scientific boundaries are missing")
    if not isinstance(snapshot.get("restart_or_recheck_conditions"), list) or not snapshot[
        "restart_or_recheck_conditions"
    ]:
        raise SrTiO3PublicationProvenanceError("publication recheck conditions are missing")
    return snapshot


def _validate_repository_evidence(config: Mapping[str, Any]) -> dict[str, Any]:
    paths = {
        name: _resolve_repo_path(path)
        for name, path in config["repository_evidence"].items()
    }
    snapshots = {name: _load_json(path) for name, path in paths.items()}

    metadata = snapshots["metadata_snapshot"]
    source = metadata.get("source")
    if metadata.get("execution_status") != "metadata_audit_completed":
        raise SrTiO3PublicationProvenanceError("metadata snapshot is not completed")
    if not isinstance(source, Mapping) or source.get("record_id") != 20300700:
        raise SrTiO3PublicationProvenanceError("metadata snapshot is not the pinned Zenodo record")
    if source.get("doi") != ZENODO_DOI:
        raise SrTiO3PublicationProvenanceError("metadata Zenodo DOI drifted")

    expected_paths = [item["path"] for item in config["expected_saed_members"]]
    remote = snapshots["remote_inventory_snapshot"]
    inventory = remote.get("inventory_summary")
    if remote.get("execution_status") != "remote_central_directory_inventory_completed":
        raise SrTiO3PublicationProvenanceError("remote inventory is not completed")
    if not isinstance(inventory, Mapping) or not isinstance(inventory.get("member_paths"), list):
        raise SrTiO3PublicationProvenanceError("remote inventory member paths are invalid")
    if any(path not in inventory["member_paths"] for path in expected_paths):
        raise SrTiO3PublicationProvenanceError("expected SAED TIFF is absent from remote inventory")

    tiff = snapshots["tiff_metadata_snapshot"]
    common = tiff.get("common_tiff_structure")
    readiness = tiff.get("readiness")
    tiff_members = tiff.get("members")
    if tiff.get("case_id") != "zenodo_srtio3_saed_tiff_metadata":
        raise SrTiO3PublicationProvenanceError("TIFF metadata case identity drifted")
    if not isinstance(common, Mapping) or common.get("ImageWidth") != 2048 or common.get("ImageLength") != 2048:
        raise SrTiO3PublicationProvenanceError("TIFF dimensions differ from verified evidence")
    if not isinstance(readiness, Mapping) or readiness.get("pixel_access_authorized") is not False:
        raise SrTiO3PublicationProvenanceError("TIFF pixel-access boundary drifted")
    if common.get("StripOffsets") != 272:
        raise SrTiO3PublicationProvenanceError("TIFF first-pixel offset drifted")
    if not isinstance(tiff_members, list) or [
        item.get("path") for item in tiff_members if isinstance(item, Mapping)
    ] != expected_paths:
        raise SrTiO3PublicationProvenanceError("TIFF member order/identity differs from contract")

    prepixel = snapshots["prepixel_metadata_snapshot"]
    text_metadata = prepixel.get("common_text_metadata")
    range_evidence = prepixel.get("range_evidence")
    if prepixel.get("case_id") != "zenodo_srtio3_saed_prepixel_metadata":
        raise SrTiO3PublicationProvenanceError("pre-pixel metadata case identity drifted")
    if not isinstance(text_metadata, Mapping) or not isinstance(range_evidence, Mapping):
        raise SrTiO3PublicationProvenanceError("pre-pixel evidence structure is invalid")
    software = text_metadata.get("Software")
    if not isinstance(software, Mapping) or software.get("text") != "tifffile.py":
        raise SrTiO3PublicationProvenanceError("TIFF serialization evidence drifted")
    if range_evidence.get("pixel_bytes_decompressed") != 0:
        raise SrTiO3PublicationProvenanceError("pre-pixel audit unexpectedly accessed pixels")

    notebook = snapshots["notebook_provenance_snapshot"]
    search = notebook.get("search_summary")
    if notebook.get("case_id") != "zenodo_srtio3_notebook_provenance" or not isinstance(search, Mapping):
        raise SrTiO3PublicationProvenanceError("notebook provenance evidence drifted")
    for field in (
        "explicit_saed_term_hits",
        "explicit_23K_hits",
        "explicit_91K_hits",
        "explicit_172K_hits",
    ):
        if search.get(field) != 0:
            raise SrTiO3PublicationProvenanceError(
                "notebook evidence unexpectedly acquired direct SAED/temperature linkage"
            )

    return {
        "record_id": 20300700,
        "doi": ZENODO_DOI,
        "saed_archive_key": "SAED.zip",
        "saed_member_paths": expected_paths,
        "tiff_shape": [2048, 2048],
        "tiff_storage": "float64",
        "tiff_serialization_software": "tifffile.py",
        "verified_first_pixel_strip_offset": 272,
        "notebook_explicit_saed_or_temperature_hits": 0,
        "snapshot_sha256": {name: _sha256_file(path) for name, path in paths.items()},
    }


def run_audit(*, config_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = _validate_config(_load_json(config_resolved))
    publication_snapshot_path = _resolve_repo_path(config["publication"]["evidence_snapshot"])
    publication_snapshot = _validate_publication_snapshot(publication_snapshot_path)
    repository_binding = _validate_repository_evidence(config)

    claims = publication_snapshot["claims"]
    interpretation = publication_snapshot["interpretation"]
    if claims["data_availability_zenodo_doi"] != repository_binding["doi"]:
        raise SrTiO3PublicationProvenanceError(
            "publication data-availability DOI does not match repository Zenodo evidence"
        )
    expected_temperatures = [item["temperature_k"] for item in config["expected_saed_members"]]
    if claims["figure_1d_temperatures_k"] != expected_temperatures:
        raise SrTiO3PublicationProvenanceError(
            "publication temperatures do not match the configured SAED labels"
        )

    result = {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "execution_status": "publication_provenance_audit_completed",
        "config_sha256": _sha256_file(config_resolved),
        "network_access_performed": False,
        "publication": {
            "doi": ARTICLE_DOI,
            "title": ARTICLE_TITLE,
            "source_url": ARTICLE_URL,
            "capture_method": publication_snapshot["capture_method"],
            "captured_at": publication_snapshot["captured_at"],
            "evidence_snapshot_sha256": _sha256_file(publication_snapshot_path),
            "raw_publication_html_retained": False,
            "raw_publication_pdf_retained": False,
            "published_figure_image_retained": False,
        },
        "repository_binding": repository_binding,
        "supported_publication_facts": {
            "figure_1d_temperatures_k": claims["figure_1d_temperatures_k"],
            "figure_1d_reciprocal_scale_bar_inv_angstrom": claims[
                "figure_1d_reciprocal_scale_bar_inv_angstrom"
            ],
            "figure_1d_afd_superspot_assignment": claims[
                "figure_1d_afd_superspot_assignment"
            ],
            "extended_data_diffraction_temperature_range_k": claims[
                "extended_data_diffraction_temperature_range_k"
            ],
            "final_article_data_availability_zenodo_doi": claims[
                "data_availability_zenodo_doi"
            ],
        },
        "evidence_assessment": {
            "final_publication_identity": interpretation["publication_identity"],
            "publication_to_zenodo_record_binding": interpretation[
                "publication_to_zenodo_record_binding"
            ],
            "saed_filename_temperature_semantics": interpretation[
                "saed_temperature_label_semantics"
            ],
            "published_figure_1d_reciprocal_scale_bar": interpretation[
                "published_figure_scale_bar"
            ],
            "source_author_afd_superspot_assignment": interpretation[
                "source_author_afd_assignment"
            ],
            "exact_tiff_byte_to_figure_panel_binding": interpretation[
                "exact_source_tiff_to_figure_panel_identity"
            ],
            "source_tiff_pixel_to_reciprocal_scale_calibration": interpretation[
                "source_tiff_reciprocal_calibration"
            ],
            "source_tiff_pattern_center": interpretation["source_tiff_pattern_center"],
            "saed_acquisition_independence": interpretation["saed_acquisition_independence"],
            "detector_native_intensity_provenance": interpretation[
                "detector_native_intensity_provenance"
            ],
            "complete_reference_truth_for_phase_indexing": interpretation[
                "complete_phase_indexing_truth"
            ],
            "external_validation_readiness": interpretation["external_validation_readiness"],
            "scientific_evidence_level": "Diagnostic",
        },
        "readiness": {
            "temperature_semantics_resolved": True,
            "bounded_source_to_published_figure_mapping_can_be_predeclared": True,
            "saed_tiff_pixel_access_authorized": False,
            "published_figure_image_download_authorized": False,
            "image_registration_authorized": False,
            "four_d_stem_download_authorized": False,
            "analyzer_execution_authorized": False,
            "phase_indexing_authorized": False,
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "next_evidence": {
            "priority": 1,
            "requirement": (
                "predeclared_bounded_source_tiff_to_published_figure1d_identity_and_"
                "reciprocal_scale_mapping"
            ),
            "why": (
                "The final publication resolves the 23K/91K/172K temperature semantics and "
                "provides a 0.1 inverse-angstrom scale bar for the displayed patterns, but the "
                "source TIFF pixels are not yet byte-to-panel bound or calibrated."
            ),
            "pixel_access_requires_separate_contract": True,
            "four_d_stem_access_required": False,
        },
        "scientific_boundary": list(publication_snapshot["scientific_boundaries"]),
        "software_validation_boundary": (
            "This no-network audit validates the integrity and consistency of a manually curated "
            "authoritative-publication evidence snapshot. It does not independently re-fetch or "
            "re-parse the Nature article in CI."
        ),
    }

    output = Path(output_path).expanduser().resolve(strict=False)
    if output.exists():
        raise SrTiO3PublicationProvenanceError(f"refusing to overwrite output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the checksum-bound final-publication evidence snapshot against the existing "
            "SrTiO3 Zenodo/SAED provenance chain without network or pixel access."
        )
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = run_audit(config_path=args.config, output_path=args.output)
    except (SrTiO3PublicationProvenanceError, FileNotFoundError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
