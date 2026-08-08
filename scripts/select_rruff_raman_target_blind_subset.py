from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RruffTargetBlindSelectionError(RuntimeError):
    """Raised when the target-blind RRUFF selection contract is violated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RruffTargetBlindSelectionError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise RruffTargetBlindSelectionError(f"invalid JSON: {resolved}") from exc
    if not isinstance(payload, dict):
        raise RruffTargetBlindSelectionError(f"JSON root must be an object: {resolved}")
    return payload


def _resolve_repo_path(value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise RruffTargetBlindSelectionError("repository path must be a non-empty string")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise RruffTargetBlindSelectionError("configured repository path is unsafe")
    resolved = (PROJECT_ROOT / candidate).resolve(strict=True)
    if PROJECT_ROOT not in resolved.parents:
        raise RruffTargetBlindSelectionError("repository path resolved outside project root")
    return resolved


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_contract(config: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "selection_id",
        "predeclared_at",
        "source_inventory",
        "eligible_id_field",
        "expected_eligible_id_count",
        "selection_size",
        "ranking",
        "authorized_selection_inputs",
        "authorized_operations",
        "decision_rules",
    }
    if set(config) != required or config.get("schema_version") != "1.0":
        raise RruffTargetBlindSelectionError("selection contract keys/schema mismatch")
    if config.get("selection_id") != "rruff-raman-target-blind-subset-v1":
        raise RruffTargetBlindSelectionError("selection identity drifted")
    source_path = _resolve_repo_path(config.get("source_inventory"))
    if source_path.name != "verified_annotation_inventory_snapshot.json":
        raise RruffTargetBlindSelectionError("source inventory path drifted")
    if config.get("eligible_id_field") != "annotation_inventory.rruff_ids":
        raise RruffTargetBlindSelectionError("eligible ID field drifted")
    if config.get("expected_eligible_id_count") != 55 or config.get("selection_size") != 10:
        raise RruffTargetBlindSelectionError("eligible count or selection size drifted")

    ranking = config.get("ranking")
    expected_ranking = {
        "algorithm": "sha256_ascending_hex",
        "seed": "mca-rruff-peak-localization-v1",
        "message_format": "{seed}:{rruff_id}",
        "tie_breaker": "rruff_id_ascending",
        "replacement_rule": "If a selected ID fails later source-readiness criteria, use the next unused ID in this same frozen ranking. Never replace based on analyzer performance.",
    }
    if ranking != expected_ranking:
        raise RruffTargetBlindSelectionError("ranking contract drifted")

    inputs = config.get("authorized_selection_inputs")
    if not isinstance(inputs, dict) or inputs.get("rruff_id_strings_only") is not True:
        raise RruffTargetBlindSelectionError("RRUFF ID input authorization is invalid")
    if any(value is not False for key, value in inputs.items() if key != "rruff_id_strings_only"):
        raise RruffTargetBlindSelectionError("selection contract authorizes non-ID inputs")

    operations = config.get("authorized_operations")
    allowed_true = {
        "read_pinned_rruff_id_list",
        "compute_deterministic_hash_ranking",
        "emit_full_ranking_and_selected_ids",
    }
    if not isinstance(operations, dict):
        raise RruffTargetBlindSelectionError("authorized_operations must be an object")
    if any(operations.get(key) is not True for key in allowed_true):
        raise RruffTargetBlindSelectionError("required deterministic selection operation is disabled")
    if any(value is not False for key, value in operations.items() if key not in allowed_true):
        raise RruffTargetBlindSelectionError("spectrum/analyzer/scoring operations must remain disabled")

    rules = config.get("decision_rules")
    if not isinstance(rules, dict) or not rules or any(value is not True for value in rules.values()):
        raise RruffTargetBlindSelectionError("all target-blind decision rules must be enabled")
    return config


def _load_eligible_ids(config: Mapping[str, Any]) -> tuple[Path, list[str]]:
    source_path = _resolve_repo_path(config["source_inventory"])
    source = _load_json(source_path)
    inventory = source.get("annotation_inventory")
    readiness = source.get("readiness")
    evidence = source.get("evidence_assessment")
    if not isinstance(inventory, Mapping):
        raise RruffTargetBlindSelectionError("source annotation inventory is missing")
    if not isinstance(readiness, Mapping) or readiness.get("annotation_inventory_ready") is not True:
        raise RruffTargetBlindSelectionError("source annotation inventory is not ready")
    if readiness.get("raman_analyzer_execution_authorized") is not False:
        raise RruffTargetBlindSelectionError("source unexpectedly authorizes Raman execution")
    if not isinstance(evidence, Mapping) or evidence.get("published_peak_annotation_inventory") != "Diagnostic":
        raise RruffTargetBlindSelectionError("source annotation evidence boundary drifted")

    ids = inventory.get("rruff_ids")
    if not isinstance(ids, list) or any(not isinstance(item, str) or not item for item in ids):
        raise RruffTargetBlindSelectionError("source RRUFF ID list is invalid")
    if len(ids) != config["expected_eligible_id_count"]:
        raise RruffTargetBlindSelectionError("eligible RRUFF ID count drifted")
    if len(set(ids)) != len(ids):
        raise RruffTargetBlindSelectionError("eligible RRUFF IDs are not unique")
    if ids != sorted(ids):
        raise RruffTargetBlindSelectionError("pinned RRUFF ID list is not canonical ascending order")
    return source_path, list(ids)


def _rank_ids(ids: list[str], seed: str) -> list[dict[str, Any]]:
    ranked: list[tuple[str, str]] = []
    for rruff_id in ids:
        message = f"{seed}:{rruff_id}".encode("utf-8")
        ranked.append((hashlib.sha256(message).hexdigest(), rruff_id))
    ranked.sort(key=lambda item: (item[0], item[1]))
    hashes = [digest for digest, _ in ranked]
    if len(hashes) != len(set(hashes)):
        raise RruffTargetBlindSelectionError("SHA-256 ranking collision detected")
    return [
        {
            "rank": index,
            "rruff_id": rruff_id,
            "sha256_rank_key": digest,
        }
        for index, (digest, rruff_id) in enumerate(ranked, start=1)
    ]


def run_selection(*, config_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = _validate_contract(_load_json(config_resolved))
    source_path, ids = _load_eligible_ids(config)
    ranking = _rank_ids(ids, str(config["ranking"]["seed"]))
    selection_size = int(config["selection_size"])
    selected = ranking[:selection_size]
    replacements = ranking[selection_size:]

    result = {
        "schema_version": "1.0",
        "selection_id": config["selection_id"],
        "execution_status": "target_blind_rruff_subset_selected",
        "contract_sha256": _sha256_file(config_resolved),
        "source_inventory": {
            "path": str(source_path.relative_to(PROJECT_ROOT)),
            "sha256": _sha256_file(source_path),
            "eligible_id_count": len(ids),
        },
        "ranking_method": config["ranking"],
        "selection_size": selection_size,
        "selected_ids": [row["rruff_id"] for row in selected],
        "selected_records": selected,
        "replacement_order": [row["rruff_id"] for row in replacements],
        "full_ranking": ranking,
        "selection_inputs_used": ["rruff_id"],
        "selection_inputs_not_used": sorted(
            key
            for key, allowed in config["authorized_selection_inputs"].items()
            if allowed is False
        ),
        "readiness": {
            "target_blind_subset_frozen": True,
            "source_spectrum_download_authorized": False,
            "source_metadata_inspection_authorized": False,
            "raman_analyzer_execution_authorized": False,
            "parameter_or_tolerance_tuning_authorized": False,
            "validation_scoring_authorized": False,
            "external_validation_ready": False,
        },
        "next_evidence": {
            "requirement": "audit_exact_source_spectrum_availability_and_acquisition_metadata_for_selected_ids_in_frozen_rank_order",
            "replacement_rule": config["ranking"]["replacement_rule"],
        },
        "scientific_boundary": [
            "Selection used only the exact pinned RRUFF ID strings and the public fixed SHA-256 seed.",
            "Peak annotations, noise, formula, mineral type, crystal system, Materials Project IDs, computed modes, source spectra, MCA outputs, and manual preference were not selection inputs.",
            "This selection establishes no source availability, analyzer performance, external-validation, mineral-identification, or engineering evidence."
        ],
    }

    output = Path(output_path).expanduser().resolve(strict=False)
    if output.exists():
        raise RruffTargetBlindSelectionError(f"refusing to overwrite output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Select a deterministic target-blind RRUFF Raman subset from pinned IDs only."
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = run_selection(config_path=args.config, output_path=args.output)
    except (RruffTargetBlindSelectionError, FileNotFoundError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
