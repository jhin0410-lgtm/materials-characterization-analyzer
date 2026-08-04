from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from mca.saed_external_validation_intake import (
    PROTOCOL_READY,
    load_intake_manifest,
    run_saed_external_validation_intake,
)
SUPPORT_PATH = Path(__file__).with_name("saed_transfer_test_case.py")
SUPPORT_SPEC = importlib.util.spec_from_file_location("saed_transfer_test_case", SUPPORT_PATH)
assert SUPPORT_SPEC is not None and SUPPORT_SPEC.loader is not None
support = importlib.util.module_from_spec(SUPPORT_SPEC)
SUPPORT_SPEC.loader.exec_module(support)

module = support.module
_sha = support._sha
_write_json = support._write_json
_source_tree = support._source_tree
_response_bundle = support._response_bundle
_verification = support._verification
_case = support._case


def test_private_transfer_requires_explicit_intake_mapping(tmp_path: Path) -> None:
    source, candidate = _source_tree(tmp_path)
    candidate["source_type"] = "private_transfer"
    response = _response_bundle(tmp_path, candidate)
    verification = _verification(tmp_path, source, response, candidate)
    payload = json.loads(verification.read_text(encoding="utf-8"))
    payload["dataset_verification"]["intake_source_type"] = "private_acquisition"
    payload["dataset_verification"][
        "source_type_mapping_basis"
    ] = "Private transfer contains a privately acquired source dataset"
    _write_json(verification, payload)

    summary = module.verify_transfer(
        response, verification, source, tmp_path / "output"
    )

    assert summary["status"] == module.READY
    intake = json.loads(
        (tmp_path / "output" / "saed_external_validation_intake_draft.json").read_text(
            encoding="utf-8"
        )
    )
    assert intake["dataset"]["source_type"] == "private_acquisition"


def test_reference_identifier_must_be_declared(tmp_path: Path) -> None:
    source, response, verification, _ = _case(tmp_path)
    payload = json.loads(verification.read_text(encoding="utf-8"))
    payload["reference_verification"]["intake_reference_identifier"] = (
        "COD:NOT-DECLARED"
    )
    _write_json(verification, payload)

    with pytest.raises(
        module.SAEDTransferVerificationError,
        match="must be one of the declared references",
    ):
        module.verify_transfer(
            response, verification, source, tmp_path / "output"
        )


def test_nonempty_output_is_not_overwritten(tmp_path: Path) -> None:
    source, response, verification, _ = _case(tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    (output / "existing.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="absent or an empty directory"):
        module.verify_transfer(response, verification, source, output)



def test_unauthorized_extra_file_is_rejected(tmp_path: Path) -> None:
    source, response, verification, _ = _case(tmp_path)
    (source / "unexpected.bin").write_bytes(b"not authorized")

    with pytest.raises(
        module.SAEDTransferVerificationError,
        match="unauthorized file",
    ):
        module.verify_transfer(
            response, verification, source, tmp_path / "output"
        )

def test_generated_draft_runs_existing_saed_intake_fail_closed(tmp_path: Path) -> None:
    source, response, verification, _ = _case(tmp_path)
    bridge_output = tmp_path / "bridge-output"
    bridge_summary = module.verify_transfer(
        response, verification, source, bridge_output
    )
    assert bridge_summary["status"] == module.READY

    intake_manifest = load_intake_manifest(
        bridge_output / "saed_external_validation_intake_draft.json"
    )
    intake_summary = run_saed_external_validation_intake(
        intake_manifest, source, tmp_path / "intake-output"
    )

    assert intake_summary["decision"]["status"] == PROTOCOL_READY
    assert intake_summary["decision"]["saed_protocol_freeze_ready"] is True
    assert intake_summary["decision"][
        "predeclared_saed_external_evaluation_ready"
    ] is False
    assert intake_summary["decision"][
        "crystallographic_performance_claim_ready"
    ] is False
    assert intake_summary["decision"]["engineering_release_ready"] is False
