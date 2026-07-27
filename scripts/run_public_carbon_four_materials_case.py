"""Run a four-sample public carbon characterization and handoff case.

The workflow selects exact Dataverse datafile IDs for DWCNT, MWCNT, FLG, and
GNP, executes the existing Raman, FTIR, XPS, TGA, and TEM-readiness contracts
for each sample, then writes one multi-sample cross-repository handoff bundle.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from . import discover_public_carbon_multimodal as discover
    from . import execute_public_carbon_multimodal_case as execute
except ImportError:  # Direct ``python scripts/...py`` execution.
    import discover_public_carbon_multimodal as discover
    import execute_public_carbon_multimodal_case as execute

from mca.handoff_bundle import write_characterization_handoff_bundle
from mca.provenance import sha256_file

DEFAULT_CONFIG = Path("case_studies/public_carbon_four_materials/case_config.json")
EXECUTED_MODALITIES = ("raman", "ftir", "xps", "tga")
REQUIRED_SAMPLE_FILES = (*EXECUTED_MODALITIES, "tem")
PRODUCER_REPOSITORY = "jhin0410-lgtm/materials-characterization-analyzer"
EXPECTED_SAMPLE_IDENTITIES = {
    "public-dwcnt": "DWCNT",
    "public-mwcnt": "MWCNT",
    "public-flg": "FLG",
    "public-gnp": "GNP",
}
_SAFE_SAMPLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")

_BASE_INSPECT_TEM_SOURCE = execute.case.inspect_tem_source


def load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}.")
    return payload


def _validated_sample_id(value: object, *, label: str) -> str:
    sample_id = str(value or "").strip()
    if (
        not sample_id
        or sample_id in {".", ".."}
        or _SAFE_SAMPLE_ID.fullmatch(sample_id) is None
    ):
        raise ValueError(
            f"{label} sample_id must be a path-safe identifier containing only "
            "letters, digits, '.', '_', and '-'."
        )
    return sample_id


def _require_unique_samples(config: dict[str, Any]) -> list[dict[str, Any]]:
    samples = config.get("samples")
    if not isinstance(samples, list) or len(samples) != len(EXPECTED_SAMPLE_IDENTITIES):
        raise ValueError(
            "Four-material case config requires exactly four samples: "
            "DWCNT, MWCNT, FLG, and GNP."
        )

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_labels: set[str] = set()
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise ValueError(f"samples[{index}] must be a JSON object.")
        sample_id = _validated_sample_id(sample.get("sample_id"), label=f"samples[{index}]")
        source_label = str(sample.get("source_label") or "").strip()
        if not source_label:
            raise ValueError(f"samples[{index}] requires source_label.")
        if sample_id in seen_ids:
            raise ValueError(f"Duplicate sample_id in four-material config: {sample_id}")
        if source_label in seen_labels:
            raise ValueError(f"Duplicate source_label in four-material config: {source_label}")
        seen_ids.add(sample_id)
        seen_labels.add(source_label)

        expected_label = EXPECTED_SAMPLE_IDENTITIES.get(sample_id)
        if expected_label != source_label:
            raise ValueError(
                "Four-material sample identities must match the fixed contract; "
                f"{sample_id!r} expected {expected_label!r}, found {source_label!r}."
            )

        files = sample.get("files")
        if not isinstance(files, dict) or set(files) != set(REQUIRED_SAMPLE_FILES):
            raise ValueError(
                f"{sample_id} files must contain exactly {list(REQUIRED_SAMPLE_FILES)}."
            )
        normalized.append(sample)

    actual_pairs = {
        (str(sample["sample_id"]), str(sample["source_label"])) for sample in normalized
    }
    expected_pairs = set(EXPECTED_SAMPLE_IDENTITIES.items())
    if actual_pairs != expected_pairs:
        raise ValueError(
            "Four-material case requires exactly the configured DWCNT, MWCNT, FLG, "
            "and GNP sample identities."
        )
    return normalized


def _metadata_version(payload: dict[str, Any]) -> str:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Dataverse metadata is missing the data object.")
    version = data.get("latestVersion") or data.get("draftVersion")
    if not isinstance(version, dict):
        raise ValueError("Dataverse metadata is missing a dataset version object.")

    major = version.get("versionNumber")
    minor = version.get("versionMinorNumber")
    if isinstance(major, int) and isinstance(minor, int):
        return f"{major}.{minor}"

    label = version.get("version")
    if isinstance(label, str) and label.strip():
        return label.strip()
    raise ValueError("Dataverse metadata does not expose a usable dataset version.")


def _verify_dataset_version(payload: dict[str, Any], configured_version: object) -> str:
    expected = str(configured_version or "").strip()
    if not expected:
        raise ValueError("Configured dataset version must be non-empty.")
    actual = _metadata_version(payload)
    if actual != expected:
        raise ValueError(
            f"Dataverse dataset version mismatch: configured {expected!r}, "
            f"metadata returned {actual!r}."
        )
    return actual


def select_exact_record(
    inventory: list[dict[str, Any]], specification: dict[str, Any], *, label: str
) -> dict[str, Any]:
    """Resolve one exact public source by immutable datafile ID and filename."""
    datafile_id = specification.get("datafile_id")
    expected_filename = specification.get("expected_filename")
    if not isinstance(datafile_id, int):
        raise ValueError(f"{label} datafile_id must be an integer.")
    if not isinstance(expected_filename, str) or not expected_filename.strip():
        raise ValueError(f"{label} expected_filename must be a non-empty string.")
    matches = [record for record in inventory if record.get("datafile_id") == datafile_id]
    if len(matches) != 1:
        raise ValueError(
            f"{label} expected exactly one inventory record for datafile_id={datafile_id}; "
            f"found {len(matches)}."
        )
    record = matches[0]
    if record.get("filename") != expected_filename:
        raise ValueError(
            f"{label} filename mismatch for datafile_id={datafile_id}: "
            f"expected {expected_filename!r}, found {record.get('filename')!r}."
        )
    if record.get("restricted"):
        raise ValueError(f"{label} exact source is restricted and cannot be downloaded.")
    return record


def _download_exact_source(
    record: dict[str, Any], destination: Path, *, cache: dict[int, bytes]
) -> dict[str, Any]:
    datafile_id = record.get("datafile_id")
    if not isinstance(datafile_id, int):
        raise ValueError("Exact source record is missing integer datafile_id.")
    payload = cache.get(datafile_id)
    if payload is None:
        payload = discover._request_bytes(discover.datafile_download_url(datafile_id))
        cache[datafile_id] = payload

    checksum = discover.verify_source_checksum(payload, record)
    checksum_supplied = bool(record.get("checksum_type") or record.get("checksum_value"))
    if checksum_supplied and checksum.get("source_checksum_verified") is not True:
        raise ValueError(
            "Source checksum was supplied but could not be verified for "
            f"datafile_id={datafile_id}; type={record.get('checksum_type')!r}."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return {
        "status": "downloaded",
        "local_path": str(destination),
        "source_path": record.get("path"),
        "source_persistent_id": record.get("persistent_id"),
        "datafile_id": datafile_id,
        "download_url": discover.datafile_download_url(datafile_id),
        "downloaded_sha256": discover.sha256_bytes(payload),
        "exact_selection": True,
        "expected_filename": record.get("filename"),
        **checksum,
        **discover.preview_bytes(payload, record),
    }


def build_sample_config(
    config: dict[str, Any], sample: dict[str, Any]
) -> dict[str, Any]:
    """Build one existing single-sample case config without inventing metadata."""
    sample_id = _validated_sample_id(sample["sample_id"], label="sample")
    source_label = str(sample["source_label"])
    common_metadata = copy.deepcopy(config["common_acquisition_metadata"])
    common_metadata["tga"].update(copy.deepcopy(sample["tga_mass_metadata"]))
    common_metadata["tem"].update(
        {"accelerating_voltage_kv": float(sample["tem_accelerating_voltage_kv"])}
    )

    extension_map = {
        "raman": [".csv", ".tab", ".txt", ".tsv"],
        "ftir": [".csv", ".tab", ".txt", ".tsv"],
        "xps": [".csv", ".tab", ".txt", ".tsv"],
        "tga": [".csv", ".tab", ".txt", ".tsv"],
        "tem": [".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp"],
    }
    modalities: dict[str, dict[str, Any]] = {}
    for modality in REQUIRED_SAMPLE_FILES:
        specification = sample["files"][modality]
        modalities[modality] = {
            "datafile_id": specification["datafile_id"],
            "expected_filename": specification["expected_filename"],
            "required_tokens": [],
            "preferred_tokens": [],
            "excluded_tokens": [],
            "extensions": extension_map[modality],
        }
    readme = config["readme_file"]
    modalities["readme"] = {
        "datafile_id": readme["datafile_id"],
        "expected_filename": readme["expected_filename"],
        "required_tokens": [],
        "preferred_tokens": [],
        "excluded_tokens": [],
        "extensions": [".pdf"],
    }

    tem_reason = (
        "The current global bright/dark threshold-region analyzer is not validated "
        f"to segment {sample['material_class']} from the holey support, overlap, "
        "aggregation, folds, edges, or background in this public image."
    )
    return {
        "case_id": f"{config['case_id']}--{sample_id}",
        "dataset": copy.deepcopy(config["dataset"]),
        "primary_sample": {
            "sample_id": sample_id,
            "source_label": source_label,
            "material_class": sample["material_class"],
            "source_description": sample["source_description"],
        },
        "comparison_samples": [entry["source_label"] for entry in config["samples"]],
        "modalities": modalities,
        "acquisition_metadata": common_metadata,
        "processing_parameters": copy.deepcopy(config["processing_parameters"]),
        "suitability_gates": {
            "tem_quantitative_segmentation": {
                "allowed": False,
                "status": "blocked_method_mismatch",
                "reason": tem_reason,
                "allowed_output": (
                    "source identity, checksum, image dimensions, dtype, and acquisition "
                    "metadata only"
                ),
            }
        },
        "availability_contract": copy.deepcopy(config["availability_contract"]),
        "scientific_guardrails": copy.deepcopy(config["scientific_guardrails"]),
    }


def _safe_sample_root(output_dir: Path, sample_id: str) -> Path:
    root = output_dir.resolve()
    candidate = (output_dir / "samples" / sample_id).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"Sample output path escapes the output directory: {sample_id!r}.")
    return candidate


def prepare_sample_discovery(
    config: dict[str, Any],
    sample: dict[str, Any],
    inventory: list[dict[str, Any]],
    output_dir: Path,
    *,
    cache: dict[int, bytes],
) -> tuple[Path, Path]:
    """Write exact-selection discovery evidence compatible with the existing runner."""
    sample_id = _validated_sample_id(sample["sample_id"], label="sample")
    sample_root = _safe_sample_root(output_dir, sample_id)
    discovery_dir = sample_root / "discovery"
    config_path = sample_root / "resolved_case_config.json"
    discovery_dir.mkdir(parents=True, exist_ok=True)
    sample_config = build_sample_config(config, sample)
    config_path.write_text(
        json.dumps(sample_config, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    selected: dict[str, dict[str, Any]] = {}
    downloads: dict[str, dict[str, Any]] = {}
    specifications = {**sample["files"], "readme": config["readme_file"]}
    for modality, specification in specifications.items():
        label = f"{sample_id}/{modality}"
        record = select_exact_record(inventory, specification, label=label)
        selected[modality] = record
        destination = discovery_dir / "raw" / discover.safe_filename(
            modality, str(record["filename"])
        )
        downloads[modality] = _download_exact_source(record, destination, cache=cache)

    (discovery_dir / "selected_files.json").write_text(
        json.dumps(selected, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (discovery_dir / "downloads.json").write_text(
        json.dumps(downloads, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        f"# Exact Public Source Selection - {sample_id}",
        "",
        f"- Dataset: `{config['dataset']['persistent_id']}`",
        f"- Dataset version: `{config['dataset']['version']}`",
        f"- Source label: `{sample['source_label']}`",
        "- Selection policy: exact configured Dataverse datafile ID and filename.",
        "",
        "| Modality | Datafile ID | Filename | Source checksum verified |",
        "|---|---:|---|---|",
    ]
    for modality in (*REQUIRED_SAMPLE_FILES, "readme"):
        record = selected[modality]
        download = downloads[modality]
        lines.append(
            f"| {modality} | {record['datafile_id']} | `{record['filename']}` | "
            f"{download.get('source_checksum_verified')} |"
        )
    lines.extend(
        [
            "",
            "This stage proves deterministic source acquisition only. It does not establish "
            "identical aliquots, scientific comparability, phase identity, or mechanism.",
            "",
        ]
    )
    (discovery_dir / "discovery_report.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    return config_path, discovery_dir


def _material_case_report(
    output_path: Path,
    config: dict[str, Any],
    source_manifest_path: Path,
    comparability_path: Path,
    analyses: dict[str, dict[str, object]],
    tem_record: dict[str, Any],
) -> None:
    """Write a truthful sample-specific report for any configured carbon material."""
    summaries = {
        "raman": execute.case.candidate_summary(
            analyses["raman"], "raman_shift_cm_1", "cm^-1"
        ),
        "ftir": execute.case.candidate_summary(
            analyses["ftir"], "wavenumber_cm_1", "cm^-1"
        ),
        "xps": execute.case.candidate_summary(
            analyses["xps"], "binding_energy_corrected_ev", "eV"
        ),
        "tga": execute.case.candidate_summary(
            analyses["tga"], "temperature_c", "degC"
        ),
    }
    warning_lines = [
        f"- **{name.upper()}**: "
        + (", ".join(analysis["analysis_result"].warnings) or "no software quality warnings")
        for name, analysis in analyses.items()
    ]
    sample = config["primary_sample"]
    gate = config["suitability_gates"]["tem_quantitative_segmentation"]
    lines = [
        f"# Public {sample['source_label']} Multimodal Validation Report",
        "",
        "## Result",
        "",
        "**Evidence level: Diagnostic.** This single-sample execution demonstrates "
        "public-file acquisition, checksum-backed provenance, adapter traceability, "
        "and real-data execution of the Raman, FTIR, XPS, and TGA software contracts. "
        "It does not establish a material mechanism or formal cross-technique "
        "scientific validation.",
        "",
        "## Source",
        "",
        f"- Dataset: {config['dataset']['title']}",
        f"- Persistent ID: `{config['dataset']['persistent_id']}`",
        f"- Version: `{config['dataset']['version']}`",
        f"- License: `{config['dataset']['license']}`",
        f"- Source sample label: `{sample['source_label']}`",
        f"- Material class: `{sample['material_class']}`",
        f"- Source description: {sample['source_description']}",
        f"- Source manifest: `{source_manifest_path}`",
        f"- Comparability matrix: `{comparability_path}`",
        "",
        "## Real-data execution",
        "",
        f"- **Raman:** {summaries['raman']}",
        f"- **FTIR:** {summaries['ftir']}",
        f"- **XPS:** {summaries['xps']}",
        f"- **TGA-air:** {summaries['tga']}",
        f"- **TEM:** decoded as `{tem_record['image_shape']}` / "
        f"`{tem_record['image_dtype']}`, but quantitative segmentation was blocked.",
        "- **SAED:** not provided; no substitute source was mixed in.",
        "- **DSC:** not provided; no substitute source was mixed in.",
        "",
        "## Analyzer warnings retained",
        "",
        *warning_lines,
        "",
        "## Scientific claim closeout",
        "",
        "- **Strongest evidence:** exact public file identity and checksums, documented "
        "acquisition metadata, explicit source-to-canonical mappings, and successful "
        "real-data software execution.",
        f"- **Primary limitation:** the common `{sample['source_label']}` source label "
        "does not prove identical physical aliquots across techniques; preparation "
        "and measurement volumes differ.",
        f"- **TEM limitation:** {gate['reason']}",
        "- **Evidence that would change the conclusion:** aliquot-level tracking, full "
        "acquisition metadata, validated technique-specific preprocessing, replicate "
        "uncertainty, and benchmark or reference-material agreement.",
        "- **Suitable use:** software integration validation, provenance demonstration, "
        "and exploratory within-technique comparison.",
        "- **Not suitable for:** phase confirmation, chemical-state assignment, "
        "functional-group proof, reaction or mechanism claims, predictive "
        "generalization, or engineering release decisions.",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _material_tem_inspection(
    source_path: Path,
    metadata: dict[str, Any],
    gate: dict[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    record = _BASE_INSPECT_TEM_SOURCE(source_path, metadata, gate, output_path)
    record["scientific_limitation"] = str(gate.get("reason") or "")
    output_path.write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return record


def _aggregate_case(
    config: dict[str, Any], output_dir: Path, sample_records: list[dict[str, Any]]
) -> dict[str, Path]:
    analyses: list[dict[str, Any]] = []
    source_manifests: dict[str, Any] = {}
    comparability_frames: list[pd.DataFrame] = []
    for record in sample_records:
        sample_id = record["sample_id"]
        result_dir = Path(record["result_dir"])
        analysis_manifest = load_json(result_dir / "case_analysis_manifest.json")
        sample_analyses = analysis_manifest.get("analyses")
        if not isinstance(sample_analyses, list) or len(sample_analyses) != 4:
            raise ValueError(f"{sample_id} must contain four executed analyses.")
        analyses.extend(sample_analyses)
        source_manifests[sample_id] = load_json(
            result_dir / "case_source_manifest.json"
        )
        matrix = pd.read_csv(result_dir / "comparability_matrix.csv")
        matrix.insert(0, "sample_id", sample_id)
        matrix.insert(1, "source_label", record["source_label"])
        matrix.insert(2, "material_class", record["material_class"])
        comparability_frames.append(matrix)

    analysis_path = output_dir / "case_analysis_manifest.json"
    analysis_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "analysis_count": len(analyses),
                "analyses": analyses,
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    source_path = output_dir / "case_source_manifest.json"
    source_path.write_text(
        json.dumps(
            {
                "case_id": config["case_id"],
                "dataset": config["dataset"],
                "selection_policy": {
                    "mode": "exact_datafile_id_and_filename",
                    "fallback_selection_allowed": False,
                    "source_checksum_verification_required_when_available": True,
                    "dataset_version_must_match_config": True,
                },
                "samples": source_manifests,
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    comparability_path = output_dir / "comparability_matrix.csv"
    pd.concat(comparability_frames, ignore_index=True).to_csv(
        comparability_path, index=False
    )

    context_rows = [
        {
            "sample_id": sample["sample_id"],
            "source_label": sample["source_label"],
            "material_class": sample["material_class"],
            "source_description": sample["source_description"],
            "dataset_persistent_id": config["dataset"]["persistent_id"],
            "dataset_version": config["dataset"]["version"],
            "identical_physical_aliquot_confirmed": False,
            "controlled_process_variable_confirmed": False,
            "process_response_model_allowed": False,
        }
        for sample in config["samples"]
    ]
    bundle_paths = write_characterization_handoff_bundle(
        output_dir,
        case_id=config["case_id"],
        sample_context_rows=context_rows,
        source_manifest_path=source_path,
        analysis_manifest_path=analysis_path,
        comparability_matrix_path=comparability_path,
        producer_repository=PRODUCER_REPOSITORY,
        evidence_level="Diagnostic",
        scientific_boundary={
            "result": "four_public_material_classes_exported_with_exact_source_binding",
            "strongest_evidence": (
                "Four explicit sample IDs, sixteen real-data instrument analyses, exact "
                "Dataverse file IDs and filenames, verified supplied checksums, a verified "
                "dataset version, and one versioned bundle."
            ),
            "primary_limitation": (
                "The samples are different material classes with different synthesis or "
                "procurement histories, not controlled levels of one process variable."
            ),
            "suitable_for": [
                "multi-sample cross-repository contract validation",
                "provenance-preserving descriptive feature transfer",
                "software testing of sample_id joins across four records",
            ],
            "unsuitable_for": [
                "process-response modeling or optimization",
                "causal or mechanistic attribution",
                "phase, chemical-state, or functional-group confirmation",
                "predictive generalization or engineering release decisions",
            ],
        },
    )
    return {
        "analysis_manifest": analysis_path,
        "source_manifest": source_path,
        "comparability_matrix": comparability_path,
        **bundle_paths,
    }


def _write_report(
    config: dict[str, Any], output_dir: Path, summary: dict[str, Any]
) -> Path:
    report_path = output_dir / "case_validation_report.md"
    sample_lines = "\n".join(
        f"- `{sample['sample_id']}`: {sample['source_label']} - {sample['material_class']}"
        for sample in config["samples"]
    )
    report = f"""# Public Carbon Four-Material Multimodal Case

## Result

**Evidence level: Diagnostic.** The workflow successfully transferred real Raman,
FTIR, XPS, and TGA features for four explicit public sample classes through one
versioned handoff bundle.

## Samples

{sample_lines}

## Software and Provenance Evidence

- Exact configured Dataverse datafile IDs and filenames were required.
- Dataset version `{summary['dataset_version_verified']}` was verified against metadata.
- Supplied repository checksums had to be supported and verify successfully.
- Sample count: `{summary['sample_count']}`.
- Executed measurement count: `{summary['measurement_count']}`.
- Feature record count: `{summary['feature_record_count']}`.
- Instruments: `{', '.join(summary['instruments'])}`.
- Every sample retained a unique, path-safe `sample_id` across the bundle boundary.
- TEM source files were checksum-verified for readiness; quantitative segmentation remained blocked.
- No row-order join, model training, optimization, or scientific metric recomputation occurred.

## Scientific Claim Closeout

- **Strongest evidence:** exact public file bindings, supported source checksums, verified dataset version, documented acquisition metadata, sixteen real-data analyses, and one four-sample bundle.
- **Primary limitation:** DWCNT, MWCNT, FLG, and GNP are different material classes with different synthesis or procurement histories. They are not controlled process levels.
- **Supported use:** software interoperability, provenance transfer, and descriptive within-technique review.
- **Unsupported use:** process-response relationships, causal or mechanistic interpretation, phase or chemical-state confirmation, prediction, optimization, or engineering release decisions.
- **Evidence needed for process science:** multiple explicitly traceable specimens produced under controlled and comparable process conditions, replicate measurements, compatible outcomes, and uncertainty estimates.
"""
    report_path.write_text(report, encoding="utf-8")
    return report_path


def run_case(config_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    config = load_json(config_path)
    samples = _require_unique_samples(config)
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(
            f"Output directory is not empty; existing files were preserved: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)

    metadata_payload = discover._request_json(
        discover.dataset_metadata_url(config["dataset"]["persistent_id"])
    )
    dataset_version = _verify_dataset_version(
        metadata_payload, config["dataset"]["version"]
    )
    inventory = discover.flatten_inventory(metadata_payload)
    if not inventory:
        raise RuntimeError("Dataverse metadata contained no files.")
    inventory_path = output / "source_inventory.json"
    inventory_path.write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    cache: dict[int, bytes] = {}
    sample_records: list[dict[str, Any]] = []
    for sample in samples:
        sample_config_path, discovery_dir = prepare_sample_discovery(
            config, sample, inventory, output, cache=cache
        )
        sample_id = _validated_sample_id(sample["sample_id"], label="sample")
        result_dir = _safe_sample_root(output, sample_id) / "result"

        previous_report_writer = execute.case.write_case_report
        previous_tem_inspector = execute.case.inspect_tem_source
        execute.case.write_case_report = _material_case_report
        execute.case.inspect_tem_source = _material_tem_inspection
        try:
            result = execute.case.run_case(
                sample_config_path, discovery_dir, result_dir
            )
        finally:
            execute.case.write_case_report = previous_report_writer
            execute.case.inspect_tem_source = previous_tem_inspector

        result["tga_case_candidate_review"] = execute.review_tga_case_candidates(
            result_dir
        )
        sample_records.append(
            {
                "sample_id": sample_id,
                "source_label": sample["source_label"],
                "material_class": sample["material_class"],
                "result_dir": str(result_dir),
                "result": result,
            }
        )

    outputs = _aggregate_case(config, output, sample_records)
    bundle = load_json(outputs["manifest"])
    feature_record = bundle["feature_table"]
    summary = {
        "case_id": config["case_id"],
        "status": "completed",
        "evidence_level": "Diagnostic",
        "dataset_persistent_id": config["dataset"]["persistent_id"],
        "dataset_version_verified": dataset_version,
        "sample_count": feature_record["sample_count"],
        "measurement_count": feature_record["measurement_count"],
        "feature_record_count": feature_record["row_count"],
        "instruments": feature_record["instruments"],
        "sample_ids": sorted(sample["sample_id"] for sample in samples),
        "exact_source_binding": True,
        "fallback_source_selection_used": False,
        "source_inventory_sha256": sha256_file(inventory_path),
        "tga_mass_metadata_semantics": {
            "sample_mass_mg": "W_sa starting mass before dry-air purge",
            "dry_air_purge_mass_change_mg": "W_sp mass change after dry-air purge",
            "helium_purge_starting_sample_mass_mg": (
                "W_sm starting mass for separate TGA-MS experiment"
            ),
            "empty_crucible_mass_inferred": False,
            "sample_plus_crucible_mass_inferred": False,
        },
        "software_validation": {
            "real_data_analyses_executed": True,
            "dataset_version_verified": True,
            "path_safe_sample_ids_validated": True,
            "supplied_source_checksums_verified": True,
            "sample_specific_reports_generated": True,
            "sample_id_join_contract_ready": True,
            "row_order_join_used": False,
            "model_trained": False,
            "optimization_performed": False,
            "scientific_metrics_recomputed_after_analysis": False,
        },
        "scientific_closeout": bundle["scientific_closeout"],
    }
    summary_path = output / "case_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path = _write_report(config, output, summary)
    summary["outputs"] = {
        **{name: str(path) for name, path in outputs.items()},
        "summary": str(summary_path),
        "report": str(report_path),
        "source_inventory": str(inventory_path),
    }
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = run_case(args.config, args.output)
    except Exception as exc:  # noqa: BLE001 - CLI boundary reports actionable context.
        print(f"public carbon four-material case failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
