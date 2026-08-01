from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import audit_datacore_saed_candidate as audit  # noqa: E402


def _zip_payload(paths: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in paths:
            archive.writestr(path, path.encode("utf-8"))
    return buffer.getvalue()


def test_safe_members_rejects_parent_traversal() -> None:
    payload = _zip_payload(["../escape.dm4"])
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        with pytest.raises(audit.SourceAuditError, match="unsafe ZIP member"):
            audit._safe_members(archive)


def test_safe_members_rejects_casefold_duplicate_paths() -> None:
    payload = _zip_payload(["Pattern.dm4", "pattern.dm4"])
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        with pytest.raises(audit.SourceAuditError, match="duplicate ZIP member"):
            audit._safe_members(archive)


def test_selected_metadata_keeps_only_relevant_instrument_fields() -> None:
    selected = audit._selected_metadata(
        {
            "Acquisition": {
                "Accelerating Voltage": 200000,
                "Detector": "Example camera",
                "Unrelated": "ignored",
            },
            "Camera Length": 0.8,
        }
    )
    keys = {row["key"] for row in selected}
    assert "Acquisition.Accelerating Voltage" in keys
    assert "Acquisition.Detector" in keys
    assert "Camera Length" in keys
    assert "Acquisition.Unrelated" not in keys


def test_array_comparison_distinguishes_exact_and_shape_mismatch() -> None:
    left = np.arange(16, dtype=np.uint16).reshape(4, 4)
    exact = audit._compare_arrays(left, left.copy())
    assert exact["shape_equal"]
    assert exact["dtype_equal"]
    assert exact["exact_value_equal"]
    assert exact["allclose"]

    mismatch = audit._compare_arrays(left, np.arange(8, dtype=np.uint16).reshape(2, 4))
    assert not mismatch["shape_equal"]
    assert not mismatch["exact_value_equal"]


def test_run_records_raw_evidence_without_authorizing_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _zip_payload(
        [
            "patterns/001.dm4",
            "patterns/001.tif",
            "patterns/112.dm4",
            "patterns/112.tif",
        ]
    )
    array_001 = np.arange(64, dtype=np.uint16).reshape(8, 8)
    array_112 = np.arange(64, 128, dtype=np.uint16).reshape(8, 8)

    monkeypatch.setattr(
        audit,
        "_request_bytes",
        lambda url: (payload, "https://datacore.iu.edu/downloads/example?token=removed"),
    )

    def inspect_dm4(path: Path):
        array = array_001 if "001" in path.name else array_112
        return (
            {
                "signal_count": 1,
                "signals": [
                    {
                        "array": audit._array_record(array),
                        "selected_original_metadata": [
                            {"key": "Microscope.Voltage", "value": 200000},
                            {"key": "Microscope.Camera Length", "value": 0.8},
                            {"key": "Acquisition.Date", "value": "2025-01-01"},
                            {"key": "Detector.Name", "value": "camera"},
                        ],
                    }
                ],
            },
            [array],
        )

    def inspect_tiff(path: Path):
        array = array_001 if "001" in path.name else array_112
        return ({"series_count": 1, "arrays": [audit._array_record(array)]}, [array.copy()])

    monkeypatch.setattr(audit, "_inspect_dm4", inspect_dm4)
    monkeypatch.setattr(audit, "_inspect_tiff", inspect_tiff)

    output = tmp_path / "audit"
    summary = audit.run(
        source_url="https://datacore.iu.edu/downloads/example?locale=en",
        output=output,
    )

    assert summary["counts"]["dm4_file_count"] == 2
    assert summary["counts"]["tiff_file_count"] == 2
    assert summary["evidence_gates"]["all_paired_arrays_exactly_equal"]
    assert summary["decision"]["raw_file_audit_completed"]
    assert not summary["decision"]["independent_acquisition_count_verified"]
    assert not summary["decision"]["eligible_for_calibrated_saed_validation_now"]
    assert not summary["decision"]["phase_or_zone_axis_claim_allowed"]
    assert not (output / "source.zip").exists()
    assert not (output / "extracted").exists()
    assert (output / "source_audit_summary.json").exists()
    assert (output / "source_audit_manifest.json").exists()
