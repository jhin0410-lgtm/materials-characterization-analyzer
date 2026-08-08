from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from scripts import inspect_zenodo_srtio3_saed_figure1d_pixels as inspect

CONFIG_PATH = Path(
    "case_studies/zenodo_srtio3_saed_figure1d_identity_mapping/evidence_contract.json"
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
