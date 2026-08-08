from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import audit_zenodo_srtio3_saed_publication_provenance as audit

CONFIG_PATH = Path("case_studies/zenodo_srtio3_saed_publication_provenance/case_config.json")
PUBLICATION_SNAPSHOT_PATH = Path(
    "case_studies/zenodo_srtio3_saed_publication_provenance/verified_publication_claims_snapshot.json"
)


def _config_payload() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _publication_payload() -> dict:
    return json.loads(PUBLICATION_SNAPSHOT_PATH.read_text(encoding="utf-8"))


def test_config_keeps_network_pixel_and_inference_actions_disabled() -> None:
    config = audit._validate_config(_config_payload())
    assert config["publication"]["doi"] == audit.ARTICLE_DOI
    assert config["publication"]["title"] == audit.ARTICLE_TITLE
    boundary = config["scientific_boundary"]
    assert boundary
    assert all(value is False for value in boundary.values())
    assert boundary["publication_network_access_authorized"] is False
    assert boundary["saed_tiff_pixel_access_authorized"] is False
    assert boundary["published_figure_image_download_authorized"] is False
    assert boundary["image_registration_authorized"] is False
    assert boundary["analyzer_inference_authorized"] is False
    assert boundary["phase_indexing_authorized"] is False


def test_publication_snapshot_has_exact_supported_claims_and_no_raw_source() -> None:
    snapshot = audit._validate_publication_snapshot(PUBLICATION_SNAPSHOT_PATH.resolve())
    assert snapshot["capture_method"] == "manual_authoritative_publication_review"
    assert snapshot["raw_publication_html_retained"] is False
    assert snapshot["raw_publication_pdf_retained"] is False
    assert snapshot["published_figure_image_retained"] is False
    assert snapshot["source"]["doi"] == audit.ARTICLE_DOI
    assert snapshot["source"]["publication_date"] == "2026-07-22"
    assert snapshot["claims"] == {
        "figure_1d_temperatures_k": [23, 91, 172],
        "figure_1d_reciprocal_scale_bar_inv_angstrom": 0.1,
        "figure_1d_afd_superspot_assignment": "half-integer positions",
        "extended_data_diffraction_temperature_range_k": [23, 215],
        "data_availability_zenodo_doi": "10.5281/zenodo.20300700",
    }


def test_repository_binding_preserves_pre_pixel_boundary() -> None:
    config = audit._validate_config(_config_payload())
    binding = audit._validate_repository_evidence(config)

    assert binding["record_id"] == 20300700
    assert binding["doi"] == "10.5281/zenodo.20300700"
    assert binding["saed_member_paths"] == [
        "SAED/23K.tif",
        "SAED/91K.tif",
        "SAED/172K.tif",
    ]
    assert binding["tiff_shape"] == [2048, 2048]
    assert binding["tiff_storage"] == "float64"
    assert binding["tiff_serialization_software"] == "tifffile.py"
    assert binding["verified_first_pixel_strip_offset"] == 272
    assert binding["notebook_explicit_saed_or_temperature_hits"] == 0
    assert set(binding["snapshot_sha256"]) == {
        "metadata_snapshot",
        "remote_inventory_snapshot",
        "tiff_metadata_snapshot",
        "prepixel_metadata_snapshot",
        "notebook_provenance_snapshot",
    }


def test_audit_upgrades_temperature_semantics_without_calibration_promotion(
    tmp_path: Path,
) -> None:
    output = tmp_path / "publication_provenance_snapshot.json"
    result = audit.run_audit(config_path=CONFIG_PATH, output_path=output)

    assert result["execution_status"] == "publication_provenance_audit_completed"
    assert result["network_access_performed"] is False
    assert result["publication"]["capture_method"] == (
        "manual_authoritative_publication_review"
    )
    assert result["publication"]["raw_publication_html_retained"] is False
    assert result["publication"]["raw_publication_pdf_retained"] is False
    assert result["publication"]["published_figure_image_retained"] is False
    assert result["supported_publication_facts"]["figure_1d_temperatures_k"] == [
        23,
        91,
        172,
    ]
    assert result["supported_publication_facts"][
        "figure_1d_reciprocal_scale_bar_inv_angstrom"
    ] == 0.1

    evidence = result["evidence_assessment"]
    assert evidence["publication_to_zenodo_record_binding"] == "Supported"
    assert evidence["saed_filename_temperature_semantics"] == "Supported"
    assert evidence["published_figure_1d_reciprocal_scale_bar"] == "Supported"
    assert evidence["exact_tiff_byte_to_figure_panel_binding"] == "Diagnostic"
    assert evidence["source_tiff_pixel_to_reciprocal_scale_calibration"] == (
        "Inconclusive"
    )
    assert evidence["source_tiff_pattern_center"] == "Inconclusive"
    assert evidence["saed_acquisition_independence"] == "Inconclusive"

    readiness = result["readiness"]
    assert readiness["temperature_semantics_resolved"] is True
    assert readiness["bounded_source_to_published_figure_mapping_can_be_predeclared"] is True
    assert readiness["saed_tiff_pixel_access_authorized"] is False
    assert readiness["published_figure_image_download_authorized"] is False
    assert readiness["image_registration_authorized"] is False
    assert readiness["four_d_stem_download_authorized"] is False
    assert readiness["phase_indexing_authorized"] is False
    assert readiness["external_validation_ready"] is False
    assert result["next_evidence"]["pixel_access_requires_separate_contract"] is True
    assert "does not independently re-fetch" in result["software_validation_boundary"]
    assert output.is_file()


def test_mutated_publication_claim_fails_closed(tmp_path: Path) -> None:
    snapshot = _publication_payload()
    snapshot["claims"]["figure_1d_temperatures_k"] = [20, 91, 172]
    mutated = tmp_path / "publication.json"
    mutated.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(
        audit.SrTiO3PublicationProvenanceError,
        match="publication scientific claims drifted",
    ):
        audit._validate_publication_snapshot(mutated)


def test_retained_publication_source_fails_closed(tmp_path: Path) -> None:
    snapshot = _publication_payload()
    snapshot["raw_publication_html_retained"] = True
    mutated = tmp_path / "publication.json"
    mutated.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(
        audit.SrTiO3PublicationProvenanceError,
        match="retained prohibited raw source",
    ):
        audit._validate_publication_snapshot(mutated)


def test_output_is_never_overwritten(tmp_path: Path) -> None:
    output = tmp_path / "publication_provenance_snapshot.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(audit.SrTiO3PublicationProvenanceError, match="overwrite"):
        audit.run_audit(config_path=CONFIG_PATH, output_path=output)
