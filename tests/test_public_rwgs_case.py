from __future__ import annotations

import json
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import pytest

from scripts.run_public_rwgs_xrd_sem_eds_case import (
    adapt_eds_xlsx,
    adapt_xrd_asc,
    derive_atomic_percent,
    extract_eds_weight_table,
    inspect_sem_source,
    run_case,
)


def _write_minimal_eds_xlsx(path: Path) -> None:
    shared = [
        "Project:",
        "Cu-Al2O3",
        "Specimen:",
        "Specimen 1",
        "Site:",
        "Site 3",
        "Element",
        "Line",
        "K-Factor",
        "K-Factor Type",
        "Absorption Correction",
        "Wt%",
        "Wt% Sigma",
        "C",
        "K",
        "O",
        "Al",
        "Si",
        "Ni",
        "Cu",
        "Au",
        "Total:",
        "NOTE: C, Si and Au were discarded for interpretation.",
    ]
    shared_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{len(shared)}" uniqueCount="{len(shared)}">'
        + "".join(f"<si><t>{value}</t></si>" for value in shared)
        + "</sst>"
    )

    index = {value: position for position, value in enumerate(shared)}
    rows: list[str] = []

    def string_cell(reference: str, value: str) -> str:
        return f'<c r="{reference}" t="s"><v>{index[value]}</v></c>'

    def number_cell(reference: str, value: float) -> str:
        return f'<c r="{reference}"><v>{value}</v></c>'

    rows.extend(
        [
            f'<row r="1">{string_cell("A1", "Project:")}{string_cell("B1", "Cu-Al2O3")}</row>',
            f'<row r="3">{string_cell("A3", "Specimen:")}{string_cell("B3", "Specimen 1")}</row>',
            f'<row r="5">{string_cell("A5", "Site:")}{string_cell("B5", "Site 3")}</row>',
            '<row r="8">'
            + string_cell("A8", "Element")
            + string_cell("B8", "Line")
            + string_cell("C8", "K-Factor")
            + string_cell("D8", "K-Factor Type")
            + string_cell("E8", "Absorption Correction")
            + string_cell("F8", "Wt%")
            + string_cell("G8", "Wt% Sigma")
            + "</row>",
        ]
    )
    source_rows = [
        (9, "C", 16.11, 0.42),
        (10, "O", 29.71, 0.41),
        (11, "Al", 25.43, 0.32),
        (12, "Si", 0.20, 0.06),
        (13, "Ni", 21.49, 0.30),
        (14, "Cu", 6.54, 0.20),
        (15, "Au", 0.52, 0.15),
    ]
    for row, element, wt, sigma in source_rows:
        rows.append(
            f'<row r="{row}">'
            + string_cell(f"A{row}", element)
            + string_cell(f"B{row}", "K")
            + number_cell(f"C{row}", 1.0)
            + number_cell(f"E{row}", 1.0)
            + number_cell(f"F{row}", wt)
            + number_cell(f"G{row}", sigma)
            + "</row>"
        )
    rows.append(
        '<row r="16">'
        + string_cell("A16", "Total:")
        + number_cell("F16", 100.0)
        + "</row>"
    )
    rows.append(f'<row r="18">{string_cell("A18", shared[-1])}</row>')
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        + "".join(rows)
        + "</sheetData></worksheet>"
    )

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/sharedStrings.xml", shared_xml.encode("utf-8"))
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml.encode("utf-8"))


def _write_sem_fixture(path: Path) -> None:
    image = np.zeros((768, 1024), dtype=np.uint8)
    image[:704] = 40
    cv2.circle(image, (330, 250), 120, 150, thickness=-1)
    cv2.circle(image, (560, 400), 170, 210, thickness=-1)
    image[743, 193:324] = 255
    success, encoded = cv2.imencode(".tif", image)
    assert success
    encoded.tofile(path)


def _write_xrd_fixture(path: Path) -> None:
    two_theta = np.arange(2.01, 90.01 + 0.001, 0.02)
    intensity = (
        100.0
        + 800.0 * np.exp(-0.5 * ((two_theta - 37.0) / 0.25) ** 2)
        + 500.0 * np.exp(-0.5 * ((two_theta - 46.0) / 0.35) ** 2)
    )
    pd.DataFrame({0: two_theta, 1: intensity}).to_csv(
        path, sep=" ", header=False, index=False, float_format="%.10f"
    )


def _case_config() -> dict[str, object]:
    return {
        "case_id": "test-rwgs-case",
        "dataset": {
            "title": "Test public dataset fixture",
            "doi": "10.0000/test",
            "version": "test",
            "license": "CC-BY-4.0",
        },
        "primary_sample": {
            "sample_id": "rwgs-5wt-cu-al2o3",
            "source_label": "5%Cu/Al2O3",
        },
        "selected_sources": {
            "xrd": "xrd_archive/sample.ASC",
            "sem": "sem_eds_archive/sample.tif",
            "eds": "sem_eds_archive/sample.xlsx",
        },
        "xrd": {
            "expected_row_count": 4401,
            "expected_start_two_theta_deg": 2.01,
            "expected_end_two_theta_deg": 90.01,
            "expected_step_deg": 0.02,
            "smoothing_window": 11,
            "smoothing_polyorder": 3,
            "prominence_fraction": 0.05,
            "min_distance_samples": 3,
        },
        "sem": {
            "image_shape": [768, 1024],
            "analytical_crop": {
                "x_start": 0,
                "x_end": 1024,
                "y_start": 0,
                "y_end": 704,
                "reason": "Exclude footer.",
            },
            "manual_footer_review": {
                "instrument": "test SEM",
                "magnification": "1.45 kX",
                "working_distance_mm": 2.9,
                "accelerating_voltage_kv": 1.5,
                "signal": "ESB",
                "noise_reduction": "Pixel Avg.",
                "esb_grid_voltage_v": 800,
                "acquisition_date": "2022-06-01",
                "acquisition_time": "17:03:02",
                "scale_bar_microns": 10.0,
                "scale_bar_start_x_px": 193,
                "scale_bar_end_x_px": 323,
                "scale_bar_y_px": 743,
                "scale_bar_pixel_distance": 130,
                "microns_per_pixel": 10.0 / 130.0,
                "calibration_basis": "fixture",
            },
            "quantitative_segmentation_gate": {
                "status": "blocked_method_mismatch",
                "allowed": False,
                "reason": "ESB contrast is not a validated particle-boundary signal.",
                "allowed_output": "qualitative inspection only",
            },
        },
        "eds": {
            "project_label": "Cu-Al2O3",
            "specimen_label": "Specimen 1",
            "site_label": "Site 3",
            "acquisition_timestamp_from_filename": "2023-09-18T17:48:56",
            "atomic_percent_basis": "derived",
            "source_exclusion_note_policy": "preserve all rows",
            "atomic_weights_g_mol": {
                "C": 12.011,
                "O": 15.999,
                "Al": 26.9815385,
                "Si": 28.085,
                "Ni": 58.6934,
                "Cu": 63.546,
                "Au": 196.96657,
            },
            "unexpected_element_review": {
                "elements": ["Ni"],
                "weight_percent_threshold": 0.5,
                "reason": "Ni is not nominal.",
            },
        },
        "evidence_classification": {"level": "Diagnostic"},
    }


def test_xrd_adapter_preserves_values_and_order(tmp_path: Path) -> None:
    source = tmp_path / "source.ASC"
    destination = tmp_path / "canonical.csv"
    _write_xrd_fixture(source)
    record = adapt_xrd_asc(source, destination, _case_config()["xrd"])
    frame = pd.read_csv(destination)
    assert len(frame) == 4401
    assert frame.iloc[0].to_dict() == pytest.approx({"two_theta": 2.01, "intensity": frame.iloc[0]["intensity"]})
    assert frame["two_theta"].iloc[-1] == pytest.approx(90.01)
    assert record["rows_removed"] == 0
    assert record["sorting_applied"] is False
    assert record["interpolation_applied"] is False
    assert record["numeric_values_modified"] is False


def test_eds_source_rows_are_preserved_and_atomic_percent_is_derived(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    _write_minimal_eds_xlsx(source)
    source_table, metadata = extract_eds_weight_table(source)
    assert source_table["element"].tolist() == ["C", "O", "Al", "Si", "Ni", "Cu", "Au"]
    assert source_table["weight_percent"].sum() == pytest.approx(100.0)
    assert metadata["source_note"].startswith("NOTE:")

    derived = derive_atomic_percent(
        source_table, _case_config()["eds"]["atomic_weights_g_mol"]
    )
    assert derived["atomic_percent"].sum() == pytest.approx(100.0)
    assert set(derived["element"]) == {"C", "O", "Al", "Si", "Ni", "Cu", "Au"}

    source_table_path = tmp_path / "reported.csv"
    canonical_path = tmp_path / "canonical.csv"
    _, record = adapt_eds_xlsx(
        source,
        source_table_path,
        canonical_path,
        _case_config()["eds"],
    )
    assert record["source_rows_removed"] == 0
    assert record["unexpected_elements"] == [{"element": "Ni", "weight_percent": 21.49}]


def test_sem_suitability_blocks_quantitative_segmentation(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    _write_sem_fixture(source)
    record = inspect_sem_source(source, tmp_path / "sem-output", _case_config()["sem"])
    assert record["status"] == "blocked_method_mismatch"
    assert record["quantitative_segmentation_allowed"] is False
    assert record["quantitative_segmentation_executed"] is False
    assert record["calculated_microns_per_pixel"] == pytest.approx(10.0 / 130.0)
    assert Path(record["cropped_image_path"]).is_file()
    assert not (tmp_path / "sem-output" / "sem_measurements.csv").exists()


def test_full_case_exports_diagnostic_evidence_without_sem_metrics(tmp_path: Path) -> None:
    discovery = tmp_path / "discovery"
    xrd_source = discovery / "extracted" / "xrd_archive" / "sample.ASC"
    sem_source = discovery / "extracted" / "sem_eds_archive" / "sample.tif"
    eds_source = discovery / "extracted" / "sem_eds_archive" / "sample.xlsx"
    xrd_source.parent.mkdir(parents=True)
    sem_source.parent.mkdir(parents=True)
    _write_xrd_fixture(xrd_source)
    _write_sem_fixture(sem_source)
    _write_minimal_eds_xlsx(eds_source)

    config_path = tmp_path / "case.json"
    config_path.write_text(json.dumps(_case_config()), encoding="utf-8")
    output = tmp_path / "result"
    summary = run_case(config_path, discovery, output)

    assert summary["evidence_level"] == "Diagnostic"
    assert summary["xrd"]["status"] == "executed"
    assert summary["xrd"]["detected_peak_count"] >= 2
    assert summary["sem"]["status"] == "blocked_method_mismatch"
    assert summary["sem"]["quantitative_segmentation_executed"] is False
    assert summary["eds"]["source_rows_removed"] == 0
    assert summary["eds"]["nominal_composition_confirmed"] is False
    assert summary["same_physical_aliquot_confirmed"] is False

    manifest = json.loads((output / "characterization_manifest.json").read_text(encoding="utf-8"))
    assert manifest["analysis_count"] == 3
    sem_analysis = next(item for item in manifest["analyses"] if item["instrument"] == "sem")
    assert sem_analysis["features"] == []
    assert "quantitative_segmentation_not_executed" in sem_analysis["warnings"]
    eds_analysis = next(item for item in manifest["analyses"] if item["instrument"] == "eds")
    assert "unexpected_nickel_conflicts_with_nominal_sample_description" in eds_analysis["warnings"]

    features = pd.read_csv(output / "characterization_features_long.csv")
    assert set(features["instrument"]) == {"xrd", "eds"}
    assert "sem" not in set(features["instrument"])
    assert not (output / "analyses" / "sem" / "sem_measurements.csv").exists()
    assert "legacy `mca analyze-all` report was intentionally not generated" in (
        output / "case_validation_report.md"
    ).read_text(encoding="utf-8")
