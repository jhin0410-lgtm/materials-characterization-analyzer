"""Versioned readiness registry for all public characterization analyzers."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

REGISTRY_SCHEMA_VERSION = "1.0"
EXPECTED_ANALYZER_IDS = (
    "xrd",
    "sem",
    "eds",
    "raman",
    "xps",
    "ftir",
    "tga",
    "dsc",
    "tem",
    "saed",
)
SOFTWARE_STATUSES = {
    "baseline_workflow_supported",
    "baseline_and_validation_contracts_supported",
}
DIAGNOSTIC_USE_STATUSES = {
    "ready_with_review",
    "ready_only_after_method_suitability_review",
    "ready_for_software_and_diagnostic_use_only",
}
REAL_DATA_STATUSES = {
    "public_real_data_diagnostic_exercised",
    "public_real_data_method_suitability_exercised",
}
EVIDENCE_LEVELS = {"Supported", "Diagnostic", "Inconclusive", "Unsupported"}
OUTPUT_STATUS = "analyzer_readiness_registry_generated"
CSV_NAME = "analyzer_readiness.csv"
SUMMARY_NAME = "analyzer_readiness_summary.json"
REPORT_NAME = "analyzer_readiness_report.md"
MANIFEST_NAME = "analyzer_readiness_artifact_manifest.json"

_ROW_FIELDS = (
    "analyzer_id",
    "display_name",
    "software_readiness",
    "diagnostic_use_status",
    "real_data_evidence",
    "scientific_validation_status",
    "software_evidence_level",
    "scientific_evidence_level",
    "representative_cases",
    "supported_uses",
    "blocked_claims",
    "primary_limitation",
    "next_required_evidence",
    "independent_external_validation_ready",
    "engineering_decision_ready",
)


class AnalyzerReadinessError(ValueError):
    """Raised when the pinned readiness contract fails closed."""


def generate_analyzer_readiness_registry(
    config_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    config_file = Path(config_path)
    payload = _load_json_object(config_file)
    rows = _validate_registry(payload)

    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite analyzer-readiness output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = output.parent / f".{output.name}.building"
    if stage.exists():
        raise FileExistsError(f"Analyzer-readiness staging directory already exists: {stage}")
    stage.mkdir()
    try:
        csv_path = stage / CSV_NAME
        summary_path = stage / SUMMARY_NAME
        report_path = stage / REPORT_NAME

        _write_csv(rows, csv_path)
        summary = _build_summary(payload, rows)
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        report_path.write_text(_build_report(summary, rows), encoding="utf-8")

        artifact_records = []
        for artifact in (csv_path, summary_path, report_path):
            artifact_records.append(
                {
                    "path": artifact.name,
                    "size_bytes": artifact.stat().st_size,
                    "sha256": _sha256_file(artifact),
                }
            )
        manifest = {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "status": OUTPUT_STATUS,
            "source_config": {
                "path": config_file.name,
                "size_bytes": config_file.stat().st_size,
                "sha256": _sha256_file(config_file),
            },
            "artifacts": artifact_records,
            "scientific_boundary": {
                "software_validation_supported": True,
                "independent_external_validation_ready_count": 0,
                "engineering_decision_ready_count": 0,
                "missing_metadata_inferred": False,
                "scientific_claims_promoted": False,
            },
        }
        manifest_path = stage / MANIFEST_NAME
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        stage.replace(output)
        return {
            "status": OUTPUT_STATUS,
            "output": str(output),
            "analyzer_count": len(rows),
            "independent_external_validation_ready_count": 0,
            "engineering_decision_ready_count": 0,
            "csv": str(output / CSV_NAME),
            "summary": str(output / SUMMARY_NAME),
            "report": str(output / REPORT_NAME),
            "manifest": str(output / MANIFEST_NAME),
        }
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _validate_registry(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    _only(payload, {"schema_version", "snapshot_date", "scope", "analyzers"}, "registry")
    if payload.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise AnalyzerReadinessError("unsupported readiness-registry schema_version")
    _required_text(payload, "snapshot_date")
    scope = payload.get("scope")
    if not isinstance(scope, dict):
        raise AnalyzerReadinessError("scope must be an object")
    _only(
        scope,
        {
            "repository",
            "analyzer_ids",
            "software_validation_definition",
            "scientific_validation_definition",
            "registry_boundary",
        },
        "scope",
    )
    for key in (
        "repository",
        "software_validation_definition",
        "scientific_validation_definition",
        "registry_boundary",
    ):
        _required_text(scope, key)
    analyzer_ids = scope.get("analyzer_ids")
    if analyzer_ids != list(EXPECTED_ANALYZER_IDS):
        raise AnalyzerReadinessError(
            "scope.analyzer_ids must match the exact ordered public analyzer inventory"
        )

    analyzers = payload.get("analyzers")
    if not isinstance(analyzers, list) or len(analyzers) != len(EXPECTED_ANALYZER_IDS):
        raise AnalyzerReadinessError(
            f"analyzers must contain exactly {len(EXPECTED_ANALYZER_IDS)} entries"
        )

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(analyzers):
        if not isinstance(raw, dict):
            raise AnalyzerReadinessError(f"analyzers[{index}] must be an object")
        _only(raw, set(_ROW_FIELDS), f"analyzers[{index}]")
        row = dict(raw)
        analyzer_id = _required_text(row, "analyzer_id")
        if analyzer_id in seen:
            raise AnalyzerReadinessError(f"duplicate analyzer_id: {analyzer_id}")
        seen.add(analyzer_id)
        for key in (
            "display_name",
            "scientific_validation_status",
            "primary_limitation",
            "next_required_evidence",
        ):
            _required_text(row, key)
        if row.get("software_readiness") not in SOFTWARE_STATUSES:
            raise AnalyzerReadinessError(f"invalid software_readiness for {analyzer_id}")
        if row.get("diagnostic_use_status") not in DIAGNOSTIC_USE_STATUSES:
            raise AnalyzerReadinessError(f"invalid diagnostic_use_status for {analyzer_id}")
        if row.get("real_data_evidence") not in REAL_DATA_STATUSES:
            raise AnalyzerReadinessError(f"invalid real_data_evidence for {analyzer_id}")
        if row.get("software_evidence_level") != "Supported":
            raise AnalyzerReadinessError(
                f"software_evidence_level must be Supported for {analyzer_id}"
            )
        if row.get("scientific_evidence_level") not in EVIDENCE_LEVELS:
            raise AnalyzerReadinessError(
                f"invalid scientific_evidence_level for {analyzer_id}"
            )
        for key in ("representative_cases", "supported_uses", "blocked_claims"):
            value = row.get(key)
            if not isinstance(value, list) or not value:
                raise AnalyzerReadinessError(f"{key} must be a non-empty list for {analyzer_id}")
            if any(not isinstance(item, str) or not item.strip() for item in value):
                raise AnalyzerReadinessError(f"{key} contains a blank value for {analyzer_id}")
        for key in (
            "independent_external_validation_ready",
            "engineering_decision_ready",
        ):
            if row.get(key) is not False:
                raise AnalyzerReadinessError(
                    f"{key} must remain false in the current registry for {analyzer_id}"
                )
        rows.append(row)

    if tuple(row["analyzer_id"] for row in rows) != EXPECTED_ANALYZER_IDS:
        raise AnalyzerReadinessError(
            "analyzer rows must match the exact ordered public analyzer inventory"
        )
    return rows


def _build_summary(payload: Mapping[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    use_counts = Counter(str(row["diagnostic_use_status"]) for row in rows)
    scientific_counts = Counter(str(row["scientific_evidence_level"]) for row in rows)
    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "status": OUTPUT_STATUS,
        "snapshot_date": payload["snapshot_date"],
        "repository": payload["scope"]["repository"],
        "analyzer_count": len(rows),
        "software_supported_count": sum(
            row["software_evidence_level"] == "Supported" for row in rows
        ),
        "public_real_data_exercised_count": len(rows),
        "diagnostic_use_status_counts": dict(sorted(use_counts.items())),
        "scientific_evidence_level_counts": dict(sorted(scientific_counts.items())),
        "independent_external_validation_ready_count": sum(
            bool(row["independent_external_validation_ready"]) for row in rows
        ),
        "engineering_decision_ready_count": sum(
            bool(row["engineering_decision_ready"]) for row in rows
        ),
        "analyzers_requiring_new_external_evidence": [
            row["analyzer_id"] for row in rows
        ],
        "scientific_closeout": {
            "result": "software_baselines_supported_scientific_claims_remain_bounded",
            "evidence_level": "Diagnostic",
            "strongest_evidence": (
                "All ten packaged analyzer families have regression-tested baseline "
                "workflows and public real-data diagnostic execution or method-suitability evidence."
            ),
            "primary_limitation": (
                "No analyzer currently has the complete independent reference, replicate, "
                "calibration, uncertainty, sample-comparability, and frozen-protocol evidence "
                "needed for its strongest scientific or engineering claims."
            ),
            "suitable_for": [
                "software integration",
                "provenance-aware exploratory analysis",
                "diagnostic candidate generation with expert review",
                "evidence-gap and method-suitability assessment",
            ],
            "unsuitable_for": [
                "automatic material, phase, chemical-state, functional-group, reaction, or mechanism confirmation",
                "unqualified quantitative composition, morphology, enthalpy, or crystallographic performance claims",
                "causal attribution",
                "engineering release decisions",
            ],
        },
    }


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    csv_fields = (
        "analyzer_id",
        "display_name",
        "software_readiness",
        "diagnostic_use_status",
        "real_data_evidence",
        "scientific_validation_status",
        "software_evidence_level",
        "scientific_evidence_level",
        "representative_cases",
        "primary_limitation",
        "next_required_evidence",
        "independent_external_validation_ready",
        "engineering_decision_ready",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields)
        writer.writeheader()
        for row in rows:
            rendered = {key: row[key] for key in csv_fields}
            rendered["representative_cases"] = "|".join(row["representative_cases"])
            writer.writerow(rendered)


def _build_report(summary: Mapping[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Analyzer Readiness Registry",
        "",
        f"- Snapshot: `{summary['snapshot_date']}`",
        f"- Analyzers: `{summary['analyzer_count']}`",
        f"- Software-supported baselines: `{summary['software_supported_count']}`",
        f"- Independent external-validation ready: `{summary['independent_external_validation_ready_count']}`",
        f"- Engineering-decision ready: `{summary['engineering_decision_ready_count']}`",
        "",
        "Passing software tests does not establish scientific validity. Every automatic "
        "candidate remains bounded by the technique-specific limitations below.",
        "",
        "| Analyzer | Diagnostic use | Scientific evidence | Current scientific status |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['analyzer_id']}` | `{row['diagnostic_use_status']}` | "
            f"`{row['scientific_evidence_level']}` | "
            f"`{row['scientific_validation_status']}` |"
        )
    lines.extend(["", "## Technique-specific blockers", ""])
    for row in rows:
        lines.extend(
            [
                f"### {row['display_name']} (`{row['analyzer_id']}`)",
                "",
                f"- **Primary limitation:** {row['primary_limitation']}",
                f"- **Next required evidence:** {row['next_required_evidence']}",
                "- **Blocked claims:** " + "; ".join(row["blocked_claims"]) + ".",
                "",
            ]
        )
    closeout = summary["scientific_closeout"]
    lines.extend(
        [
            "## Scientific closeout",
            "",
            f"- **Result:** `{closeout['result']}`",
            f"- **Evidence level:** `{closeout['evidence_level']}`",
            f"- **Strongest evidence:** {closeout['strongest_evidence']}",
            f"- **Primary limitation:** {closeout['primary_limitation']}",
            "",
        ]
    )
    return "\n".join(lines)


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise AnalyzerReadinessError(f"readiness registry must be a regular file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AnalyzerReadinessError(f"could not read readiness registry: {path}") from exc
    if not isinstance(payload, dict):
        raise AnalyzerReadinessError("readiness registry root must be an object")
    return payload


def _reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AnalyzerReadinessError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _only(payload: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(payload) - allowed)
    missing = sorted(allowed - set(payload))
    if unknown:
        raise AnalyzerReadinessError(f"{label} contains unknown field: {unknown[0]}")
    if missing:
        raise AnalyzerReadinessError(f"{label} is missing field: {missing[0]}")


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AnalyzerReadinessError(f"{key} must be a non-empty string")
    return value.strip()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
