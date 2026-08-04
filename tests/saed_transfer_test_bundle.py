from __future__ import annotations

import importlib.util
from pathlib import Path

DATA_PATH = Path(__file__).with_name("saed_transfer_test_data.py")
DATA_SPEC = importlib.util.spec_from_file_location("saed_transfer_test_data", DATA_PATH)
assert DATA_SPEC is not None and DATA_SPEC.loader is not None
data = importlib.util.module_from_spec(DATA_SPEC)
DATA_SPEC.loader.exec_module(data)

module = data.module
_sha = data._sha
_write_json = data._write_json

def _response_bundle(tmp_path: Path, candidate: dict[str, object]) -> Path:
    root = tmp_path / "response"
    root.mkdir()
    normalized = {
        "schema_version": "1.0",
        "request_case_id": module.SOURCE_REQUEST_CASE_ID,
        "response_status": "candidate_available",
        "respondent": {
            "name": "Repository Curator",
            "affiliation": "Microscopy Repository",
            "email": "curator@example.org",
            "authority": "repository_curator",
            "authority_basis": "Repository record custodian",
        },
        "candidate": candidate,
        "referrals": [],
        "notes": "The two acquisitions are independently collected.",
    }
    assessment = {
        "schema_version": "1.0",
        "case_id": module.SOURCE_REQUEST_CASE_ID,
        "status": module.SOURCE_RESPONSE_READY,
        "response_contract_valid": True,
        "response_status": "candidate_available",
        "evidence_gates": {"all": True},
        "source_blockers": [],
        "source_download_authorized": False,
        "ready_for_bounded_source_verification": True,
        "saed_validation_intake_ready": False,
        "external_evaluation_ready": False,
        "saed_analyzer_execution_authorized": False,
        "phase_or_reflection_indexing_authorized": False,
    }
    patterns = candidate["patterns"]
    assert isinstance(patterns, list)
    plan = {
        "schema_version": "1.0",
        "case_id": module.SOURCE_REQUEST_CASE_ID,
        "status": module.SOURCE_PLAN_READY,
        "dataset_id": candidate["dataset_id"],
        "dataset_version": candidate["dataset_version"],
        "collection_manifest_sha256": candidate["collection_manifest_sha256"],
        "declared_patterns": [
            {
                key: item[key]
                for key in (
                    "pattern_id",
                    "relative_path",
                    "bytes",
                    "sha256",
                    "sample_id",
                    "acquisition_id",
                )
            }
            for item in patterns
            if isinstance(item, dict)
        ],
        "source_download_authorized": False,
        "saed_validation_intake_ready": False,
        "external_evaluation_ready": False,
        "required_next_checks": ["verify bytes and SHA-256 independently"],
    }
    files = {
        "saed_independent_source_author_response_normalized.json": normalized,
        "saed_independent_source_response_assessment.json": assessment,
        "saed_bounded_source_verification_plan.json": plan,
    }
    for name, payload in files.items():
        _write_json(root / name, payload)
    (root / "saed_independent_source_response_assessment.md").write_text(
        "# Assessment\n", encoding="utf-8"
    )
    artifacts = []
    for name in [
        "saed_independent_source_author_response_normalized.json",
        "saed_independent_source_response_assessment.json",
        "saed_independent_source_response_assessment.md",
        "saed_bounded_source_verification_plan.json",
    ]:
        path = root / name
        artifacts.append(
            {"path": name, "bytes": path.stat().st_size, "sha256": _sha(path)}
        )
    _write_json(
        root / "saed_independent_source_response_manifest.json",
        {
            "schema_version": "1.0",
            "case_id": module.SOURCE_REQUEST_CASE_ID,
            "artifact_count": len(artifacts),
            "artifacts": artifacts,
        },
    )
    return root



__all__ = ["module", "_sha", "_write_json", "_response_bundle"]
