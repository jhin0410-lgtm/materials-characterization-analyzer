from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import audit_zenodo_srtio3_saed_publication_provenance as audit

CONFIG_PATH = Path("case_studies/zenodo_srtio3_saed_publication_provenance/case_config.json")
PUBLICATION_URL = "https://www.nature.com/articles/s41586-026-10823-x"


def _config_payload() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _fixture_html(*, include_temperature_claim: bool = True) -> bytes:
    temperature = (
        "Electron diffraction patterns collected at 23 K (left), 91 K (middle) and 172 K (right)."
        if include_temperature_claim
        else "Electron diffraction patterns were collected at cryogenic temperatures."
    )
    return f"""<!doctype html>
    <html><head><title>Imaging of nanoscale polar textures in quantum paraelectric SrTiO3</title></head>
    <body>
      <h1>Imaging of nanoscale polar textures in quantum paraelectric SrTiO3</h1>
      <p>doi: 10.1038/s41586-026-10823-x</p>
      <p>{temperature} Black arrows mark the AFD superspots located at half-integer positions.
      Scale bars, 0.1 Å−1.</p>
      <p>Electron diffraction patterns collected from 23 to 215 K.</p>
      <section>Data availability: https://doi.org/10.5281/zenodo.20300700</section>
      <script>SAED pixel data should never be sourced from script text.</script>
    </body></html>""".encode("utf-8")


def test_config_keeps_all_pixel_and_inference_actions_disabled() -> None:
    config = audit._validate_config(_config_payload())
    boundary = config["scientific_boundary"]
    assert boundary["publication_html_request_authorized"] is True
    assert boundary["publication_text_normalization_authorized"] is True
    assert boundary["saed_archive_download_authorized"] is False
    assert boundary["saed_tiff_pixel_access_authorized"] is False
    assert boundary["published_figure_image_download_authorized"] is False
    assert boundary["image_registration_authorized"] is False
    assert boundary["analyzer_inference_authorized"] is False
    assert boundary["phase_indexing_authorized"] is False


def test_visible_text_ignores_script_and_normalizes_units() -> None:
    text = audit._visible_text(_fixture_html())
    assert "electron diffraction patterns collected at 23 k" in text
    assert "0.1 å-1" in text
    assert "script text" not in text


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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _fixture_html()
    monkeypatch.setattr(
        audit,
        "_download_publication",
        lambda url, maximum_bytes: (payload, PUBLICATION_URL),
    )

    output = tmp_path / "publication_provenance_snapshot.json"
    result = audit.run_audit(config_path=CONFIG_PATH, output_path=output)

    assert result["execution_status"] == "publication_provenance_audit_completed"
    assert result["supported_publication_facts"]["figure_1d_temperatures_k"] == [23, 91, 172]
    assert result["supported_publication_facts"][
        "figure_1d_reciprocal_scale_bar_inv_angstrom"
    ] == 0.1
    evidence = result["evidence_assessment"]
    assert evidence["publication_to_zenodo_record_binding"] == "Supported"
    assert evidence["saed_filename_temperature_semantics"] == "Supported"
    assert evidence["published_figure_1d_reciprocal_scale_bar"] == "Supported"
    assert evidence["exact_tiff_byte_to_figure_panel_binding"] == "Diagnostic"
    assert evidence["source_tiff_pixel_to_reciprocal_scale_calibration"] == "Inconclusive"
    assert evidence["source_tiff_pattern_center"] == "Inconclusive"
    assert evidence["saed_acquisition_independence"] == "Inconclusive"
    readiness = result["readiness"]
    assert readiness["temperature_semantics_resolved"] is True
    assert readiness["bounded_source_to_published_figure_mapping_can_be_predeclared"] is True
    assert readiness["saed_tiff_pixel_access_authorized"] is False
    assert readiness["published_figure_image_download_authorized"] is False
    assert readiness["phase_indexing_authorized"] is False
    assert readiness["external_validation_ready"] is False
    assert result["next_evidence"]["pixel_access_requires_separate_contract"] is True
    assert output.is_file()


def test_missing_temperature_claim_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _fixture_html(include_temperature_claim=False)
    monkeypatch.setattr(
        audit,
        "_download_publication",
        lambda url, maximum_bytes: (payload, PUBLICATION_URL),
    )

    with pytest.raises(
        audit.SrTiO3PublicationProvenanceError,
        match="figure_1d_temperature_sequence",
    ):
        audit.run_audit(
            config_path=CONFIG_PATH,
            output_path=tmp_path / "publication_provenance_snapshot.json",
        )


def test_output_is_never_overwritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _fixture_html()
    monkeypatch.setattr(
        audit,
        "_download_publication",
        lambda url, maximum_bytes: (payload, PUBLICATION_URL),
    )
    output = tmp_path / "publication_provenance_snapshot.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(audit.SrTiO3PublicationProvenanceError, match="overwrite"):
        audit.run_audit(config_path=CONFIG_PATH, output_path=output)
