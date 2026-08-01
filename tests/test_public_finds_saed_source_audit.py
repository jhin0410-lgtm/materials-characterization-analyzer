from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import audit_public_finds_saed_source as audit  # noqa: E402


def test_project_contract_resolves_image_and_camera_conversion() -> None:
    inventory = {
        "examples/project saed a.txt": "examples/Project SAED A.txt",
        "examples/saed a.png": "examples/SAED A.png",
        "examples/saed a d-values.txt": "examples/SAED A d-values.txt",
    }
    payload = (
        "SAED A.png\n587.5\n586\n575\nSAED A d-values.txt\n"
    ).encode("utf-8")
    project = audit._project_candidate(
        "examples/Project SAED A.txt",
        payload,
        inventory,
    )
    assert project is not None
    assert project["image_path"] == "examples/SAED A.png"
    assert project["d_values_path"] == "examples/SAED A d-values.txt"
    assert project["camera_constant_nm_pixel"] == pytest.approx(58.75)
    assert project["reciprocal_nm_inv_per_pixel"] == pytest.approx(10.0 / 587.5)
    assert project["center_x_px"] == 586
    assert project["center_y_px"] == 575


def test_nonproject_and_numeric_d_value_text_are_ignored() -> None:
    assert audit._project_candidate(
        "README.txt",
        b"This is documentation.\nNo camera constant here.\n",
        {},
    ) is None
    assert audit._project_candidate(
        "SAED A d-values.txt",
        b"SAED A d-values\n2.022\n1.431\n1.167\n1.011\n",
        {},
    ) is None


def test_platform_resource_forks_are_not_counted_as_measurement_images() -> None:
    assert audit._member_class("SAED A.jpg", is_directory=False) == "image"
    assert (
        audit._member_class("__MACOSX/._SAED A.jpg", is_directory=False)
        == "platform_metadata"
    )
    assert audit._member_class("__MACOSX", is_directory=True) == "directory"


def test_safe_members_rejects_parent_traversal() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../escape.txt", "blocked")
    buffer.seek(0)
    with zipfile.ZipFile(buffer) as archive:
        with pytest.raises(audit.SourceAuditError, match="unsafe ZIP member"):
            audit._safe_members(archive)


def test_image_inspection_preserves_decoded_dtype_and_center_contract() -> None:
    image = np.zeros((64, 80), dtype=np.uint8)
    cv2.circle(image, (40, 30), 15, 200, 2)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    project = {
        "center_x_px": 40.0,
        "center_y_px": 30.0,
        "camera_constant_angstrom_pixel": 500.0,
        "camera_constant_nm_pixel": 50.0,
        "reciprocal_nm_inv_per_pixel": 0.02,
    }
    record = audit._inspect_image(encoded.tobytes(), "example.png", project)
    assert record["dtype"] == "uint8"
    assert record["grayscale_shape"] == [64, 80]
    assert record["center_in_bounds"]
    assert record["maximum_complete_annulus_radius_px"] == pytest.approx(30.0)
    assert record["saed_analyzer_extension_supported_directly"]


def test_jpeg_representation_is_explicitly_lossy() -> None:
    image = np.zeros((64, 64), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    project = {
        "center_x_px": 31.5,
        "center_y_px": 31.5,
        "camera_constant_angstrom_pixel": 500.0,
        "camera_constant_nm_pixel": 50.0,
        "reciprocal_nm_inv_per_pixel": 0.02,
    }
    record = audit._inspect_image(encoded.tobytes(), "example.jpg", project)
    assert record["source_representation"] == "lossy_jpeg_rendered_image"
    assert not record["saed_analyzer_extension_supported_directly"]
