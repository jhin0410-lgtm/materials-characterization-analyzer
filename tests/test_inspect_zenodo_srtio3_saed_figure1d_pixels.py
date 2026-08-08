from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from scripts import inspect_zenodo_srtio3_saed_figure1d_pixels as inspect

CONFIG_PATH = Path(
    "case_studies/zenodo_srtio3_saed_figure1d_identity_mapping/evidence_contract.json"
)
SOURCE_SNAPSHOT_PATH = Path(
    "case_studies/zenodo_srtio3_saed_figure1d_identity_mapping/verified_pixel_source_snapshot.json"
)
MANUAL_REVIEW_PATH = Path(
    "case_studies/zenodo_srtio3_saed_figure1d_identity_mapping/manual_identity_review.json"
)


def _config_payload() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def test_contract_authorizes_only_bounded_pixel_inventory_operations() -> None:
    config = inspect._validate_config(_config_payload())
    operations = config["authorized_operations"]

    assert operations["download_exact_saed_archive"] is True
    assert operations["verify_archive_md5_before_member_decode"] is True
    assert operations["decode_exact_three_saed_tiff_arrays"] is True
    assert operations["download_exact_publication_figure_png"] is True
    assert operations["create_display_only_linear_minmax_uint8_previews"] is True
    assert operations["manual_panel_localization_for_identity_review"] is True
    assert operations["record_descriptive_identity_mapping_decision"] is True

    assert operations["automatic_image_registration"] is False
    assert operations["reciprocal_pixel_scale_inference"] is False
    assert operations["pattern_center_inference"] is False
    assert operations["peak_detection"] is False
    assert operations["phase_indexing"] is False
    assert operations["analyzer_execution"] is False
    assert operations["parameter_tuning"] is False
    assert operations["four_d_stem_access"] is False
    assert operations["external_validation_claim"] is False
    assert operations["engineering_decision_claim"] is False


def test_tracked_evidence_chain_allows_only_predeclared_pixel_stage() -> None:
    config = inspect._validate_config(_config_payload())
    hashes = inspect._validate_evidence_chain(config)

    assert set(hashes) == {
        "metadata_snapshot",
        "remote_inventory_snapshot",
        "tiff_metadata_snapshot",
        "prepixel_metadata_snapshot",
        "publication_claims_snapshot",
        "publication_provenance_snapshot",
    }
    assert all(len(value) == 64 for value in hashes.values())


def test_live_pixel_source_snapshot_pins_exact_source_and_figure_bytes() -> None:
    snapshot = json.loads(SOURCE_SNAPSHOT_PATH.read_text(encoding="utf-8"))

    assert snapshot["schema_version"] == "1.0"
    assert snapshot["contract_config_sha256"] == (
        "f7e2947cd28143ac1376ca43866dec1e70366a36d226cb2783b5f1d6a29a0a9d"
    )
    assert snapshot["source_archive"] == {
        "bytes": 25850906,
        "md5": "0c830a9b276a491e91037872891cb440",
        "sha256": "5f4c9406a7b22691414e4145784ef0548f19c152c8c529991d978d6f94e2f828",
    }
    assert [item["temperature_k"] for item in snapshot["source_tiffs"]] == [23, 91, 172]
    assert [item["sha256"] for item in snapshot["source_tiffs"]] == [
        "b7fc809f09a7807a89792fa7b581fe086894a820cb507f2ab6e06562c9ec8c2b",
        "26d704f99821a651bc12d4ccf910e809d47eeaf2ebfc20ebaa228b2b4d7a5799",
        "bc94402678b67dacea6bd7d3235176ad2fcd5086784662941ecb7dc11d479758",
    ]
    for item in snapshot["source_tiffs"]:
        assert item["shape"] == [2048, 2048]
        assert item["dtype"] == "float64"
        assert item["finite_count"] == 4194304
        assert item["nonfinite_count"] == 0
        assert item["finite_max"] >= item["finite_min"]
    assert snapshot["publication_figure"]["sha256"] == (
        "3ac7a9ba3f349ca74020008319f3994cc6dfe2e3b9653075a369eabf47a1a426"
    )
    assert snapshot["publication_figure"]["decoded_shape"] == [398, 685, 4]
    assert all(value is False for value in snapshot["retention_boundary"].values())


def test_manual_review_preserves_diagnostic_identity_and_blocks_calibration() -> None:
    review = json.loads(MANUAL_REVIEW_PATH.read_text(encoding="utf-8"))
    decision = review["decision"]
    next_evidence = review["next_evidence_requirement"]

    assert review["review_method"] == (
        "manual_visual_review_of_fixed_source_previews_and_pinned_publication_figure"
    )
    assert review["publication_panel_context"]["manual_panel_boxes_xyxy"] == {
        "left": [383, 137, 462, 216],
        "middle": [482, 137, 561, 216],
        "right": [579, 137, 658, 216],
    }
    assert decision["overall_source_family_to_figure1d_correspondence"] == "Diagnostic"
    assert decision["individual_23k_tiff_to_left_panel_identity"] == "Inconclusive"
    assert decision["individual_91k_tiff_to_middle_panel_identity"] == "Inconclusive"
    assert decision["individual_172k_tiff_to_right_panel_identity"] == "Inconclusive"
    assert decision["temperature_semantics"] == "Supported"
    assert decision["source_tiff_reciprocal_calibration"] == "Inconclusive"
    assert decision["source_tiff_pattern_center"] == "Inconclusive"
    assert decision["external_validation_readiness"] == "Inconclusive"
    assert next_evidence["automatic_registration_authorized"] is False
    assert next_evidence["reciprocal_scale_inference_authorized"] is False
    assert next_evidence["additional_saed_source_bytes_required"] is False
    assert next_evidence["four_d_stem_bytes_required"] is False


def _tiny_tiff_payload(values: np.ndarray) -> bytes:
    header = bytearray(inspect.PIXEL_OFFSET)
    header[:4] = b"II*\x00"
    return bytes(header) + values.astype("<f8").tobytes(order="C")


def _tiny_member() -> dict[str, object]:
    return {
        "path": "fixture.tif",
        "temperature_k": 23,
        "expected_uncompressed_bytes": inspect.PIXEL_OFFSET + 4 * 8,
        "expected_shape": [2, 2],
        "expected_storage": "float64",
    }


def test_tiff_decoder_reads_only_predeclared_float64_layout() -> None:
    values = np.array([[1.0, 2.5], [3.25, 4.0]], dtype=np.float64)
    decoded = inspect._decode_authorized_tiff(_tiny_tiff_payload(values), _tiny_member())

    assert decoded.shape == (2, 2)
    assert decoded.dtype == np.dtype("<f8")
    assert np.array_equal(decoded, values)


def test_tiff_decoder_rejects_header_or_size_drift() -> None:
    values = np.arange(4, dtype=np.float64).reshape(2, 2)
    valid = bytearray(_tiny_tiff_payload(values))
    valid[:4] = b"MM\x00*"

    with pytest.raises(inspect.SrTiO3FigurePixelInventoryError, match="little-endian"):
        inspect._decode_authorized_tiff(bytes(valid), _tiny_member())

    truncated = _tiny_tiff_payload(values)[:-8]
    with pytest.raises(inspect.SrTiO3FigurePixelInventoryError, match="byte count"):
        inspect._decode_authorized_tiff(truncated, _tiny_member())


def test_array_summary_preserves_nonfinite_quality_information() -> None:
    array = np.array([[1.0, np.nan], [np.inf, -2.0]], dtype=np.float64)
    summary = inspect._array_summary(array)

    assert summary["shape"] == [2, 2]
    assert summary["dtype"] == "float64"
    assert summary["finite_count"] == 2
    assert summary["nonfinite_count"] == 2
    assert summary["finite_min"] == -2.0
    assert summary["finite_max"] == 1.0


def test_preview_is_fixed_display_only_linear_minmax() -> None:
    array = np.array([[0.0, 1.0], [2.0, 3.0]], dtype=np.float64)
    preview = inspect._preview_uint8(array)

    assert preview.shape == (inspect.PREVIEW_SIZE, inspect.PREVIEW_SIZE)
    assert preview.dtype == np.uint8
    assert int(preview.min()) == 0
    assert int(preview.max()) == 255


def test_preview_handles_constant_and_nonfinite_values_without_source_mutation() -> None:
    array = np.array([[5.0, 5.0], [np.nan, 5.0]], dtype=np.float64)
    before = array.copy()
    preview = inspect._preview_uint8(array)

    assert preview.shape == (inspect.PREVIEW_SIZE, inspect.PREVIEW_SIZE)
    assert np.all(preview == 0)
    assert np.array_equal(array, before, equal_nan=True)


def test_untrusted_figure_host_fails_contract_validation(tmp_path: Path) -> None:
    config = _config_payload()
    config["publication_figure"]["image_url"] = (
        "https://example.com/41586_2026_10823_Fig1_HTML.png"
    )
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(inspect.SrTiO3FigurePixelInventoryError, match="host"):
        inspect._validate_config(inspect._load_json(path))
