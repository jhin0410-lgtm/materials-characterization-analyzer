"""Run a provenance-first real-data DWCNT multimodal validation case."""

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
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_delimited_table(path: str | Path) -> tuple[pd.DataFrame, str]:
    source = Path(path)
    failures: list[str] = []
    for separator, label in ((";", "semicolon"), ("\t", "tab"), (",", "comma")):
        try:
            frame = pd.read_csv(source, sep=separator, engine="python")
        except Exception as exc:  # noqa: BLE001 - collect actionable adapter errors.
            failures.append(f"{label}: {exc}")
            continue
        if frame.shape[1] >= 2:
            return frame, label
    raise ValueError(
        f"Could not parse {source} with semicolon, tab, or comma delimiters: "
        + " | ".join(failures)
    )


def _numeric_column(frame: pd.DataFrame, index: int, label: str) -> pd.Series:
    if index >= frame.shape[1]:
        raise ValueError(f"Missing required {label} column index {index}.")
    original = frame.iloc[:, index]
    numeric = pd.to_numeric(original, errors="coerce")
    invalid = numeric.isna() & original.notna() & original.astype(str).str.strip().ne("")
    if invalid.any():
        raise ValueError(f"{label} contains non-numeric value {original.loc[invalid].iloc[0]!r}.")
    return numeric


def adapt_two_column_source(
    source_path: str | Path,
    destination: str | Path,
    *,
    x_name: str,
    y_name: str,
) -> dict[str, Any]:
    """Convert one two-column source table to canonical CSV without changing values."""
    source, destination = Path(source_path), Path(destination)
    frame, delimiter = _read_delimited_table(source)
    if frame.shape[1] != 2:
        raise ValueError(f"Expected exactly 2 columns in {source.name}; found {frame.shape[1]}.")
    x = _numeric_column(frame, 0, x_name)
    y = _numeric_column(frame, 1, y_name)
    valid = x.notna() & y.notna()
    canonical = pd.DataFrame({x_name: x[valid], y_name: y[valid]}).reset_index(drop=True)
    if len(canonical) < 7:
        raise ValueError(f"Canonical table for {source.name} contains fewer than 7 rows.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    canonical.to_csv(destination, index=False)
    return _adapter_record(
        source,
        destination,
        frame,
        canonical,
        delimiter,
        {str(frame.columns[0]): x_name, str(frame.columns[1]): y_name},
        "public_two_column_to_canonical_csv",
        int((~valid).sum()),
    )


def adapt_tga_air_source(source_path: str | Path, destination: str | Path) -> dict[str, Any]:
    """Map documented TGA-air columns 1, 2, and 6 to temperature/time/retention."""
    source, destination = Path(source_path), Path(destination)
    frame, delimiter = _read_delimited_table(source)
    if frame.shape[1] < 7:
        raise ValueError(f"Documented TGA-air table requires >=7 columns; found {frame.shape[1]}.")
    temperature = _numeric_column(frame, 0, "temperature")
    time_s = _numeric_column(frame, 1, "time")
    retention = _numeric_column(frame, 5, "mass retention percent")
    valid = temperature.notna() & time_s.notna() & retention.notna()
    canonical = pd.DataFrame(
        {
            "temperature_c": temperature[valid],
            "time_s": time_s[valid],
            "signal": retention[valid],
        }
    ).reset_index(drop=True)
    if len(canonical) < 7:
        raise ValueError("Canonical TGA table contains fewer than 7 rows.")
    if not np.all(np.diff(canonical["temperature_c"]) > 0):
        raise ValueError("Selected TGA source is not one strictly increasing heating segment.")
    if not np.all(np.diff(canonical["time_s"]) > 0):
        raise ValueError("Selected TGA source time is not strictly increasing.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    canonical.to_csv(destination, index=False)
    record = _adapter_record(
        source,
        destination,
        frame,
        canonical,
        delimiter,
        {
            str(frame.columns[0]): "temperature_c",
            str(frame.columns[1]): "time_s",
            str(frame.columns[5]): "signal_mass_retention_percent",
        },
        "documented_tga_air_seven_column_mapping",
        int((~valid).sum()),
    )
    record["mapping_basis"] = "Dataset_Raw/ReadMe_Raw.pdf seven-column TGA-air definition"
    return record


def _adapter_record(
    source: Path,
    destination: Path,
    source_frame: pd.DataFrame,
    canonical: pd.DataFrame,
    delimiter: str,
    mapping: dict[str, str],
    adapter: str,
    incomplete_rows: int,
) -> dict[str, Any]:
    return {
        "adapter": adapter,
        "source_path": str(source),
        "source_sha256": sha256_file(source),
        "canonical_path": str(destination),
        "canonical_sha256": sha256_file(destination),
        "source_delimiter": delimiter,
        "source_headers": [str(value) for value in source_frame.columns],
        "column_mapping": mapping,
        "source_row_count": int(len(source_frame)),
        "canonical_row_count": int(len(canonical)),
        "incomplete_rows_removed": incomplete_rows,
        "numeric_values_modified": False,
    }


def _downloaded_source(downloads: dict[str, Any], modality: str, discovery_dir: Path) -> Path:
    record = downloads.get(modality) or {}
    if record.get("status") != "downloaded":
        raise ValueError(f"Required modality {modality!r} was not downloaded: {record.get('status')}")
    stored = Path(str(record.get("local_path", "")))
    for candidate in (stored, discovery_dir / "raw" / stored.name):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Could not resolve downloaded {modality} file {stored}.")


def rebind_result_to_original_source(
    analysis: dict[str, object],
    raw_source: Path,
    adapter: dict[str, Any],
) -> AnalysisResult:
    """Attach original source provenance and adapter history to analyzer output."""
    result = analysis["analysis_result"]
    if not isinstance(result, AnalysisResult):
        raise TypeError("Analyzer did not return AnalysisResult.")
    step = PreprocessingStep(
        "public-source-adapter",
        str(adapter["adapter"]),
        {
            "source_sha256": adapter["source_sha256"],
            "canonical_sha256": adapter["canonical_sha256"],
            "source_delimiter": adapter.get("source_delimiter"),
            "column_mapping": adapter.get("column_mapping"),
            "incomplete_rows_removed": adapter.get("incomplete_rows_removed", 0),
            "numeric_values_modified": False,
        },
        notes="Case adapter only; analyzer algorithms were unchanged.",
    )
    steps = [step, *result.preprocessing_steps]
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
            "public_source_original_path": adapter["source_path"],
            "public_source_original_sha256": source_hash,
            "canonical_adapter_path": adapter["canonical_path"],
            "canonical_adapter_sha256": adapter["canonical_sha256"],
        }
    )
    feature_path = analysis.get("feature_path")
    if feature_path is not None:
        records_to_frame(features).to_csv(Path(feature_path), index=False)
    analysis["features"] = features
    return result


def inspect_tem_source(
    source_path: Path,
    metadata: dict[str, Any],
    gate: dict[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    image = cv2.imread(str(source_path), cv2.IMREAD_UNCHANGED)
    if image is None or image.ndim not in {2, 3}:
        raise ValueError(f"Could not decode supported TEM image {source_path}.")
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
            "The current Otsu region analyzer is not a nanotube tracing, bundle-width, "
            "or support-grid separation method; no TEM size distribution was generated."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return record


def build_comparability_matrix(
    config: dict[str, Any], execution: dict[str, str], output_path: str | Path
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for modality in ("raman", "ftir", "xps", "tga", "tem", "saed", "dsc"):
        if modality in EXECUTED_MODALITIES:
            status = "conditionally_comparable"
            use = "diagnostic within-technique review; cautious cross-technique context"
            limitation = "Identical physical aliquot is not established."
        elif modality == "tem":
            status = "source_available_analysis_blocked"
            use = "source and acquisition readiness only"
            limitation = config["suitability_gates"]["tem_quantitative_segmentation"]["reason"]
        else:
            status = "not_available_not_comparable"
            use = "none in this case"
            limitation = "Dataset does not provide this modality; no unrelated source was substituted."
        rows.append(
            {
                "modality": modality,
                "dataset_availability": config["availability_contract"].get(modality),
                "comparability_status": status,
                "source_sample_class": config["primary_sample"]["source_label"],
                "identical_physical_aliquot_confirmed": False,
                "analysis_execution": execution.get(modality, "not_executed"),
                "scientific_use": use,
                "primary_limitation": limitation,
            }
        )
    frame = pd.DataFrame(rows)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    return frame


def candidate_summary(analysis: dict[str, object], column: str, unit: str) -> str:
    table = analysis.get("candidate_table")
    if table is None:
        table = analysis.get("peak_table")
    if not isinstance(table, pd.DataFrame) or table.empty or column not in table:
        return "No automatic candidates were retained by the configured diagnostic threshold."
    values = pd.to_numeric(table[column], errors="coerce").dropna().tolist()
    shown = ", ".join(f"{value:.3g} {unit}" for value in values[:8])
    extra = "" if len(values) <= 8 else f"; {len(values) - 8} additional candidates omitted"
    return f"{len(values)} review-required candidates: {shown}{extra}."


def write_case_report(
    output_path: Path,
    config: dict[str, Any],
    source_manifest_path: Path,
    comparability_path: Path,
    analyses: dict[str, dict[str, object]],
    tem_record: dict[str, Any],
) -> None:
    summaries = {
        "raman": candidate_summary(analyses["raman"], "raman_shift_cm_1", "cm^-1"),
        "ftir": candidate_summary(analyses["ftir"], "wavenumber_cm_1", "cm^-1"),
        "xps": candidate_summary(analyses["xps"], "binding_energy_corrected_ev", "eV"),
        "tga": candidate_summary(analyses["tga"], "temperature_c", "degC"),
    }
    warning_lines = [
        f"- **{name.upper()}**: "
        + (", ".join(analysis["analysis_result"].warnings) or "no software quality warnings")
        for name, analysis in analyses.items()
    ]
    lines = [
        "# Public DWCNT Multimodal Validation Report",
        "",
        "## Result",
        "",
        "**Evidence level: Diagnostic.** The case demonstrates public-file acquisition, "
        "checksum-backed provenance, adapter traceability, and real-data execution of the "
        "Raman, FTIR, XPS, and TGA software contracts. It does not establish a material "
        "mechanism or formal cross-technique scientific validation.",
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
        f"- **Raman:** {summaries['raman']}",
        f"- **FTIR:** {summaries['ftir']}",
        f"- **XPS:** {summaries['xps']}",
        f"- **TGA-air:** {summaries['tga']}",
        f"- **TEM:** decoded as `{tem_record['image_shape']}` / `{tem_record['image_dtype']}`, "
        "but quantitative segmentation was blocked.",
        "- **SAED:** not provided; no substitute source was mixed in.",
        "- **DSC:** not provided; no substitute source was mixed in.",
        "",
        "## Analyzer warnings retained",
        "",
        *warning_lines,
        "",
        "## Scientific claim closeout",
        "",
        "- **Strongest evidence:** original file IDs/checksums, documented acquisition metadata, "
        "explicit source-to-canonical mappings, and successful real-data execution.",
        "- **Primary limitation:** a common DWCNT label does not prove identical physical aliquots; "
        "preparation and measurement volumes differ by technique.",
        "- **TEM limitation:** intertwined nanotubes and holey support invalidate the current global "
        "threshold-region measurement contract.",
        "- **Evidence that would change the conclusion:** aliquot-level tracking, full acquisition "
        "metadata, validated technique-specific preprocessing, replicate uncertainty, and benchmark "
        "or reference-material agreement.",
        "- **Suitable use:** software integration validation, provenance demonstration, and exploratory "
        "within-technique comparison.",
        "- **Not suitable for:** phase confirmation, chemical-state assignment, functional-group proof, "
        "reaction/mechanism claims, or engineering release decisions.",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def run_case(config_path: Path, discovery_dir: Path, output_dir: Path) -> dict[str, Any]:
    config, downloads = load_json(config_path), load_json(discovery_dir / "downloads.json")
    missing = [
        name
        for name in REQUIRED_DOWNLOADS
        if (downloads.get(name) or {}).get("status") != "downloaded"
    ]
    if missing:
        raise ValueError("Missing required public sources: " + ", ".join(missing))

    output_dir.mkdir(parents=True, exist_ok=True)
    canonical_dir, analysis_root = output_dir / "canonical", output_dir / "analyses"
    sample_id = config["primary_sample"]["sample_id"]
    raw = {
        name: _downloaded_source(downloads, name, discovery_dir)
        for name in REQUIRED_DOWNLOADS
    }
    adapters = {
        "raman": adapt_two_column_source(
            raw["raman"],
            canonical_dir / "raman_dwcnt.csv",
            x_name="raman_shift_cm_1",
            y_name="intensity",
        ),
        "ftir": adapt_two_column_source(
            raw["ftir"],
            canonical_dir / "ftir_dwcnt.csv",
            x_name="wavenumber_cm_1",
            y_name="signal",
        ),
        "xps": adapt_two_column_source(
            raw["xps"],
            canonical_dir / "xps_dwcnt.csv",
            x_name="binding_energy_ev",
            y_name="intensity",
        ),
        "tga": adapt_tga_air_source(raw["tga"], canonical_dir / "tga_air_dwcnt.csv"),
    }
    parameters, metadata = config["processing_parameters"], config["acquisition_metadata"]
    analyses: dict[str, dict[str, object]] = {
        "raman": analyze_raman(
            adapters["raman"]["canonical_path"],
            analysis_root / "raman",
            sample_id=sample_id,
            measurement_id=f"{sample_id}-raman-public",
            acquisition_metadata=metadata["raman"],
            **parameters["raman"],
        ),
        "ftir": analyze_ftir(
            adapters["ftir"]["canonical_path"],
            analysis_root / "ftir",
            sample_id=sample_id,
            measurement_id=f"{sample_id}-ftir-public",
            acquisition_metadata=metadata["ftir"],
            **parameters["ftir"],
        ),
    }
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
    results = [
        rebind_result_to_original_source(analyses[name], raw[name], adapters[name])
        for name in EXECUTED_MODALITIES
    ]
    tem_record = inspect_tem_source(
        raw["tem"],
        metadata["tem"],
        config["suitability_gates"]["tem_quantitative_segmentation"],
        analysis_root / "tem" / "tem_readiness.json",
    )
    execution = {name: "executed_real_data" for name in EXECUTED_MODALITIES}
    execution.update(
        {"tem": "blocked_by_suitability_gate", "saed": "not_available", "dsc": "not_available"}
    )
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
            "purpose": "Acquisition metadata source manually transcribed into case_config.json.",
        },
    }
    source_manifest_path = output_dir / "case_source_manifest.json"
    source_manifest_path.write_text(
        json.dumps(source_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    analysis_manifest_path = write_analysis_manifest(
        results, output_dir / "case_analysis_manifest.json"
    )
    report_path = output_dir / "case_validation_report.md"
    write_case_report(
        report_path,
        config,
        source_manifest_path,
        comparability_path,
        analyses,
        tem_record,
    )
    status_counts = {
        str(key): int(value)
        for key, value in comparability["comparability_status"].value_counts().items()
    }
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
        "comparability_status_counts": status_counts,
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
    except Exception as exc:  # noqa: BLE001 - CLI boundary reports actionable context.
        print(f"public carbon case failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
