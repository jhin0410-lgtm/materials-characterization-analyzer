from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import pytest

from mca.cli_entry import main as cli_main
from mca.saed import (
    analyze_saed,
    calculate_radial_profile,
    detect_ring_candidates,
    load_saed_image,
    resolve_calibration,
    resolve_center,
)


def _write_ring_image(
    path: Path,
    *,
    dtype=np.uint16,
    center=(64.0, 64.0),
    rings=(20.0, 40.0),
    dark=False,
    saturated=False,
) -> np.ndarray:
    height = width = 129
    yy, xx = np.indices((height, width), dtype=float)
    radius = np.hypot(xx - center[0], yy - center[1])
    base = 50000.0 if dark else 1000.0
    image = np.full((height, width), base, dtype=float)
    amplitude = -20000.0 if dark else 20000.0
    for ring_radius in rings:
        image += amplitude * np.exp(-0.5 * ((radius - ring_radius) / 1.5) ** 2)
    image += (10000.0 if not dark else -5000.0) * np.exp(-0.5 * (radius / 2.0) ** 2)
    if saturated:
        image[int(center[1]), int(center[0])] = np.iinfo(dtype).max
    image = np.clip(image, 0, np.iinfo(dtype).max).astype(dtype)
    assert cv2.imwrite(str(path), image)
    return image


def test_load_saed_preserves_uint16(tmp_path: Path) -> None:
    source = tmp_path / "saed.tif"
    original = _write_ring_image(source)
    loaded = load_saed_image(source)
    assert loaded.dtype == np.uint16
    assert np.array_equal(loaded, original)


def test_resolve_center_requires_pair_and_valid_bounds() -> None:
    with pytest.raises(ValueError, match="supplied together"):
        resolve_center((100, 100), center_x_px=50)
    with pytest.raises(ValueError, match="within"):
        resolve_center((100, 100), center_x_px=101, center_y_px=50)
    assert resolve_center((101, 101)) == (50.0, 50.0, "image_midpoint")


def test_calibration_routes_and_g_convention() -> None:
    direct = resolve_calibration(reciprocal_nm_inv_per_pixel=0.02)
    assert direct["reciprocal_nm_inv_per_pixel"] == pytest.approx(0.02)

    camera = resolve_calibration(camera_constant_nm_pixel=50.0)
    assert camera["reciprocal_nm_inv_per_pixel"] == pytest.approx(0.02)

    reference = resolve_calibration(reference_d_nm=2.0, reference_radius_px=25.0)
    assert reference["camera_constant_nm_pixel"] == pytest.approx(50.0)
    assert reference["reciprocal_nm_inv_per_pixel"] == pytest.approx(0.02)


def test_calibration_rejects_ambiguous_or_partial_input() -> None:
    with pytest.raises(ValueError, match="supplied together"):
        resolve_calibration(reference_d_nm=2.0)
    with pytest.raises(ValueError, match="only one"):
        resolve_calibration(
            reciprocal_nm_inv_per_pixel=0.02,
            camera_constant_nm_pixel=50.0,
        )


def test_radial_profile_detects_bright_rings_and_d_spacing(tmp_path: Path) -> None:
    source = tmp_path / "bright.tif"
    image = _write_ring_image(source)
    profile = calculate_radial_profile(image, center_x_px=64, center_y_px=64)
    _, candidates = detect_ring_candidates(
        profile,
        min_radius_px=5,
        prominence_fraction=0.1,
        min_distance_px=10,
        smoothing_window=5,
        calibration=resolve_calibration(reciprocal_nm_inv_per_pixel=0.02),
    )
    assert list(candidates["radius_px"]) == pytest.approx([20, 40], abs=1.0)
    assert list(candidates["d_spacing_nm"]) == pytest.approx([2.5, 1.25], abs=0.1)


def test_dark_ring_contrast_is_explicit(tmp_path: Path) -> None:
    source = tmp_path / "dark.tif"
    image = _write_ring_image(source, dark=True)
    profile = calculate_radial_profile(image, center_x_px=64, center_y_px=64)
    _, candidates = detect_ring_candidates(
        profile,
        ring_contrast="dark",
        min_radius_px=5,
        prominence_fraction=0.1,
        min_distance_px=10,
        smoothing_window=5,
    )
    assert list(candidates["radius_px"]) == pytest.approx([20, 40], abs=1.0)


def test_max_radius_cannot_use_incomplete_annuli(tmp_path: Path) -> None:
    source = tmp_path / "saed.tif"
    image = _write_ring_image(source, center=(40, 64))
    with pytest.raises(ValueError, match="complete annulus"):
        calculate_radial_profile(
            image,
            center_x_px=40,
            center_y_px=64,
            max_radius_px=50,
        )


def test_analyze_saed_without_calibration_preserves_pixel_only_output(tmp_path: Path) -> None:
    source = tmp_path / "saed.tif"
    _write_ring_image(source)
    result = analyze_saed(
        source,
        tmp_path / "out",
        sample_id="sample-a",
        center_x_px=64,
        center_y_px=64,
        prominence_fraction=0.1,
        min_distance_px=10,
        smoothing_window=5,
    )
    assert result["ring_candidates"]["d_spacing_nm"].isna().all()
    assert "saed_reciprocal_calibration_not_provided" in result["analysis_result"].warnings


def test_analyze_saed_writes_provenance_features_and_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "saed.tif"
    _write_ring_image(source, saturated=True)
    output = tmp_path / "out"
    result = analyze_saed(
        source,
        output,
        sample_id="sample-a",
        center_x_px=64,
        center_y_px=64,
        reciprocal_nm_inv_per_pixel=0.02,
        prominence_fraction=0.1,
        min_distance_px=10,
        smoothing_window=5,
        acquisition_metadata={"accelerating_voltage_kv": 200},
    )
    expected = {
        "saed_radial_profile.csv",
        "saed_ring_candidates.csv",
        "saed_features_long.csv",
        "saed_radial_profile.png",
        "saed_ring_overlay.png",
    }
    assert expected == {path.name for path in output.iterdir()}
    assert result["analysis_result"].source_sha256
    assert "saturated_pixels_present" in result["analysis_result"].warnings
    feature_frame = pd.read_csv(result["feature_path"])
    assert set(feature_frame["quality_flag"]) == {"review_required"}
    assert "candidate_d_spacing" in set(feature_frame["feature_name"])


def test_midpoint_center_is_recorded_as_warning(tmp_path: Path) -> None:
    source = tmp_path / "saed.tif"
    _write_ring_image(source)
    result = analyze_saed(
        source,
        tmp_path / "out",
        sample_id="sample-a",
        prominence_fraction=0.1,
        min_distance_px=10,
        smoothing_window=5,
    )
    assert "saed_center_assumed_image_midpoint" in result["analysis_result"].warnings
    assert result["analysis_result"].acquisition_metadata["center_method"] == "image_midpoint"


def test_metadata_is_validated_before_artifact_creation(tmp_path: Path) -> None:
    source = tmp_path / "saed.tif"
    _write_ring_image(source)
    output = tmp_path / "out"
    with pytest.raises(ValueError, match="accelerating_voltage_kv"):
        analyze_saed(
            source,
            output,
            sample_id="sample-a",
            acquisition_metadata={"accelerating_voltage_kv": 0},
        )
    assert not output.exists()


def test_saed_cli_writes_manifest(tmp_path: Path) -> None:
    source = tmp_path / "saed.tif"
    _write_ring_image(source)
    output = tmp_path / "out"
    exit_code = cli_main(
        [
            "saed",
            "--input",
            str(source),
            "--output",
            str(output),
            "--sample-id",
            "sample-a",
            "--center-x-px",
            "64",
            "--center-y-px",
            "64",
            "--reciprocal-nm-inv-per-pixel",
            "0.02",
            "--prominence-fraction",
            "0.1",
            "--min-distance-px",
            "10",
            "--smoothing-window",
            "5",
        ]
    )
    assert exit_code == 0
    manifest = json.loads((output / "saed_analysis_manifest.json").read_text(encoding="utf-8"))
    analysis = manifest["analyses"][0]
    assert analysis["instrument"] == "saed"
    assert analysis["acquisition_metadata"]["reciprocal_space_convention"] == "g_equals_1_over_d"
