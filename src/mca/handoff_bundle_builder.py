"""Config-driven, transactional producer for portable characterization handoff bundles."""
from __future__ import annotations

import json
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .handoff_bundle import (
    FEATURE_FILE_NAME,
    MANIFEST_FILE_NAME,
    SAMPLE_CONTEXT_FILE_NAME,
    write_characterization_handoff_bundle,
)
from .handoff_bundle_validation import validate_characterization_handoff_bundle

CONFIG_SCHEMA_VERSION = "1.0"
BUILD_STATUS = "characterization_handoff_bundle_built_and_validated"
_REQUIRED_EVIDENCE = {"source_manifest", "analysis_manifest", "comparability_matrix"}
_RESERVED_OUTPUT_NAMES = {FEATURE_FILE_NAME, SAMPLE_CONTEXT_FILE_NAME, MANIFEST_FILE_NAME}


class HandoffBundleBuildError(ValueError):
    """Raised when a generic handoff build contract fails closed."""


def build_characterization_handoff_bundle_from_config(
    config_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    config_file = Path(config_path)
    config = _load_json(config_file, "handoff build config")
    _only(
        config,
        {
            "schema_version",
            "case_id",
            "producer_repository",
            "evidence_level",
            "sample_context_rows",
            "scientific_boundary",
            "evidence",
        },
        "handoff build config",
    )
    if config.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise HandoffBundleBuildError("unsupported handoff build config schema_version")
    case_id = _text(config, "case_id")
    producer_repository = _text(config, "producer_repository")
    evidence_level = _text(config, "evidence_level")
    rows = config.get("sample_context_rows")
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        raise HandoffBundleBuildError("sample_context_rows must be a non-empty list of objects")
    scientific_boundary = config.get("scientific_boundary")
    if not isinstance(scientific_boundary, dict):
        raise HandoffBundleBuildError("scientific_boundary must be an object")
    evidence = config.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != _REQUIRED_EVIDENCE:
        raise HandoffBundleBuildError(
            "evidence must contain source_manifest, analysis_manifest, and comparability_matrix"
        )

    base = config_file.resolve().parent
    resolved = {label: _resolve_input(base, value, label) for label, value in evidence.items()}
    basenames = [path.name for path in resolved.values()]
    if len(basenames) != len(set(basenames)):
        raise HandoffBundleBuildError("evidence input basenames must be unique")
    collision = sorted(set(basenames) & _RESERVED_OUTPUT_NAMES)
    if collision:
        raise HandoffBundleBuildError(f"evidence filename conflicts with bundle artifact: {collision[0]}")

    output = Path(output_dir)
    if output.exists():
        raise FileExistsError("output must not already exist")
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    stage = parent / f".{output.name}.building"
    if stage.exists():
        raise FileExistsError(f"staging directory already exists: {stage}")
    stage.mkdir()

    try:
        copied: dict[str, Path] = {}
        for label, source in resolved.items():
            destination = stage / source.name
            shutil.copyfile(source, destination)
            copied[label] = destination

        paths = write_characterization_handoff_bundle(
            stage,
            case_id=case_id,
            sample_context_rows=[dict(row) for row in rows],
            source_manifest_path=copied["source_manifest"],
            analysis_manifest_path=copied["analysis_manifest"],
            comparability_matrix_path=copied["comparability_matrix"],
            producer_repository=producer_repository,
            evidence_level=evidence_level,
            scientific_boundary=dict(scientific_boundary),
        )
        validation = validate_characterization_handoff_bundle(stage)
        stage.replace(output)
        return {
            "status": BUILD_STATUS,
            "output": str(output),
            "feature_table": str(output / paths["feature_table"].name),
            "sample_context": str(output / paths["sample_context"].name),
            "manifest": str(output / paths["manifest"].name),
            "validation": validation,
        }
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _resolve_input(base: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise HandoffBundleBuildError(f"evidence.{label} must be a non-empty path string")
    pure = PurePosixPath(value.replace("\\", "/"))
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = base / Path(*pure.parts)
    if not candidate.is_file() or candidate.is_symlink():
        raise HandoffBundleBuildError(f"evidence.{label} must be a regular non-symlink file")
    return candidate.resolve()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise HandoffBundleBuildError(f"{label} must be a regular file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HandoffBundleBuildError(f"could not read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise HandoffBundleBuildError(f"{label} root must be an object")
    return payload


def _reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HandoffBundleBuildError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _only(payload: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise HandoffBundleBuildError(f"{label} contains unknown field: {unknown[0]}")


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HandoffBundleBuildError(f"{key} must be a non-empty string")
    return value.strip()
