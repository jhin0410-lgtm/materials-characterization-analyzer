"""Run a provenance-first real-data DWCNT multimodal validation case.

The runner adapts selected public Dataverse source files into the repository's
canonical input contracts, executes only scientifically suitable analyzers, and
writes comparability and claim-closeout evidence. It does not assign phases,
functional groups, chemical states, reactions, or mechanisms.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd

from mca.contracts import AnalysisResult, PreprocessingStep, write_analysis_manifest
from mca.feature_records import records_to_frame
from mca.ftir import analyze_ftir
from mca.provenance import preprocessing_fingerprint, sha256_file
from mca.raman import analyze_raman
from mca.thermal import analyze_thermal
from mca.xps import analyze_xps


DEFAULT_CONFIG = Path("case_studies/public_carbon_multimodal/case_config.json")
EXECUTED_MODALITIES = ("raman", "ftir", "xps", "tga")
REQUIRED_DOWNLOADS = (*EXECUTED_MODALITIES, "tem", "readme")


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_delimited_table(path: str | Path) -> tuple[pd.DataFrame, str]:
    source = Path(path)
    attempts = ((";", "semicolon"), ("\t", "tab"), (",", "comma"))
    errors: list[str] = []
    for separator, label in attempts:
        try:
            frame = pd.read_csv(source, sep=separator, engine="python")
        except Exception as exc:  # noqa: BLE001 - adapter reports all attempted formats.
            errors.append(f"{label}: {exc}")
            continue
        if frame.shape[1] >= 2:
            return frame, label
    raise ValueError(
        f"Could not parse public source table {source} with semicolon, tab, or comma delimiters. "
        f"Attempts: {' | '.join(errors)}"
    )


def _numeric_series(frame: pd.DataFrame, index: int, *, label: str) -> pd.Series:
    if index >= frame.shape[1]:
        raise ValueError(f"Source table does not contain required {label} column index {index}.")
    original = frame.iloc[:, index]
    numeric = pd.to_numeric(original, errors="coerce")
    invalid = numeric.isna() & original.notna() & original.astype(str).str.strip().ne("")
    if invalid.any():
        value = original.loc[invalid].iloc[0]
        raise ValueError(f"Source {label} column contains non-numeric value {value!r}.")
    return numeric


def adapt_two_column_source(
    source_path: str | Path,
    destination: str | Path,
    *,
    x_name: str,
    y_name: str,
) -> dict[str, Any]:
    """Adapt one public two-column table without changing numeric values."""
    source = Path(source_path)
    destination = Path(destination)
    frame, delimiter = _read_delimited_table(source)
    if frame.shape[1] != 2:
        raise ValueError(
            f"Expected exactly two source columns for {source.name}; found {frame.shape[1]}."
        )
    x = _numeric_series(frame, 0, label=x_name)
    y = _numeric_series(frame, 1, label=y_name)
    valid = x.notna() & y.notna()
    if not valid.any():
        raise ValueError(f"No complete numeric rows were found in {source}.")
    incomplete_rows = int((~valid).sum())
    canonical = pd.DataFrame({x_name: x.loc[valid], y_name: y.loc[valid]}).reset_index(drop=True)
    if len(canonical) < 7:
        raise ValueError(f"Canonical table for {source.name} contains fewer than 7 rows.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    canonical.to_csv(destination, index=False)
    return {
        "adapter": "public_two_column_to_canonical_csv",
        "source_path": str(source),
        "source_sha256": sha256_file(source),
        "canonical_path": str(destination),
        "canonical_sha256": sha256_file(destination),
        "source_delimiter": delimiter,
        "source_headers": [str(value) for value in frame.columns],
        "column_mapping": {str(frame.columns[0]): x_name, str(frame.columns[1]): y_name},
        "source_row_count": int(len(frame)),
        "canonical_row_count": int(len(canonical)),
        "incomplete_rows_removed": incomplete_rows,
        "numeric_values_modified": False,
    }


def adapt_tga_air_source(source_path: str | Path, destination: str | Path) -> dict[str, Any]:
    """Map the documented seven-column TGA-air export to temperature/time/retention."""
    source = Path(source_path)
    destination = Path(destination)
    frame, delimiter = _read_delimited_table(source)
    if frame.shape[1] < 7:
        raise ValueError(
            f"The documented TGA-air source requires at least 7 columns; found {frame.shape[1]}."
        )
    temperature = _numeric_series(frame, 0, label="temperature")
    time_s = _numeric_series(frame, 1, label="time")
    mass_retention = _numeric_series(frame, 5, label="mass retention percent")
    valid = temperature.notna() & time_s.notna() & mass_retention.notna()
    if not valid.any():
        raise ValueError(f"No complete TGA rows were found in {source}.")
    canonical = pd.DataFrame(
        {
            "temperature_c": temperature.loc[valid],
            "time_s": time_s.loc[valid],
            "signal": mass_retention.loc[valid],
        }
    ).reset_index(drop=True)
    if len(canonical) < 7:
        raise ValueError("Canonical TGA table contains fewer than 7 rows.")
    if not np.all(np.diff(canonical["temperature_c"].to_numpy(dtype=float)) > 0):
        raise ValueError("Selected TGA-air source is not one strictly increasing heating segment.")
    if not np.all(np.diff(canonical["time_s"].to_numpy(dtype=float)) > 0):
        raise ValueError("Selected TGA-air source time axis is not strictly increasing.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    canonical.to_csv(destination, index=False)
    return {
        "adapter": "documented_tga_air_seven_column_mapping",
        "source_path": str(source),
        "source_sha256": sha256_file(source),
        "canonical_path": str(destination),
        "canonical_sha256": sha256_file(destination),
        "source_delimiter": delimiter,
        "source_headers": [str(value) for value in frame.columns],
        "column_mapping": {
            str(frame.columns[0]): "temperature_c",
            str(frame.columns[1]): "time_s",
            str(frame.columns[5]): "signal_mass_retention_percent",
        },
        "source_row_count": int(len(frame)),
        "canonical_row_count": int(len(canonical)),
        "incomplete_rows_removed": int((~valid).sum()),
        "numeric_values_modified": False,
        "mapping_basis": "Dataset_Raw/ReadMe_Raw.pdf TGA-air seven-column definition",
    }


def _downloaded_source(downloads: dict[str, Any], modality: str, discovery_dir: Path) -> Path:
    record = downloads.get(modality) or {}
    if record.get("status") != "downloaded":
        raise ValueError(f"Required modality {modality!r} was not downloaded: {record.get('status')}")
    stored = Path(str(record.get("local_path", "")))
    candidates = [stored, discovery_dir / "raw" / stored.name]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"Downloaded modality {modality!r} could not be resolved from recorded path {stored}."
    )


def _rebind_result_to_original_source(
    analysis: dict[str, object],
    *,
    raw_source: Path,
    adapter_record: dict[str, Any],
) -> AnalysisResult:
    """Replace canonical-file provenance with original-file provenance and adapter history."""
    result = analysis["analysis_result"]
    if not isinstance(result, AnalysisResult):
        raise TypeError("Analyzer did not return an AnalysisResult contract.")
    adapter_step = PreprocessingStep(
        "public-source-adapter",
        str(adapter_record["adapter"]),
        {
            "source_sha256": adapter_record["source_sha256"],
            "canonical_sha256": adapter_record["canonical_sha256"],
            "source_delimiter": adapter_record.get("source_delimiter"),
            "column_mapping": adapter_record.get("column_mapping"),
            "incomplete_rows_removed": adapter_record.get("incomplete_rows_removed", 0),
            "numeric_values_modified": adapter_record.get("numeric_values_modified", False),
        },
        notes="Case-study adapter only; analyzer algorithms were not changed.",
    )
    steps = [adapter_step, *result.preprocessing_steps]
    preprocessing_id = preprocessing_fingerprint(result.instrument, steps)
    source_hash = sha256_file(raw_source)
    features = [
        replace(
            feature,
            source_file=str(raw_source),
            source_sha256=source_hash,
            preprocessing_id=preprocessing_id,
        )
        for feature in result.features
    ]
    result.source_file = str(raw_source)
    result.source_sha256 = source_hash
    result.preprocessing_steps = steps
    result.features = features
    result.acquisition_metadata.update(
        {
            "public_dataset_persistent_id": "doi:10.57745/7KA2UG",
            "public_source_original_path": adapter_record.get("source_path"),
            "public_source_original_sha256": source_hash,
            "canonical_adapter_path": adapter_record.get("canonical_path"),
            "canonical_adapter_sha256": adapter_record.get("canonical_sha256"),
        }
    )
    feature_path = analysis.get("feature_path")
    if feature_path is not None:
        records_to_frame(features).to_csv(Path(feature_path), index=False)
    analysis["features"] = features
    return result


def inspect_tem_source(
    source_path: Path,
    *,
    metadata: dict[str, Any],
    gate: dict[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    image = cv2.imread(str(source_path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"OpenCV could not decode selected TEM source {source_path}.")
    if image.ndim not in {2, 3}:
        raise ValueError(f"Unexpected TEM image shape {image.shape}.")
    record = {
        "status": gate.get("status", "blocked"),
        "quantitative_segmentation_executed": False,
        "quantitative_segmentation_allowed": bool(gate.get("allowed", False)),
        "block_reason": gate.get("reason"),
        "allowed_output": gate.get("allowed_output"),
        "source_file": str(source_path),
        "source_sha256": sha256_file(source_path),
        "image_shape": list(image.shape),
        "image_dtype": str(image.dtype),
        "acquisition_metadata": metadata,
        "scale_review": {
            "embedded_scale_bar_nm": metadata.get("embedded_scale_bar_nm"),
            "manually_reviewed_scale_bar_pixels": metadata.get(
                "manually_reviewed_scale_bar_pixels"
            ),
            "reviewed_nm_per_pixel": metadata.get("reviewed_nm_per_pixel"),
            "used_for_segmentation": False,
        },
        "scientific_limitation": (
            "The current Otsu contrast-region analyzer is not a nanotube-tracing, bundle-width, "
            "or support-grid separation method. No TEM size distribution was generated."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return record


def build_comparability_matrix(
    config: dict[str, Any],
    execution: dict[str, str],
    output_path: str | Path,
) -> pd.DataFrame:
    rows = []
    availability = config["availability_contract"]
    for modality in ("raman", "ftir", "xps", "tga", "tem", "saed", "dsc"):
        available = availability.get(modality, "unspecified")
        if modality in EXECUTED_MODALITIES:
            status = "conditionally_comparable"
            scientific_use = "diagnostic within-technique review; cautious cross-technique context"
            limitation = "Same source sample class, but identical physical aliquot is not established."
        elif modality == "tem":
            status = "source_available_analysis_blocked"
            scientific_use = "source and acquisition readiness only"
            limitation = config["suitability_gates"]["tem_quantitative_segmentation"]["reason"]
        else:
            status = "not_available_not_comparable"
            scientific_use = "none in this case"
            limitation = "The source dataset does not provide this modality; no unrelated data were substituted."
        rows.append(
            {
                "modality": modality,
                "dataset_availability": available,
                "comparability_status": status,
                "source_sample_class": config["primary_sample"]["source_label"],
                "identical_physical_aliquot_confirmed": False,
                "analysis_execution": execution.get(modality, "not_executed"),
                "scientific_use": scientific_use,
                "primary_limitation": limitation,
            }
        )
    frame = pd.DataFrame(rows)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    return frame


def _candidate_summary(analysis: dict[str, object], column: str, unit: str) -> str:
    table = analysis.get("candidate_table") or analysis.get("peak_table")
    if not isinstance(table, pd.DataFrame) or table.empty or column not in table.columns:
        return "No automatic candidates were retained by the configured diagnostic threshold."
    values = pd.to_numeric(table[column], errors="coerce").dropna().tolist()
    shown = ", ".join(f"{value:.3g} {unit}" for value in values[:8])
    suffix = "" if len(values) <= 8 else f"; {len(values) - 8} additional candidates omitted"
    return f"{len(values)} review-required candidates: {shown}{suffix}."


def write_case_report(
    output_path: Path,
    *,
    config: dict[str, Any],
    source_manifest_path: Path,
    comparability_path: Path,
    analyses: dict[str, dict[str, object]],
    tem_record: dict[str, Any],
) -> None:
    summaries = {
        "Raman": _candidate_summary(analyses["raman"], "raman_shift_cm_1", "cm^-1"),
        "FTIR": _candidate_summary(analyses["ftir"], "wavenumber_cm_1", "cm^-1"),
        "XPS": _candidate_summary(analyses["xps"], "binding_energy_corrected_ev", "eV"),
        "TGA": _candidate_summary(analyses["tga"], "temperature_c", "degC"),
    }
    warning_lines = []
    for modality, analysis in analyses.items():
        result = analysis["analysis_result"]
        warning_lines.append(
            f"- **{modality.upper()}**: "
            + (", ".join(result.warnings) if result.warnings else "no software quality warnings")
        )
    lines = [
        "# Public DWCNT Multimodal Validation Report",
        "",
        "## Result",
        "",
        "**Evidence level: Diagnostic.** The case demonstrates real public-file acquisition, "
        "checksum-backed provenance, adapter traceability, and successful execution of the existing "
        "Raman, FTIR, XPS, and TGA software contracts. It does not establish a material mechanism or "
        "formal cross-technique scientific validation.",
        "",
        "## Source",
        "",
        f"- Dataset: {config['dataset']['title']}",
        f"- Persistent ID: `{config['dataset']['persistent_id']}`",
        f"- Version: `{config['dataset']['version']}`",
        f"- License: `{config['dataset']['license']}`",
        f"- Primary source sample class: `{config['primary_sample']['source_label']}`",
        f"- Source manifest: `{source_manifest_path}`",
        f"- Comparability matrix: `{comparability_path}`",
        "",
        "## Real-data execution",
        "",
        f"- **Raman:** {summaries['Raman']}",
        f"- **FTIR:** {summaries['FTIR']}",
        f"- **XPS:** {summaries['XPS']}",
        f"- **TGA-air:** {summaries['TGA']}",
        f"- **TEM:** source decoded as shape `{tem_record['image_shape']}` and dtype "
        f"`{tem_record['image_dtype']}`, but quantitative segmentation was blocked.",
        "- **SAED:** not provided by the selected dataset; no substitute source was mixed in.",
        "- **DSC:** not provided by the selected dataset; no substitute source was mixed in.",
        "",
        "## Analyzer warnings retained",
        "",
        *warning_lines,
        "",
        "## Scientific claim closeout",
        "",
        "- **Strongest evidence:** original file identifiers and checksums, documented acquisition "
        "metadata, explicit source-to-canonical mappings, and successful real-data execution.",
        "- **Primary limitation:** the common DWCNT label does not prove that every technique measured "
        "the identical physical aliquot; sample preparation and measurement volumes differ by technique.",
        "- **TEM limitation:** the selected image contains intertwined nanotubes on holey support. The "
        "current global threshold-region method would confuse support holes and bundles, so no size "
        "distribution was generated.",
        "- **Evidence that would change the conclusion:** aliquot-level sample tracking, complete raw "
        "acquisition metadata, validated technique-specific preprocessing, replicate/uncertainty analysis, "
        "and reference-material or benchmark agreement.",
        "- **Suitable use:** software integration validation, provenance demonstration, and exploratory "
        "within-technique comparison.",
        "- **Not suitable for:** phase confirmation, chemical-state assignment, functional-group proof, "
        "reaction/mechanism claims, or engineering release decisions without independent validation.",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def run_case(config_path: Path, discovery_dir: Path, output_dir: Path) -> dict[str, Any]:
    config = load_json(config_path)
    downloads = load_json(discovery_dir / "downloads.json")
    missing = [name for name in REQUIRED_DOWNLOADS if (downloads.get(name) or {}).get("status") != "downloaded"]
    if missing:
        raise ValueError(f"Public case is missing required downloaded sources: {', '.join(missing)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    canonical_dir = output_dir / "canonical"
    analysis_root = output_dir / "analyses"
    sample_id = config["primary_sample"]["sample_id"]

    raw = {name: _downloaded_source(downloads, name, discovery_dir) for name in REQUIRED_DOWNLOADS}
    adapters = {
        "raman": adapt_two_column_source(
            raw["raman"], canonical_dir / "raman_dwcnt.csv", x_name="raman_shift_cm_1", y_name="intensity"
        ),
        "ftir": adapt_two_column_source(
            raw["ftir"], canonical_dir / "ftir_dwcnt.csv", x_name="wavenumber_cm_1", y_name="signal"
        ),
        "xps": adapt_two_column_source(
            raw["xps"], canonical_dir / "xps_dwcnt.csv", x_name="binding_energy_ev", y_name="intensity"
        ),
        "tga": adapt_tga_air_source(raw["tga"], canonical_dir / "tga_air_dwcnt.csv"),
    }

    parameters = config["processing_parameters"]
    metadata = config["acquisition_metadata"]
    analyses: dict[str, dict[str, object]] = {}
    analyses["raman"] = analyze_raman(
        adapters["raman"]["canonical_path"],
        analysis_root / "raman",
        sample_id=sample_id,
        measurement_id=f"{sample_id}-raman-public",
        acquisition_metadata=metadata["raman"],
        **parameters["raman"],
    )
    analyses["ftir"] = analyze_ftir(
        adapters["ftir"]["canonical_path"],
        analysis_root / "ftir",
        sample_id=sample_id,
        measurement_id=f"{sample_id}-ftir-public",
        acquisition_metadata=metadata["ftir"],
        **parameters["ftir"],
    )
    xps_parameters = dict(parameters["xps"])
    xps_parameters.pop("energy_reference", None)
    analyses["xps"] = analyze_xps(
        adapters["xps"]["canonical_path"],
        analysis_root / "xps",
        sample_id=sample_id,
        measurement_id=f"{sample_id}-xps-public",
        acquisition_metadata=metadata["xps"],
        **xps_parameters,
    )
    analyses["tga"] = analyze_thermal(
        adapters["tga"]["canonical_path"],
        analysis_root / "tga",
        sample_id=sample_id,
        measurement_id=f"{sample_id}-tga-air-public",
        mode="tga",
        acquisition_metadata=metadata["tga"],
        **parameters["tga"],
    )

    results: list[AnalysisResult] = []
    for modality in EXECUTED_MODALITIES:
        results.append(
            _rebind_result_to_original_source(
                analyses[modality], raw_source=raw[modality], adapter_record=adapters[modality]
            )
        )

    tem_record = inspect_tem_source(
        raw["tem"],
        metadata=metadata["tem"],
        gate=config["suitability_gates"]["tem_quantitative_segmentation"],
        output_path=analysis_root / "tem" / "tem_readiness.json",
    )
    execution = {name: "executed_real_data" for name in EXECUTED_MODALITIES}
    execution.update({"tem": "blocked_by_suitability_gate", "saed": "not_available", "dsc": "not_available"})
    comparability_path = output_dir / "comparability_matrix.csv"
    comparability = build_comparability_matrix(config, execution, comparability_path)

    source_manifest = {
        "case_id": config["case_id"],
        "dataset": config["dataset"],
        "primary_sample": config["primary_sample"],
        "downloads": downloads,
        "adapters": adapters,
        "tem_readiness": tem_record,
        "readme_source": {
            "source_file": str(raw["readme"]),
            "source_sha256": sha256_file(raw["readme"]),
            "purpose": "acquisition metadata source; values were manually transcribed into case_config.json",
        },
    }
    source_manifest_path = output_dir / "case_source_manifest.json"
    source_manifest_path.write_text(
        json.dumps(source_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    analysis_manifest_path = write_analysis_manifest(results, output_dir / "case_analysis_manifest.json")
    report_path = output_dir / "case_validation_report.md"
    write_case_report(
        report_path,
        config=config,
        source_manifest_path=source_manifest_path,
        comparability_path=comparability_path,
        analyses=analyses,
        tem_record=tem_record,
    )
    summary = {
        "case_id": config["case_id"],
        "evidence_level": "Diagnostic",
        "executed_modalities": list(EXECUTED_MODALITIES),
        "blocked_modalities": ["tem"],
        "unavailable_modalities": ["saed", "dsc"],
        "analysis_manifest": str(analysis_manifest_path),
        "source_manifest": str(source_manifest_path),
        "comparability_matrix": str(comparability_path),
        "report": str(report_path),
        "comparability_status_counts": comparability["comparability_status"].value_counts().to_dict(),
    }
    (output_dir / "case_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
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
    except Exception as exc:  # noqa: BLE001 - top-level CLI must report actionable context.
        print(f"public carbon case failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
