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
from .handoff_validation.validator import EVIDENCE_IDENTITY_BINDING_CONTRACT_VERSION

LEGACY_CONFIG_SCHEMA_VERSION = "1.0"
LADDER_CONFIG_SCHEMA_VERSION = "1.1"
CONFIG_SCHEMA_VERSION = LEGACY_CONFIG_SCHEMA_VERSION
SUPPORTED_CONFIG_SCHEMA_VERSIONS = (
    LEGACY_CONFIG_SCHEMA_VERSION,
    LADDER_CONFIG_SCHEMA_VERSION,
)
BUILD_STATUS = "characterization_handoff_bundle_built_and_validated"
_REQUIRED_EVIDENCE = {"source_manifest", "analysis_manifest", "comparability_matrix"}
_LEGACY_CONFIG_FIELDS = {
    "schema_version",
    "case_id",
    "producer_repository",
    "evidence_level",
    "sample_context_rows",
    "scientific_boundary",
    "evidence",
    "downstream_use_policy",
}
_LADDER_CONFIG_FIELDS = _LEGACY_CONFIG_FIELDS | {"scientific_evidence_ladder"}
_RESERVED_OUTPUT_NAMES = {FEATURE_FILE_NAME, SAMPLE_CONTEXT_FILE_NAME, MANIFEST_FILE_NAME}


class HandoffBundleBuildError(ValueError):
    """Raised when a generic handoff build contract fails closed."""


def _enable_evidence_identity_binding(stage: Path, manifest_path: Path) -> None:
    manifest = _load_json(manifest_path, "generated handoff manifest")
    if "evidence_identity_binding_contract" in manifest:
        raise HandoffBundleBuildError(
            "generated handoff manifest unexpectedly contains evidence_identity_binding_contract"
        )
    manifest["evidence_identity_binding_contract"] = {
        "schema_version": EVIDENCE_IDENTITY_BINDING_CONTRACT_VERSION,
        "required": True,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if manifest_path.parent.resolve() != stage.resolve():
        raise HandoffBundleBuildError("generated handoff manifest escaped staging directory")


def _validate_config_schema(config: Mapping[str, Any]) -> str:
    schema_version = config.get("schema_version")
    if not isinstance(schema_version, str) or schema_version not in SUPPORTED_CONFIG_SCHEMA_VERSIONS:
        raise HandoffBundleBuildError("unsupported handoff build config schema_version")
    ladder_present = "scientific_evidence_ladder" in config
    if schema_version == LEGACY_CONFIG_SCHEMA_VERSION:
        _only(config, _LEGACY_CONFIG_FIELDS, "handoff build config")
        if ladder_present:
            raise HandoffBundleBuildError(
                "scientific_evidence_ladder requires handoff build config schema_version 1.1"
            )
    else:
        _only(config, _LADDER_CONFIG_FIELDS, "handoff build config")
        if not ladder_present:
            raise HandoffBundleBuildError(
                "handoff build config schema_version 1.1 requires scientific_evidence_ladder"
            )
    return schema_version


def build_characterization_handoff_bundle_from_config(
    config_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    config_file = Path(config_path)
    config = _load_json(config_file, "handoff build config")
    config_schema_version = _validate_config_schema(config)
    case_id = _text(config, "case_id")
    producer_repository = _text(config, "producer_repository")
    evidence_level = _text(config, "evidence_level")
    rows = config.get("sample_context_rows")
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        raise HandoffBundleBuildError("sample_context_rows must be a non-empty list of objects")
    scientific_boundary = config.get("scientific_boundary")
    if not isinstance(scientific_boundary, dict):
        raise HandoffBundleBuildError("scientific_boundary must be an object")
    downstream_use_policy = config.get("downstream_use_policy")
    if downstream_use_policy is not None and not isinstance(downstream_use_policy, dict):
        raise HandoffBundleBuildError("downstream_use_policy must be an object when provided")
    evidence = config.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != _REQUIRED_EVIDENCE:
        raise HandoffBundleBuildError(
            "evidence must contain source_manifest, analysis_manifest, and comparability_matrix"
        )

    base = config_file.resolve().parent
    resolved = {label: _resolve_input(base, value, label) for label, value in evidence.items()}
    ladder_value = config.get("scientific_evidence_ladder")
    ladder_source = (
        None
        if ladder_value is None
        else _resolve_input(base, ladder_value, "scientific_evidence_ladder")
    )
    if config_schema_version == LADDER_CONFIG_SCHEMA_VERSION and ladder_source is None:
        raise HandoffBundleBuildError(
            "handoff build config schema_version 1.1 requires a scientific_evidence_ladder file"
        )
    all_inputs = [*resolved.values(), *([ladder_source] if ladder_source is not None else [])]
    basenames = [path.name for path in all_inputs]
    if len(basenames) != len(set(basenames)):
        raise HandoffBundleBuildError("handoff input basenames must be unique")
    collision = sorted(set(basenames) & _RESERVED_OUTPUT_NAMES)
    if collision:
        raise HandoffBundleBuildError(f"input filename conflicts with bundle artifact: {collision[0]}")

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
        copied_ladder: Path | None = None
        if ladder_source is not None:
            copied_ladder = stage / ladder_source.name
            shutil.copyfile(ladder_source, copied_ladder)

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
            downstream_use_policy=(
                dict(downstream_use_policy)
                if downstream_use_policy is not None
                else None
            ),
            scientific_evidence_ladder_assessment_path=copied_ladder,
        )
        _enable_evidence_identity_binding(stage, paths["manifest"])
        validation = validate_characterization_handoff_bundle(stage)
        stage.replace(output)
        result = {
            "status": BUILD_STATUS,
            "config_schema_version": config_schema_version,
            "output": str(output),
            "feature_table": str(output / paths["feature_table"].name),
            "sample_context": str(output / paths["sample_context"].name),
            "manifest": str(output / paths["manifest"].name),
            "validation": validation,
        }
        if copied_ladder is not None:
            result["scientific_evidence_ladder_assessment"] = str(
                output / copied_ladder.name
            )
        return result
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
