"""Run the public 5 wt% Cu/Al2O3 XRD/SEM/EDS diagnostic case.

The runner executes XRD peak-candidate extraction, blocks scientifically
unsuitable SEM threshold segmentation, and adapts the source EDS XLSX while
preserving every reported element. Atomic percent is derived explicitly from
source-reported weight percent because the workbook does not report atomic
percent. No phase, particle-size, nominal-composition, or mechanism claim is
made.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import cv2
import numpy as np
import pandas as pd

from mca.contracts import AnalysisResult, PreprocessingStep, write_analysis_manifest
from mca.eds import analyze_eds
from mca.feature_records import (
    build_eds_feature_records,
    build_xrd_feature_records,
    records_to_frame,
)
from mca.provenance import build_analysis_result, preprocessing_fingerprint, sha256_file
from mca.xrd import analyze_xrd


DEFAULT_CONFIG = Path("case_studies/public_rwgs_xrd_sem_eds/case_config.json")
MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve_selected_source(discovery_dir: Path, relative_path: str) -> Path:
    source = discovery_dir / "extracted" / Path(relative_path)
    if not source.is_file():
        raise FileNotFoundError(f"Selected public source file was not found: {source}")
    return source


def adapt_xrd_asc(source_path: str | Path, destination: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    """Convert the selected headerless ASC file without sorting or interpolation."""
    source, destination = Path(source_path), Path(destination)
    frame = pd.read_csv(source, sep=r"\s+", header=None, names=["two_theta", "intensity"])
    if frame.shape[1] != 2:
        raise ValueError(f"Expected two XRD columns; found {frame.shape[1]}.")
    for column in ("two_theta", "intensity"):
        original = frame[column]
        numeric = pd.to_numeric(original, errors="coerce")
        invalid = numeric.isna() & original.notna() & original.astype(str).str.strip().ne("")
        if invalid.any():
            raise ValueError(f"XRD column {column!r} contains non-numeric source values.")
        frame[column] = numeric
    if frame.isna().any(axis=None):
        raise ValueError("Selected XRD source contains missing numeric values.")

    expected_rows = int(config["expected_row_count"])
    if len(frame) != expected_rows:
        raise ValueError(f"Expected {expected_rows} XRD rows; found {len(frame)}.")
    values = frame["two_theta"].to_numpy(dtype=float)
    differences = np.diff(values)
    if not np.all(differences > 0):
        raise ValueError("Selected XRD source is not strictly increasing in acquisition order.")
    expected_step = float(config["expected_step_deg"])
    if not np.allclose(differences, expected_step, rtol=0.0, atol=1e-9):
        raise ValueError("Selected XRD source does not have the configured constant 2theta step.")
    if not np.isclose(values[0], float(config["expected_start_two_theta_deg"]), atol=1e-9):
        raise ValueError("Unexpected XRD start angle.")
    if not np.isclose(values[-1], float(config["expected_end_two_theta_deg"]), atol=1e-9):
        raise ValueError("Unexpected XRD end angle.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(destination, index=False)
    return {
        "adapter": "headerless_whitespace_asc_to_canonical_csv",
        "source_path": str(source),
        "source_sha256": sha256_file(source),
        "canonical_path": str(destination),
        "canonical_sha256": sha256_file(destination),
        "source_row_count": int(len(frame)),
        "canonical_row_count": int(len(frame)),
        "two_theta_start_deg": float(values[0]),
        "two_theta_end_deg": float(values[-1]),
        "two_theta_step_deg": expected_step,
        "rows_removed": 0,
        "numeric_values_modified": False,
        "sorting_applied": False,
        "interpolation_applied": False,
    }


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        payload = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ElementTree.fromstring(payload)
    strings: list[str] = []
    for item in root.findall(f"{MAIN_NS}si"):
        text = "".join(node.text or "" for node in item.iter(f"{MAIN_NS}t"))
        strings.append(text)
    return strings


def _cell_value(cell: ElementTree.Element, shared: list[str]) -> str | float | None:
    value_node = cell.find(f"{MAIN_NS}v")
    if value_node is None or value_node.text is None:
        inline = cell.find(f"{MAIN_NS}is")
        if inline is None:
            return None
        return "".join(node.text or "" for node in inline.iter(f"{MAIN_NS}t"))
    raw = value_node.text
    if cell.attrib.get("t") == "s":
        return shared[int(raw)]
    try:
        return float(raw)
    except ValueError:
        return raw


def read_xlsx_sheet_cells(path: str | Path, worksheet_xml: str = "xl/worksheets/sheet1.xml") -> dict[str, Any]:
    """Read basic shared-string/numeric XLSX cells using only the standard library."""
    with zipfile.ZipFile(path) as archive:
        shared = _shared_strings(archive)
        root = ElementTree.fromstring(archive.read(worksheet_xml))
    cells: dict[str, Any] = {}
    for cell in root.iter(f"{MAIN_NS}c"):
        reference = cell.attrib.get("r")
        if reference:
            cells[reference] = _cell_value(cell, shared)
    return cells


def _row_number(reference: str) -> int:
    match = re.search(r"(\d+)$", reference)
    if match is None:
        raise ValueError(f"Invalid XLSX cell reference: {reference}")
    return int(match.group(1))


def _column_letters(reference: str) -> str:
    match = re.match(r"([A-Z]+)", reference)
    if match is None:
        raise ValueError(f"Invalid XLSX cell reference: {reference}")
    return match.group(1)


def extract_eds_weight_table(source_path: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Extract the source-reported EDS weight-percent table and workbook note."""
    cells = read_xlsx_sheet_cells(source_path)
    rows: dict[int, dict[str, Any]] = {}
    for reference, value in cells.items():
        rows.setdefault(_row_number(reference), {})[_column_letters(reference)] = value

    header_row = None
    for row_number, values in sorted(rows.items()):
        if str(values.get("A", "")).strip() == "Element" and str(values.get("F", "")).strip() == "Wt%":
            header_row = row_number
            break
    if header_row is None:
        raise ValueError("Could not locate the EDS Element/Wt% table in the source XLSX.")

    records: list[dict[str, Any]] = []
    for row_number in range(header_row + 1, max(rows) + 1):
        values = rows.get(row_number, {})
        element = str(values.get("A", "")).strip()
        if element == "Total:":
            break
        if not element:
            continue
        weight_percent = values.get("F")
        if weight_percent is None:
            continue
        records.append(
            {
                "element": element,
                "line_type": values.get("B"),
                "k_factor": values.get("C"),
                "k_factor_type": values.get("D"),
                "absorption_correction": values.get("E"),
                "weight_percent": float(weight_percent),
                "weight_percent_sigma": float(values["G"]) if values.get("G") is not None else np.nan,
                "source_row": row_number,
            }
        )
    frame = pd.DataFrame(records)
    if frame.empty:
        raise ValueError("Source XLSX EDS table contained no composition rows.")
    if not np.isclose(frame["weight_percent"].sum(), 100.0, atol=1e-6):
        raise ValueError("Source XLSX EDS weight percent does not sum to 100%.")

    note = next(
        (
            str(value).strip()
            for value in cells.values()
            if isinstance(value, str) and value.strip().startswith("NOTE:")
        ),
        None,
    )
    metadata = {
        "project_label": cells.get("B1"),
        "specimen_label": cells.get("B3"),
        "site_label": cells.get("B5"),
        "source_note": note,
        "source_row_count": int(len(frame)),
        "reported_weight_percent_total": float(frame["weight_percent"].sum()),
    }
    return frame, metadata


def derive_atomic_percent(weight_table: pd.DataFrame, atomic_weights: dict[str, float]) -> pd.DataFrame:
    """Derive atomic percent algebraically while retaining all source-reported elements."""
    missing = sorted(set(weight_table["element"]) - set(atomic_weights))
    if missing:
        raise ValueError(f"Atomic weights are not configured for source elements: {missing}")
    output = weight_table.copy()
    output["atomic_weight_g_mol"] = output["element"].map(atomic_weights).astype(float)
    output["relative_moles"] = output["weight_percent"] / output["atomic_weight_g_mol"]
    mole_total = float(output["relative_moles"].sum())
    if mole_total <= 0:
        raise ValueError("Cannot derive atomic percent from a non-positive mole total.")
    output["atomic_percent"] = output["relative_moles"] / mole_total * 100.0
    output["atomic_percent_basis"] = "derived_from_source_weight_percent"
    if not np.isclose(output["atomic_percent"].sum(), 100.0, atol=1e-9):
        raise ValueError("Derived EDS atomic percent does not sum to 100%.")
    return output


def adapt_eds_xlsx(
    source_path: str | Path,
    source_table_path: str | Path,
    canonical_path: str | Path,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    source = Path(source_path)
    source_table, metadata = extract_eds_weight_table(source)
    derived = derive_atomic_percent(source_table, config["atomic_weights_g_mol"])

    source_table_path = Path(source_table_path)
    canonical_path = Path(canonical_path)
    source_table_path.parent.mkdir(parents=True, exist_ok=True)
    source_table.to_csv(source_table_path, index=False)
    derived.to_csv(canonical_path, index=False)

    review = config["unexpected_element_review"]
    unexpected_rows = derived[
        derived["element"].isin(review["elements"])
        & (derived["weight_percent"] >= float(review["weight_percent_threshold"]))
    ]
    record = {
        "adapter": "xlsx_reported_weight_percent_with_explicit_atomic_percent_derivation",
        "source_path": str(source),
        "source_sha256": sha256_file(source),
        "source_table_path": str(source_table_path),
        "source_table_sha256": sha256_file(source_table_path),
        "canonical_path": str(canonical_path),
        "canonical_sha256": sha256_file(canonical_path),
        "source_metadata": metadata,
        "source_elements": derived["element"].tolist(),
        "reported_weight_percent_total": float(derived["weight_percent"].sum()),
        "derived_atomic_percent_total": float(derived["atomic_percent"].sum()),
        "atomic_percent_basis": config["atomic_percent_basis"],
        "source_exclusion_note_policy": config["source_exclusion_note_policy"],
        "source_rows_removed": 0,
        "reported_weight_percent_modified": False,
        "unexpected_elements": unexpected_rows[["element", "weight_percent"]].to_dict("records"),
        "unexpected_element_reason": review["reason"],
    }
    return derived, record


def inspect_sem_source(source_path: str | Path, output_dir: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    """Record SEM source readiness and block unsuitable quantitative segmentation."""
    source, output_dir = Path(source_path), Path(output_dir)
    data = np.fromfile(source, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"Could not decode selected SEM image: {source}")
    height, width = image.shape[:2]
    if [height, width] != list(config["image_shape"]):
        raise ValueError(f"Unexpected SEM image shape: {[height, width]}")

    footer = config["manual_footer_review"]
    x1, x2, y = (
        int(footer["scale_bar_start_x_px"]),
        int(footer["scale_bar_end_x_px"]),
        int(footer["scale_bar_y_px"]),
    )
    if int(footer["scale_bar_pixel_distance"]) != x2 - x1:
        raise ValueError("Configured scale-bar pixel distance does not equal endpoint separation.")
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scale_segment = gray[y, x1 : x2 + 1]
    white_fraction = float(np.mean(scale_segment >= 220))
    if white_fraction < 0.95:
        raise ValueError("Configured SEM scale-bar coordinates do not match the source image.")
    calculated_scale = float(footer["scale_bar_microns"]) / float(x2 - x1)
    if not np.isclose(calculated_scale, float(footer["microns_per_pixel"]), atol=1e-12):
        raise ValueError("Configured SEM microns-per-pixel is inconsistent with the scale bar.")

    crop = config["analytical_crop"]
    xs, xe = int(crop["x_start"]), int(crop["x_end"])
    ys, ye = int(crop["y_start"]), int(crop["y_end"])
    if not (0 <= xs < xe <= width and 0 <= ys < ye <= height):
        raise ValueError("Configured SEM crop is outside the source image.")
    cropped = image[ys:ye, xs:xe]
    output_dir.mkdir(parents=True, exist_ok=True)
    cropped_path = output_dir / "sem_field_cropped.png"
    success, encoded = cv2.imencode(".png", cropped)
    if not success:
        raise ValueError("Could not encode cropped SEM image.")
    encoded.tofile(cropped_path)

    gate = config["quantitative_segmentation_gate"]
    record = {
        "status": gate["status"],
        "quantitative_segmentation_allowed": bool(gate["allowed"]),
        "quantitative_segmentation_executed": False,
        "block_reason": gate["reason"],
        "allowed_output": gate["allowed_output"],
        "source_file": str(source),
        "source_sha256": sha256_file(source),
        "source_image_shape": list(image.shape),
        "source_dtype": str(image.dtype),
        "analytical_crop": crop,
        "cropped_image_path": str(cropped_path),
        "cropped_image_sha256": sha256_file(cropped_path),
        "footer_metadata": footer,
        "scale_bar_white_fraction": white_fraction,
        "calculated_microns_per_pixel": calculated_scale,
        "scientific_limitation": (
            "The selected ESB image provides compositional contrast on overlapping catalyst agglomerates. "
            "The existing Otsu external-contour method is not a validated particle-boundary or phase-separation method."
        ),
    }
    suitability_path = output_dir / "sem_suitability.json"
    suitability_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    record["suitability_path"] = str(suitability_path)
    return record


def _eds_features_with_truthful_methods(
    table: pd.DataFrame,
    *,
    sample_id: str,
    measurement_id: str,
    source_file: Path,
    preprocessing_id: str,
) -> list[Any]:
    records = build_eds_feature_records(
        table,
        sample_id=sample_id,
        measurement_id=measurement_id,
        source_file=source_file,
        preprocessing_id=preprocessing_id,
    )
    adjusted = []
    for record in records:
        if "atomic_percent" in record.feature_name:
            adjusted.append(
                replace(
                    record,
                    method="atomic_percent_derived_from_source_weight_percent",
                    quality_flag="derived_review_required",
                )
            )
        else:
            adjusted.append(
                replace(
                    record,
                    method="source_xlsx_reported_weight_percent",
                    quality_flag="review_required",
                )
            )
    return adjusted


def build_comparability_matrix(config: dict[str, Any], output_path: Path) -> pd.DataFrame:
    sample = config["primary_sample"]
    rows = [
        {
            "modality": "xrd",
            "source_sample_label": sample["source_label"],
            "same_nominal_sample_label_confirmed": True,
            "same_physical_aliquot_confirmed": False,
            "analysis_execution": "executed",
            "comparability_status": "conditionally_comparable",
            "scientific_use": "peak-candidate and data-quality review only",
            "primary_limitation": "X-ray source, instrument, and instrumental broadening were not provided.",
        },
        {
            "modality": "sem",
            "source_sample_label": sample["source_label"],
            "same_nominal_sample_label_confirmed": True,
            "same_physical_aliquot_confirmed": False,
            "analysis_execution": "quantitative_analysis_blocked",
            "comparability_status": "source_available_analysis_blocked",
            "scientific_use": "source, acquisition, scale, and qualitative morphology review only",
            "primary_limitation": config["sem"]["quantitative_segmentation_gate"]["reason"],
        },
        {
            "modality": "eds",
            "source_sample_label": sample["source_label"],
            "same_nominal_sample_label_confirmed": True,
            "same_physical_aliquot_confirmed": False,
            "analysis_execution": "executed_with_adapter",
            "comparability_status": "conditionally_comparable_with_composition_conflict",
            "scientific_use": "source-table and composition-quality review only",
            "primary_limitation": "Source EDS reports 21.49 wt% Ni despite a nominal Cu/gamma-Al2O3 synthesis description.",
        },
    ]
    frame = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    return frame


def _peak_summary(peak_table: pd.DataFrame) -> str:
    if peak_table.empty:
        return "No peak candidates passed the configured diagnostic threshold."
    strongest = peak_table.sort_values("intensity", ascending=False).head(5)
    values = ", ".join(f"{row.two_theta_deg:.3f} deg" for row in strongest.itertuples())
    return f"{len(peak_table)} candidates; five strongest candidate positions: {values}."


def write_case_report(
    output_path: Path,
    config: dict[str, Any],
    xrd_result: dict[str, object],
    sem_record: dict[str, Any],
    eds_result: dict[str, object],
    eds_adapter: dict[str, Any],
    manifest_path: Path,
    feature_path: Path,
    comparability_path: Path,
) -> None:
    composition = eds_result["composition_table"]
    if not isinstance(composition, pd.DataFrame):
        raise TypeError("EDS analyzer did not return a composition table.")
    table_lines = ["| Element | Source wt% | Derived at% |", "|---|---:|---:|"]
    canonical = pd.read_csv(eds_adapter["canonical_path"])
    for row in canonical.sort_values("weight_percent", ascending=False).itertuples():
        table_lines.append(f"| {row.element} | {row.weight_percent:.3f} | {row.atomic_percent:.3f} |")
    unexpected = eds_adapter["unexpected_elements"]
    unexpected_text = ", ".join(
        f"{row['element']} {row['weight_percent']:.2f} wt%" for row in unexpected
    ) or "none"

    report = f"""# Public RWGS 5 wt% Cu/Al2O3 XRD-SEM-EDS Validation Case

## Source and sample identity

- Dataset: `{config['dataset']['title']}`
- DOI: `{config['dataset']['doi']}`
- Version/license: `{config['dataset']['version']}` / `{config['dataset']['license']}`
- Selected nominal sample: `{config['primary_sample']['source_label']}`
- Preparation: incipient wetness impregnation, 120 degC drying for 2 h, 450 degC calcination for 6 h.
- Same study and same nominal sample label: confirmed.
- Same physical aliquot across XRD, SEM, and EDS: **not confirmed**.

## XRD

- Execution: completed on the 4,401-row source pattern without sorting, interpolation, or value modification.
- Result: {_peak_summary(xrd_result['peak_table'])}
- Radiation source, wavelength, diffractometer, and instrumental broadening were not supplied; Scherrer estimates and phase assignment were not performed.

## SEM

- Source metadata reviewed from the embedded footer: `{config['sem']['manual_footer_review']['instrument']}`, {config['sem']['manual_footer_review']['accelerating_voltage_kv']} kV, ESB signal, 10 micrometre scale bar.
- Reviewed scale: `{sem_record['calculated_microns_per_pixel']:.9f}` micrometres/pixel.
- Quantitative segmentation: **blocked** (`{sem_record['status']}`).
- Reason: {sem_record['block_reason']}
- The footer was cropped only for qualitative field review; no particle-size or area-fraction table was generated.

## EDS

- Source workbook labels: `{config['eds']['project_label']}`, `{config['eds']['specimen_label']}`, `{config['eds']['site_label']}`.
- Source wt% rows removed: `0`.
- Atomic percent is derived from source wt% using explicitly recorded atomic weights; it is not instrument-reported.
- The workbook note about discarding C, Si, and Au was preserved but not automatically applied.
- Unexpected nominal-composition conflict: **{unexpected_text}**.

{chr(10).join(table_lines)}

## Comparability and evidence closeout

- Evidence level: **Diagnostic**.
- Strongest evidence: checksum-verified public acquisition, exact same nominal 5% Cu/Al2O3 filename mapping, preserved XRD values, preserved EDS wt% rows, and an explicit SEM suitability block.
- Primary limitation: identical physical aliquots are unconfirmed; SEM quantitative segmentation is unsuitable; the EDS Ni result conflicts with the nominal synthesis description; key XRD and EDS acquisition metadata are absent.
- Evidence that would change the conclusion: sample/aliquot linkage records, original SEM/EDS acquisition metadata, explanation or repeat measurement for Ni, validated SEM segmentation labels, and XRD instrument/radiation metadata.
- Suitable for: software integration, provenance, adapter, and data-quality diagnostics.
- Not suitable for: phase confirmation, particle-size claims, nominal-composition confirmation, catalytic mechanism claims, or engineering release decisions.

## Evidence files

- Analysis manifest: `{manifest_path}`
- Long-format features: `{feature_path}`
- Comparability matrix: `{comparability_path}`
- SEM suitability record: `{sem_record['suitability_path']}`

The legacy `mca analyze-all` report was intentionally not generated because it would imply that quantitative SEM measurements were available. The individual analyzer algorithms were not modified.
"""
    output_path.write_text(report, encoding="utf-8")


def run_case(config_path: Path, discovery_dir: Path, output_dir: Path) -> dict[str, Any]:
    config = load_json(config_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    adapters_dir = output_dir / "adapters"
    analyses_dir = output_dir / "analyses"
    adapters_dir.mkdir(parents=True, exist_ok=True)
    analyses_dir.mkdir(parents=True, exist_ok=True)

    xrd_source = resolve_selected_source(discovery_dir, config["selected_sources"]["xrd"])
    sem_source = resolve_selected_source(discovery_dir, config["selected_sources"]["sem"])
    eds_source = resolve_selected_source(discovery_dir, config["selected_sources"]["eds"])
    selected_sources = {
        "xrd": {"path": str(xrd_source), "sha256": sha256_file(xrd_source)},
        "sem": {"path": str(sem_source), "sha256": sha256_file(sem_source)},
        "eds": {"path": str(eds_source), "sha256": sha256_file(eds_source)},
    }
    source_selection_path = output_dir / "selected_source_manifest.json"
    source_selection_path.write_text(
        json.dumps(selected_sources, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    canonical_xrd = adapters_dir / "xrd_5wt_cu_al2o3.csv"
    xrd_adapter = adapt_xrd_asc(xrd_source, canonical_xrd, config["xrd"])
    xrd_output = analyses_dir / "xrd"
    xrd_analysis = analyze_xrd(
        canonical_xrd,
        xrd_output,
        smoothing_window=int(config["xrd"]["smoothing_window"]),
        smoothing_polyorder=int(config["xrd"]["smoothing_polyorder"]),
        prominence_fraction=float(config["xrd"]["prominence_fraction"]),
        min_distance=int(config["xrd"]["min_distance_samples"]),
        wavelength=None,
    )

    sem_output = analyses_dir / "sem"
    sem_record = inspect_sem_source(sem_source, sem_output, config["sem"])

    source_eds_table = adapters_dir / "eds_source_reported_weight_percent.csv"
    canonical_eds = adapters_dir / "eds_with_derived_atomic_percent.csv"
    _, eds_adapter = adapt_eds_xlsx(
        eds_source,
        source_eds_table,
        canonical_eds,
        config["eds"],
    )
    eds_output = analyses_dir / "eds"
    eds_analysis = analyze_eds(canonical_eds, eds_output)

    sample_id = config["primary_sample"]["sample_id"]
    xrd_steps = [
        PreprocessingStep(
            "rwgs-xrd-source-adapter",
            xrd_adapter["adapter"],
            {
                "rows_removed": 0,
                "sorting_applied": False,
                "interpolation_applied": False,
                "numeric_values_modified": False,
            },
        ),
        PreprocessingStep(
            "xrd-savgol-smoothing",
            "savgol_smoothing",
            {
                "window_length": config["xrd"]["smoothing_window"],
                "polyorder": config["xrd"]["smoothing_polyorder"],
            },
        ),
        PreprocessingStep(
            "xrd-peak-detection",
            "scipy_find_peaks",
            {
                "prominence_fraction": config["xrd"]["prominence_fraction"],
                "minimum_distance_samples": config["xrd"]["min_distance_samples"],
            },
        ),
    ]
    eds_steps = [
        PreprocessingStep(
            "rwgs-eds-xlsx-extraction",
            "extract_source_reported_weight_percent_from_xlsx",
            {"source_rows_removed": 0, "reported_weight_percent_modified": False},
        ),
        PreprocessingStep(
            "rwgs-eds-atomic-percent-derivation",
            "derive_atomic_percent_from_weight_percent",
            {"atomic_weights_g_mol": config["eds"]["atomic_weights_g_mol"]},
            notes="Atomic percent was not reported by the source workbook.",
        ),
        PreprocessingStep("eds-sort", "sort_by_weight_percent", {"ascending": False}),
    ]
    sem_steps = [
        PreprocessingStep(
            "rwgs-sem-footer-review",
            "manual_embedded_footer_metadata_and_scale_review",
            config["sem"]["manual_footer_review"],
        ),
        PreprocessingStep(
            "rwgs-sem-footer-crop",
            "crop_instrument_annotation_footer",
            config["sem"]["analytical_crop"],
            notes="Crop is for qualitative review only; quantitative segmentation was not executed.",
        ),
    ]

    xrd_preprocessing_id = preprocessing_fingerprint("xrd", xrd_steps)
    eds_preprocessing_id = preprocessing_fingerprint("eds", eds_steps)
    xrd_features = build_xrd_feature_records(
        xrd_analysis["peak_table"],
        sample_id=sample_id,
        measurement_id=f"{sample_id}-xrd",
        source_file=xrd_source,
        preprocessing_id=xrd_preprocessing_id,
    )
    eds_features = _eds_features_with_truthful_methods(
        eds_analysis["composition_table"],
        sample_id=sample_id,
        measurement_id=f"{sample_id}-eds",
        source_file=eds_source,
        preprocessing_id=eds_preprocessing_id,
    )
    all_features = [*xrd_features, *eds_features]
    feature_path = output_dir / "characterization_features_long.csv"
    records_to_frame(all_features).to_csv(feature_path, index=False)

    xrd_result = build_analysis_result(
        measurement_id=f"{sample_id}-xrd",
        sample_id=sample_id,
        instrument="xrd",
        source_file=xrd_source,
        acquisition_metadata={
            "public_dataset_doi": config["dataset"]["doi"],
            "two_theta_start_deg": xrd_adapter["two_theta_start_deg"],
            "two_theta_end_deg": xrd_adapter["two_theta_end_deg"],
            "two_theta_step_deg": xrd_adapter["two_theta_step_deg"],
            "xray_source": None,
            "instrument": None,
            "instrumental_broadening": None,
        },
        preprocessing_steps=xrd_steps,
        tables={"canonical_input": canonical_xrd, "peak_table": xrd_analysis["peak_table_path"]},
        figures={"pattern_with_peaks": xrd_analysis["plot_path"]},
        features=xrd_features,
        warnings=[
            "xrd_instrument_not_provided",
            "xrd_radiation_source_not_provided",
            "instrumental_broadening_not_provided",
            "scherrer_estimate_not_executed",
        ],
        limitations=[
            "Detected XRD peaks and FWHM values do not confirm phases.",
            "Missing radiation and instrument metadata limit cross-study comparison.",
        ],
    )
    sem_result = build_analysis_result(
        measurement_id=f"{sample_id}-sem",
        sample_id=sample_id,
        instrument="sem",
        source_file=sem_source,
        acquisition_metadata={
            "public_dataset_doi": config["dataset"]["doi"],
            **config["sem"]["manual_footer_review"],
            "same_physical_aliquot_confirmed": False,
        },
        preprocessing_steps=sem_steps,
        tables={"suitability_gate": sem_record["suitability_path"]},
        figures={"cropped_field": sem_record["cropped_image_path"]},
        features=[],
        warnings=[
            "quantitative_segmentation_not_executed",
            "esb_compositional_contrast_not_particle_boundary_contrast",
        ],
        limitations=[sem_record["scientific_limitation"]],
    )
    eds_warnings = [
        "atomic_percent_derived_not_instrument_reported",
        "source_exclusion_note_preserved_not_applied",
        "eds_acquisition_metadata_incomplete",
    ]
    if eds_adapter["unexpected_elements"]:
        eds_warnings.append("unexpected_nickel_conflicts_with_nominal_sample_description")
    eds_result = build_analysis_result(
        measurement_id=f"{sample_id}-eds",
        sample_id=sample_id,
        instrument="eds",
        source_file=eds_source,
        acquisition_metadata={
            "public_dataset_doi": config["dataset"]["doi"],
            "project_label": config["eds"]["project_label"],
            "specimen_label": config["eds"]["specimen_label"],
            "site_label": config["eds"]["site_label"],
            "acquisition_timestamp_from_filename": config["eds"]["acquisition_timestamp_from_filename"],
            "atomic_percent_basis": config["eds"]["atomic_percent_basis"],
            "source_note": eds_adapter["source_metadata"].get("source_note"),
        },
        preprocessing_steps=eds_steps,
        tables={
            "source_reported_weight_percent": source_eds_table,
            "canonical_with_derived_atomic_percent": canonical_eds,
            "composition_table": eds_analysis["table_path"],
        },
        figures={"composition_chart": eds_analysis["chart_path"]},
        features=eds_features,
        warnings=eds_warnings,
        limitations=[
            "EDS composition does not confirm crystalline phases or chemical states.",
            "Atomic percent is derived from reported weight percent, not instrument-reported.",
            "The unexpected Ni result prevents nominal Cu/Al2O3 composition confirmation.",
            "Quantification depends on missing acquisition, correction, geometry, and preparation details.",
        ],
    )

    manifest_path = write_analysis_manifest(
        [xrd_result, sem_result, eds_result], output_dir / "characterization_manifest.json"
    )
    comparability_path = output_dir / "comparability_matrix.csv"
    comparability = build_comparability_matrix(config, comparability_path)
    report_path = output_dir / "case_validation_report.md"
    write_case_report(
        report_path,
        config,
        xrd_analysis,
        sem_record,
        eds_analysis,
        eds_adapter,
        manifest_path,
        feature_path,
        comparability_path,
    )

    summary = {
        "case_id": config["case_id"],
        "sample_id": sample_id,
        "dataset_doi": config["dataset"]["doi"],
        "evidence_level": config["evidence_classification"]["level"],
        "xrd": {
            "status": "executed",
            "source_rows": xrd_adapter["source_row_count"],
            "detected_peak_count": int(len(xrd_analysis["peak_table"])),
            "phase_assignment_executed": False,
            "scherrer_estimate_executed": False,
        },
        "sem": {
            "status": sem_record["status"],
            "quantitative_segmentation_executed": False,
            "microns_per_pixel_reviewed": sem_record["calculated_microns_per_pixel"],
        },
        "eds": {
            "status": "executed_with_atomic_percent_derivation",
            "source_rows_removed": 0,
            "source_elements": eds_adapter["source_elements"],
            "unexpected_elements": eds_adapter["unexpected_elements"],
            "nominal_composition_confirmed": False,
        },
        "same_nominal_sample_label_confirmed": True,
        "same_physical_aliquot_confirmed": False,
        "comparability_status": dict(
            zip(comparability["modality"], comparability["comparability_status"], strict=True)
        ),
        "manifest_path": str(manifest_path),
        "feature_path": str(feature_path),
        "report_path": str(report_path),
        "selected_source_manifest_path": str(source_selection_path),
    }
    summary_path = output_dir / "case_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--discovery", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = run_case(args.config, args.discovery, args.output)
    except Exception as exc:  # noqa: BLE001 - CLI boundary must report source-specific failures.
        print(f"public RWGS case failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
