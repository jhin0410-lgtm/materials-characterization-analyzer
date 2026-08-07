from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Bir300CalibrationReadinessError(RuntimeError):
    """Raised when the pinned calibration-readiness evidence contract is violated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise Bir300CalibrationReadinessError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise Bir300CalibrationReadinessError(f"invalid JSON: {resolved}") from exc
    if not isinstance(value, dict):
        raise Bir300CalibrationReadinessError("JSON root must be an object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_repo_path(relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise Bir300CalibrationReadinessError("configured evidence path is unsafe")
    return (PROJECT_ROOT / path).resolve(strict=True)


def validate_contract(contract: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "case_id",
        "assessment_date",
        "dataset",
        "authoritative_method_source",
        "verified_header_facts",
        "calibration_requirements",
        "current_evidence_state",
        "decision_rules",
        "next_evidence_requirement",
        "scientific_boundary",
    }
    if set(contract) != expected or contract.get("schema_version") != "1.0":
        raise Bir300CalibrationReadinessError("evidence contract keys/schema do not match")
    dataset = contract["dataset"]
    if not isinstance(dataset, dict) or dataset.get("record_id") != 10995139:
        raise Bir300CalibrationReadinessError("dataset identity is not pinned BIR 300 keV")
    method = contract["authoritative_method_source"]
    if not isinstance(method, dict) or method.get("doi") != "10.1107/S2052252524012132":
        raise Bir300CalibrationReadinessError("published method source identity drifted")
    rules = contract["decision_rules"]
    if not isinstance(rules, dict) or any(value is not True for value in rules.values()):
        raise Bir300CalibrationReadinessError("all fail-closed decision rules must remain enabled")
    state = contract["current_evidence_state"]
    if state.get("quantitative_saed_indexing_readiness") != "Unsupported":
        raise Bir300CalibrationReadinessError("quantitative SAED readiness must remain fail-closed")
    if state.get("pattern_center") != "Inconclusive" or state.get("reciprocal_scale") != "Inconclusive":
        raise Bir300CalibrationReadinessError("unresolved calibration evidence was prematurely promoted")
    next_requirement = contract["next_evidence_requirement"]
    if next_requirement.get("source_bytes_required_now") is not False:
        raise Bir300CalibrationReadinessError("additional source bytes must not be required by this contract")
    return contract


def _validate_metadata_snapshot(contract: Mapping[str, Any], snapshot: Mapping[str, Any]) -> None:
    if snapshot.get("execution_status") != "metadata_audit_completed":
        raise Bir300CalibrationReadinessError("metadata snapshot is not completed")
    source = snapshot.get("source")
    if not isinstance(source, Mapping):
        raise Bir300CalibrationReadinessError("metadata source record is invalid")
    dataset = contract["dataset"]
    if source.get("record_id") != dataset["record_id"] or source.get("doi") != dataset["doi"]:
        raise Bir300CalibrationReadinessError("metadata dataset identity drifted")
    if source.get("license_id") != "cc-by-4.0":
        raise Bir300CalibrationReadinessError("dataset reuse terms drifted")


def _validate_remote_snapshot(snapshot: Mapping[str, Any]) -> None:
    if snapshot.get("execution_status") != "remote_central_directory_inventory_completed":
        raise Bir300CalibrationReadinessError("remote inventory snapshot is not completed")
    evidence = snapshot.get("evidence_assessment")
    readiness = snapshot.get("readiness")
    if not isinstance(evidence, Mapping) or not isinstance(readiness, Mapping):
        raise Bir300CalibrationReadinessError("remote inventory evidence is invalid")
    if evidence.get("tvips_member_presence") != "Supported":
        raise Bir300CalibrationReadinessError("TVIPS member presence is no longer supported")
    if evidence.get("hyperspy_split_stream_filename_compatibility") != "Unsupported":
        raise Bir300CalibrationReadinessError("source-native filename compatibility state drifted")
    if readiness.get("external_validation_ready") is not False:
        raise Bir300CalibrationReadinessError("remote inventory prematurely authorizes external validation")


def _validate_header_snapshot(contract: Mapping[str, Any], snapshot: Mapping[str, Any]) -> None:
    if snapshot.get("execution_status") != "selected_tvips_header_prefix_audit_completed":
        raise Bir300CalibrationReadinessError("header-prefix snapshot is not completed")
    evidence = snapshot.get("evidence_assessment")
    readiness = snapshot.get("readiness")
    general = snapshot.get("tvips_general_header")
    if not isinstance(evidence, Mapping) or not isinstance(readiness, Mapping) or not isinstance(general, Mapping):
        raise Bir300CalibrationReadinessError("header-prefix evidence is invalid")
    if evidence.get("tvips_general_header_structural_match") != "Supported":
        raise Bir300CalibrationReadinessError("TVIPS internal header structure is no longer supported")
    if readiness.get("phase_indexing_authorized") is not False:
        raise Bir300CalibrationReadinessError("header evidence prematurely authorizes phase indexing")
    fields = general.get("fields")
    if not isinstance(fields, Mapping):
        raise Bir300CalibrationReadinessError("TVIPS parsed fields are missing")
    expected = contract["verified_header_facts"]
    observed = {
        "size": fields.get("size"),
        "version": fields.get("version"),
        "dimx": fields.get("dimx"),
        "dimy": fields.get("dimy"),
        "bitsperpixel": fields.get("bitsperpixel"),
        "binx": fields.get("binx"),
        "biny": fields.get("biny"),
        "offsetx": fields.get("offsetx"),
        "offsety": fields.get("offsety"),
        "pixelsize_raw": fields.get("pixelsize"),
        "ht_raw": fields.get("ht"),
        "magtotal_raw": fields.get("magtotal"),
        "frameheaderbytes": fields.get("frameheaderbytes"),
    }
    if observed != expected:
        raise Bir300CalibrationReadinessError("verified TVIPS header facts drifted")


def assess(*, contract_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    contract_resolved = Path(contract_path).expanduser().resolve(strict=True)
    contract = validate_contract(load_json(contract_resolved))
    dataset = contract["dataset"]
    metadata_path = resolve_repo_path(str(dataset["verified_metadata_snapshot"]))
    remote_path = resolve_repo_path(str(dataset["verified_remote_inventory_snapshot"]))
    header_path = resolve_repo_path(str(dataset["verified_header_prefix_snapshot"]))
    metadata = load_json(metadata_path)
    remote_snapshot = load_json(remote_path)
    header_snapshot = load_json(header_path)
    _validate_metadata_snapshot(contract, metadata)
    _validate_remote_snapshot(remote_snapshot)
    _validate_header_snapshot(contract, header_snapshot)

    state = contract["current_evidence_state"]
    blockers = [
        key
        for key in ("pattern_center", "reciprocal_scale", "sample_acquisition_lineage", "reference_truth")
        if state.get(key) != "Supported"
    ]
    result = {
        "schema_version": "1.0",
        "case_id": contract["case_id"],
        "assessment_date": contract["assessment_date"],
        "execution_status": "calibration_readiness_assessed",
        "evidence_bindings": {
            "contract_sha256": sha256_file(contract_resolved),
            "metadata_snapshot_sha256": sha256_file(metadata_path),
            "remote_inventory_snapshot_sha256": sha256_file(remote_path),
            "header_prefix_snapshot_sha256": sha256_file(header_path),
            "method_source_doi": contract["authoritative_method_source"]["doi"],
        },
        "supported_context": {
            "dataset_record_and_reuse_terms": True,
            "archive_and_tvips_member_identity": True,
            "tvips_internal_header_structure": True,
            "published_300kv_microscope_detector_diffraction_mode": True,
        },
        "blocking_evidence": blockers,
        "quantitative_saed_indexing_ready": False,
        "external_validation_ready": False,
        "engineering_decision_ready": False,
        "scientific_evidence_level": "Diagnostic",
        "next_evidence_requirement": contract["next_evidence_requirement"],
        "source_bytes_required_now": False,
        "scientific_closeout": (
            "The BIR 300 keV source is now format- and method-context credible, but quantitative "
            "SAED indexing remains blocked by unresolved pattern-centre and reciprocal-calibration "
            "evidence, with acquisition lineage and reference truth also unresolved. Additional "
            "diffraction bytes are not the current bottleneck."
        ),
        "scientific_boundary": contract["scientific_boundary"],
    }
    output = Path(output_path).expanduser().resolve(strict=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assess BIR 300 keV quantitative-SAED calibration readiness without reading new source bytes."
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("case_studies/zenodo_bir_300kev_saed_calibration_readiness/evidence_contract.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = assess(contract_path=args.contract, output_path=args.output)
    except (OSError, ValueError, Bir300CalibrationReadinessError) as exc:
        print(f"BIR 300 keV calibration-readiness assessment failed: {exc}")
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
