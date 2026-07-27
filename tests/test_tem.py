from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import pytest

from mca.cli_entry import main as cli_main
from mca.tem import (
    analyze_tem,
    crop_tem_roi,
    find_tem_regions,
    measure_tem_regions,
    read_tem_image,
    threshold_tem_regions,
    validate_tem_acquisition_metadata,
)
from mca.tem_features import build_tem_feature_records


def _write_image(path: Path, image: np.ndarray) -> None:
    success, encoded = cv2.imencode(path.suffix, image)
    assert success
    encoded.tofile(path)


def _synthetic_uint16_tem() -> np.ndarray:
    image = np.full((96, 128), 30, dtype=np.uint16)
    cv2.circle(image, (30, 30), 10, 800, -1)
    cv2.circle(image, (80, 55), 15, 1200, -1)
    return image


def test_read_tem_image_preserves_uint16(tmp_path: Path) -> None:
    path = tmp_path / "tem.png"
    _write_image(path, _synthetic_uint16_tem())

    loaded = read_tem_image(path)

    assert loaded.dtype == np.uint16
    assert loaded.shape == (96, 128)


def test_crop_tem_roi_validates_bounds() -> None:
    image = _synthetic_uint16_tem()

    assert crop_tem_roi(image, (10, 10, 20, 30)).shape == (30, 20)
    with pytest.raises(ValueError, match="exceeds image bounds"):
        crop_tem_roi(image, (120, 0, 20, 20))


def test_bright_contrast_detection_and_measurement() -> None:
    image = _synthetic_uint16_tem()

    threshold, mask = threshold_tem_regions(image, "bright")
    contours, excluded = find_tem_regions(mask, min_area_pixels=20)
    measurements = measure_tem_regions(
        contours,
        image,
        nm_per_pixel=0.5,
        contrast_target="bright",
    )

    assert threshold > 0
    assert excluded == 0
    assert len(measurements) == 2
    assert (measurements["equivalent_diameter_nm"] > 0).all()
    assert set(measurements["contrast_target"]) == {"bright"}


def test_dark_contrast_target_detects_dark_region() -> None:
    image = np.full((64, 64), 1000, dtype=np.uint16)
    cv2.circle(image, (32, 32), 8, 50, -1)

    _, mask = threshold_tem_regions(image, "dark")
    contours, _ = find_tem_regions(mask, min_area_pixels=10)

    assert len(contours) == 1


def test_border_region_exclusion_is_explicit() -> None:
    image = np.zeros((64, 64), dtype=np.uint8)
    cv2.rectangle(image, (0, 10), (15, 30), 255, -1)
    cv2.circle(image, (40, 40), 6, 255, -1)
    _, mask = threshold_tem_regions(image, "bright")

    contours, excluded = find_tem_regions(
        mask,
        min_area_pixels=5,
        exclude_border_regions=True,
    )

    assert len(contours) == 1
    assert excluded == 1


def test_tem_feature_records_are_review_required(tmp_path: Path) -> None:
    source = tmp_path / "tem.png"
    _write_image(source, _synthetic_uint16_tem())
    measurements = pd.DataFrame(
        {
            "equivalent_diameter_nm": [5.0, 7.0],
            "area_fraction": [0.1, 0.1],
            "area_nm2": [20.0, 30.0],
            "mean_intensity_raw": [800.0, 1200.0],
            "touches_border": [False, True],
        }
    )

    records = build_tem_feature_records(
        measurements,
        sample_id="sample-a",
        source_file=source,
        preprocessing_id="tem123",
    )

    assert any(record.feature_name == "detected_region_count" for record in records)
    assert all(record.instrument == "tem" for record in records)
    assert all(record.quality_flag == "review_required" for record in records)
    assert all(record.source_sha256 for record in records)


def test_analyze_tem_writes_artifacts_and_contract(tmp_path: Path) -> None:
    source = tmp_path / "tem.png"
    _write_image(source, _synthetic_uint16_tem())
    output = tmp_path / "outputs"

    result = analyze_tem(
        source,
        output,
        sample_id="sample-a",
        nm_per_pixel=0.25,
        contrast_target="bright",
        min_area_pixels=20,
        acquisition_metadata={
            "imaging_mode": "bf_tem",
            "accelerating_voltage_kv": 200,
        },
    )

    assert len(result["measurements"]) == 2
    for key in (
        "measurements_path",
        "mask_path",
        "overlay_path",
        "size_distribution_path",
        "intensity_histogram_path",
        "feature_path",
    ):
        assert Path(result[key]).exists()
    analysis = result["analysis_result"]
    assert analysis.instrument == "tem"
    assert analysis.source_sha256
    assert analysis.acquisition_metadata["scale_source"] == "user_supplied_cli"
    assert "contrast_regions_are_not_structural_assignments" in analysis.warnings


def test_metadata_is_validated_before_outputs_are_created(tmp_path: Path) -> None:
    source = tmp_path / "tem.png"
    _write_image(source, _synthetic_uint16_tem())
    output = tmp_path / "outputs"

    with pytest.raises(ValueError, match="accelerating_voltage_kv"):
        analyze_tem(
            source,
            output,
            sample_id="sample-a",
            nm_per_pixel=0.25,
            contrast_target="bright",
            acquisition_metadata={"accelerating_voltage_kv": -1},
        )

    assert not output.exists()


def test_signed_defocus_is_allowed() -> None:
    metadata = validate_tem_acquisition_metadata(
        {"imaging_mode": "hrtem", "defocus_nm": -40.0}
    )

    assert metadata["defocus_nm"] == -40.0


def test_tem_cli_dispatch_writes_manifest(tmp_path: Path) -> None:
    source = tmp_path / "tem.png"
    _write_image(source, _synthetic_uint16_tem())
    output = tmp_path / "cli-output"

    exit_code = cli_main(
        [
            "tem",
            "--input",
            str(source),
            "--output",
            str(output),
            "--sample-id",
            "sample-a",
            "--nm-per-pixel",
            "0.25",
            "--contrast-target",
            "bright",
            "--min-area-pixels",
            "20",
            "--imaging-mode",
            "bf_tem",
            "--accelerating-voltage-kv",
            "200",
        ]
    )

    assert exit_code == 0
    manifest = output / "tem_analysis_manifest.json"
    assert manifest.exists()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["analyses"][0]["instrument"] == "tem"
