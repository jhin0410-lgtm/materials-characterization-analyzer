from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from mca.tem_mendeley_candidate_audit import (
    STATUS_API_BLOCKED,
    STATUS_TEM_CANDIDATE_FOUND,
    AuditConfig,
    run_mendeley_candidate_audit,
)


def _config() -> AuditConfig:
    return AuditConfig.from_mapping(
        {
            "case_id": "mendeley_cop_co2p_co3o4_tem_candidate_audit",
            "api_base": "https://api.data.mendeley.com",
            "datasets": [
                {
                    "dataset_id": "8w66synjmx",
                    "version": 1,
                    "doi": "10.17632/8w66synjmx.1",
                    "role": "primary_raw",
                    "expected_title_fragment": "Raw data-Three-dimensional",
                },
                {
                    "dataset_id": "zhnbzhjrtr",
                    "version": 1,
                    "doi": "10.17632/zhnbzhjrtr.1",
                    "role": "duplicate_raw_record",
                    "expected_title_fragment": "Three-dimensional",
                },
                {
                    "dataset_id": "jz9dpgwwc3",
                    "version": 1,
                    "doi": "10.17632/jz9dpgwwc3.1",
                    "role": "processed_control",
                    "expected_title_fragment": "processed data",
                },
            ],
        }
    )


def _transport(url: str, accept: str) -> tuple[int, Mapping[str, str], Any]:
    del accept
    dataset_id = next(
        item for item in ("8w66synjmx", "zhnbzhjrtr", "jz9dpgwwc3") if item in url
    )
    if "/files?" not in url:
        title = {
            "8w66synjmx": "Raw data-Three-dimensional nano-framework",
            "zhnbzhjrtr": "Three-dimensional nano-framework raw data",
            "jz9dpgwwc3": "processed data-Three-dimensional nano-framework",
        }[dataset_id]
        return 200, {"content-type": "application/json"}, {
            "id": dataset_id,
            "version": 1,
            "name": title,
            "description": "raw XRD, SEM, TEM and electrochemical data",
            "doi": {"id": f"10.17632/{dataset_id}.1"},
        }
    if dataset_id == "8w66synjmx":
        return 200, {}, [
            {
                "id": "11111111-1111-4111-8111-111111111111",
                "filename": "HRTEM_raw_images.zip",
                "description": "Transmission electron microscopy images",
                "content_details": {
                    "sha256_hash": "a" * 64,
                    "content_type": "application/zip",
                    "size": 12345,
                    "download_url": "https://temporary.example/file",
                },
                "status": "AVAILABLE",
            },
            {
                "id": "22222222-2222-4222-8222-222222222222",
                "filename": "XRD.xlsx",
                "description": "X-ray diffraction",
                "content_details": {
                    "sha256_hash": "b" * 64,
                    "content_type": "application/vnd.ms-excel",
                    "size": 456,
                },
                "status": "AVAILABLE",
            },
        ]
    return 200, {}, []


def test_resolves_checksum_bound_tem_candidate_without_opening_annotation_gate(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out"
    summary = run_mendeley_candidate_audit(
        _config(),
        output,
        transport=_transport,
    )
    assert summary["inventory_readiness"]["status"] == STATUS_TEM_CANDIDATE_FOUND
    assert summary["result_counts"]["primary_file_count"] == 2
    assert summary["result_counts"]["primary_tem_candidate_file_count"] == 1
    assert summary["inventory_readiness"]["primary_checksums_and_sizes_complete"]
    assert not summary["lineage_and_annotation_gates"]["annotation_pilot_ready"]
    assert not summary["lineage_and_annotation_gates"][
        "external_model_evaluation_ready"
    ]

    inventory = (output / "mendeley_file_inventory.csv").read_text(encoding="utf-8")
    assert "HRTEM_raw_images.zip" in inventory
    assert "aaaaaaaaaaaaaaaa" in inventory
    snapshots = json.loads(
        (output / "mendeley_api_snapshots.json").read_text(encoding="utf-8")
    )
    encoded = json.dumps(snapshots, sort_keys=True)
    assert "temporary.example" not in encoded
    assert "redacted_ephemeral_url" in encoded

    manifest = json.loads(
        (output / "mendeley_candidate_audit_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["artifact_count"] == 5
    for record in manifest["artifacts"]:
        artifact = output / record["path"]
        assert record["bytes"] == artifact.stat().st_size
        assert record["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()


def test_publics_endpoint_fallback_is_supported(tmp_path: Path) -> None:
    def fallback(url: str, accept: str) -> tuple[int, Mapping[str, str], Any]:
        if "/datasets/publics/" not in url:
            return 401, {}, {"message": "authentication required"}
        return _transport(url.replace("/datasets/publics/", "/datasets/"), accept)

    summary = run_mendeley_candidate_audit(
        _config(),
        tmp_path / "out",
        transport=fallback,
    )
    assert summary["inventory_readiness"]["status"] == STATUS_TEM_CANDIDATE_FOUND
    snapshots = json.loads(
        (tmp_path / "out" / "mendeley_api_snapshots.json").read_text(
            encoding="utf-8"
        )
    )
    assert all(
        item["selected_variant"] == "datasets_publics"
        for item in snapshots["snapshots"]
    )


def test_api_blocker_is_inconclusive_and_fail_closed(tmp_path: Path) -> None:
    def blocked(url: str, accept: str) -> tuple[int, Mapping[str, str], Any]:
        del url, accept
        return 401, {}, {"message": "authentication required"}

    summary = run_mendeley_candidate_audit(
        _config(),
        tmp_path / "out",
        transport=blocked,
    )
    assert summary["inventory_readiness"]["status"] == STATUS_API_BLOCKED
    assert summary["scientific_closeout"]["status"] == "Inconclusive"
    assert summary["result_counts"]["file_count"] == 0
    assert not summary["lineage_and_annotation_gates"]["annotation_pilot_ready"]


def test_output_overwrite_is_refused(tmp_path: Path) -> None:
    output = tmp_path / "out"
    run_mendeley_candidate_audit(_config(), output, transport=_transport)
    with pytest.raises(FileExistsError, match="absent or empty"):
        run_mendeley_candidate_audit(_config(), output, transport=_transport)


def test_invalid_primary_contract_is_rejected() -> None:
    payload = {
        "case_id": "mendeley_cop_co2p_co3o4_tem_candidate_audit",
        "api_base": "https://api.data.mendeley.com",
        "datasets": [
            {
                "dataset_id": "zhnbzhjrtr",
                "version": 1,
                "doi": "10.17632/zhnbzhjrtr.1",
                "role": "primary_raw",
                "expected_title_fragment": "Three-dimensional",
            }
        ],
    }
    with pytest.raises(ValueError, match="pinned candidate"):
        AuditConfig.from_mapping(payload)
