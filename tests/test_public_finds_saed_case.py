from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_public_finds_saed_case as case  # noqa: E402
import verify_public_finds_saed_case as verifier  # noqa: E402


def _config() -> dict:
    return {
        "selected_project": {
            "project_path": "Project SAED A.txt",
            "project_sha256": "a" * 64,
            "image_path": "SAED A.jpg",
            "image_bytes": 1,
            "image_sha256": "b" * 64,
            "d_values_path": "SAED A d-values.txt",
            "d_values_sha256": "c" * 64,
            "camera_constant_angstrom_pixel": 587.5,
            "camera_constant_nm_pixel": 58.75,
            "reciprocal_nm_inv_per_pixel": 10.0 / 587.5,
            "center_x_px": 40.0,
            "center_y_px": 30.0,
            "source_image_width_px": 80,
            "source_image_height_px": 64,
            "source_image_dtype": "uint8",
            "source_image_channels": 3,
            "source_representation": "lossy_jpeg_rendered_image",
        },
        "canonical_adapter": {
            "operation": "decode_source_jpeg_then_bgr_to_grayscale_and_write_lossless_png"
        },
        "analysis": {
            "primary_smoothing_window": 7,
            "sensitivity_smoothing_windows": [5, 11],
            "center_sensitivity_offsets_px": [
                [-2.0, 0.0],
                [2.0, 0.0],
                [0.0, -2.0],
                [0.0, 2.0],
            ],
        },
    }


def test_project_parser_preserves_explicit_calibration() -> None:
    payload = b"SAED A.jpg\n587.5\n40\n30\nSAED A d-values.txt\n"
    project = case._parse_selected_project(payload, _config())
    assert project["camera_constant_nm_pixel"] == pytest.approx(58.75)
    assert project["reciprocal_nm_inv_per_pixel"] == pytest.approx(10.0 / 587.5)
    assert project["center_x_px"] == 40.0
    assert project["center_y_px"] == 30.0


def test_project_parser_rejects_center_or_reference_drift() -> None:
    config = _config()
    with pytest.raises(case.CaseError, match="calibration or center changed"):
        case._parse_selected_project(
            b"SAED A.jpg\n587.5\n41\n30\nSAED A d-values.txt\n",
            config,
        )
    with pytest.raises(case.CaseError, match="references changed"):
        case._parse_selected_project(
            b"other.jpg\n587.5\n40\n30\nSAED A d-values.txt\n",
            config,
        )


def test_source_d_values_convert_angstrom_to_nm_without_assignment() -> None:
    record = case._parse_source_d_values(b"SAED A d-values\n2.022\n1.431\n")
    assert record["d_spacing_angstrom"] == [2.022, 1.431]
    assert record["d_spacing_nm"] == pytest.approx([0.2022, 0.1431])


def test_jpeg_adapter_writes_pixel_equal_grayscale_png(tmp_path: Path) -> None:
    image = np.zeros((64, 80, 3), dtype=np.uint8)
    image[..., 0] = np.arange(80, dtype=np.uint8)[None, :]
    image[..., 1] = 100
    image[..., 2] = np.arange(64, dtype=np.uint8)[:, None]
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    destination = tmp_path / "canonical.png"
    gray, record = case.decode_to_canonical_png(
        encoded.tobytes(), destination, _config()
    )
    roundtrip = cv2.imread(str(destination), cv2.IMREAD_UNCHANGED)
    assert np.array_equal(gray, roundtrip)
    assert record["png_roundtrip_pixel_equal"]
    assert not record["normalization_applied"]
    assert not record["cropping_applied"]
    assert not record["resizing_applied"]
    assert record["canonical_sha256"] == hashlib.sha256(destination.read_bytes()).hexdigest()


def test_run_contracts_include_primary_two_smoothing_and_four_center_runs() -> None:
    contracts = case._run_contracts(_config())
    assert len(contracts) == 7
    assert contracts[0] == {
        "run_id": "primary",
        "center_x_px": 40.0,
        "center_y_px": 30.0,
        "smoothing_window": 7,
        "sensitivity_dimension": "primary",
    }
    assert {record["run_id"] for record in contracts} == {
        "primary",
        "smoothing_5",
        "smoothing_11",
        "center_m2_p0",
        "center_p2_p0",
        "center_p0_m2",
        "center_p0_p2",
    }
    assert {record["smoothing_window"] for record in contracts} == {5, 7, 11}
    center_contracts = [
        record for record in contracts if record["sensitivity_dimension"] == "center_position"
    ]
    assert {(record["center_x_px"], record["center_y_px"]) for record in center_contracts} == {
        (38.0, 30.0),
        (42.0, 30.0),
        (40.0, 28.0),
        (40.0, 32.0),
    }


def _candidate(run_id: str, ring_id: int, radius: float, d_nm: float) -> dict:
    return {
        "run_id": run_id,
        "ring_id": ring_id,
        "radius_px": radius,
        "d_spacing_nm": d_nm,
    }


def test_candidate_review_matches_one_to_one_and_preserves_unmatched() -> None:
    runs = [
        "primary",
        "smoothing_5",
        "smoothing_11",
        "center_m2_p0",
        "center_p2_p0",
        "center_p0_m2",
        "center_p0_p2",
    ]
    rows = [_candidate("primary", 1, 100.0, 0.5)]
    for index, run_id in enumerate(runs[1:], start=1):
        rows.append(_candidate(run_id, 1, 100.0 + index * 0.2, 0.5))
    rows.append(_candidate("smoothing_5", 2, 200.0, 0.25))
    reviewed, unmatched = case.review_candidate_sensitivity(
        pd.DataFrame(rows), tolerance_px=5.0
    )
    assert len(reviewed) == 1
    assert reviewed.iloc[0]["all_runs_matched"]
    assert reviewed.iloc[0]["review_status"] == "stable_radius_review_required"
    assert len(unmatched) == 1
    assert unmatched.iloc[0]["radius_px"] == pytest.approx(200.0)


def test_source_d_value_comparison_is_post_detection_context_only() -> None:
    primary = pd.DataFrame(
        [
            {"ring_id": 1, "radius_px": 100.0, "d_spacing_nm": 0.5},
            {"ring_id": 2, "radius_px": 200.0, "d_spacing_nm": 0.25},
        ]
    )
    comparison = case.compare_source_d_values(
        primary,
        {"d_spacing_nm": [0.49, 0.24]},
        camera_constant_nm_pixel=50.0,
        max_radius_px=250.0,
    )
    assert comparison["nearest_detected_ring_id"].tolist() == [1, 2]
    assert not comparison["reference_used_for_detection_tuning"].any()
    assert not comparison["material_or_phase_identity_assigned"].any()



def test_verifier_pins_primary_candidate_count_radii_and_d_spacings() -> None:
    primary = pd.DataFrame(
        [
            {"ring_id": ring_id, "radius_px": radius_px, "d_spacing_nm": d_spacing_nm}
            for ring_id, radius_px, d_spacing_nm in verifier.EXPECTED_PRIMARY_CANDIDATES
        ]
    )
    verifier._verify_pinned_primary_candidates(primary)


@pytest.mark.parametrize(
    ("column", "delta", "message"),
    [
        ("radius_px", 0.01, "primary radius drift"),
        ("d_spacing_nm", 0.001, "primary d-spacing drift"),
    ],
)
def test_verifier_rejects_primary_candidate_numerical_drift(
    column: str,
    delta: float,
    message: str,
) -> None:
    rows = [
        {"ring_id": ring_id, "radius_px": radius_px, "d_spacing_nm": d_spacing_nm}
        for ring_id, radius_px, d_spacing_nm in verifier.EXPECTED_PRIMARY_CANDIDATES
    ]
    rows[0][column] += delta
    with pytest.raises(verifier.VerificationError, match=message):
        verifier._verify_pinned_primary_candidates(pd.DataFrame(rows))


def test_verifier_rejects_missing_primary_candidate() -> None:
    rows = [
        {"ring_id": ring_id, "radius_px": radius_px, "d_spacing_nm": d_spacing_nm}
        for ring_id, radius_px, d_spacing_nm in verifier.EXPECTED_PRIMARY_CANDIDATES[:-1]
    ]
    with pytest.raises(verifier.VerificationError, match="primary candidate count drift"):
        verifier._verify_pinned_primary_candidates(pd.DataFrame(rows))
