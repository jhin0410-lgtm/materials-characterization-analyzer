from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from mca.tem_mendeley_candidate_audit import (
    STATUS_API_BLOCKED,
    STATUS_INVENTORY_RESOLVED,
    STATUS_TEM_CANDIDATE_FOUND,
    AuditConfig,
    refresh_mendeley_candidate_audit_manifest,
    run_mendeley_candidate_audit,
)


def _config() -> AuditConfig:
    return AuditConfig.from_mapping(
        {
            "case_id": "mendeley_cop_co2p_co3o4_tem_candidate_audit",
            "api_base": "https://data.mendeley.com/public-api",
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


def _snapshot(dataset_id: str) -> dict[str, Any]:
    title = {
        "8w66synjmx": "Raw data-Three-dimensional nano-framework",
        "zhnbzhjrtr": "Three-dimensional nano-framework raw data",
        "jz9dpgwwc3": "processed data-Three-dimensional nano-framework",
    }[dataset_id]
    return {
        "id": dataset_id,
        "version": 1,
        "name": title,
        "description": "raw XRD, SEM, TEM and electrochemical data",
        "doi": {"id": f"10.17632/{dataset_id}.1"},
        "licence": {"name": "CC0"},
    }


def _file(
    identifier: str,
    filename: str,
    sha256: str,
    size: int,
    description: str = "",
) -> dict[str, Any]:
    return {
        "id": identifier,
        "filename": filename,
        "description": description,
        "content_details": {
            "id": f"content-{identifier}",
            "sha256_hash": sha256,
            "content_type": "application/octet-stream",
            "size": size,
            "download_url": "https://temporary.example/file?X-Amz-Signature=secret",
        },
        "status": "AVAILABLE",
    }


def _transport(url: str, accept: str) -> tuple[int, Mapping[str, str], Any]:
    del accept
    dataset_id = next(
        item for item in ("8w66synjmx", "zhnbzhjrtr", "jz9dpgwwc3") if item in url
    )
    if "/snapshot/" in url:
        return 200, {"Content-Type": "application/json"}, _snapshot(dataset_id)
    common = [
        _file("archive", "database.rar", "a" * 64, 12_345),
        _file(
            "tem-image",
            "TEM_image.tif",
            "b" * 64,
            456,
            "Transmission electron microscopy image",
        ),
    ]
    if dataset_id in {"8w66synjmx", "zhnbzhjrtr"}:
        return 200, {"Content-Type": "application/json"}, common
    return 200, {"Content-Type": "application/json"}, [
        _file("processed", "processed data.rar", "c" * 64, 789)
    ]


def test_resolves_public_files_plain_tem_and_duplicate_content(
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
    assert summary["inventory_readiness"]["duplicate_raw_record_content_identical"]
    assert not summary["lineage_and_annotation_gates"]["annotation_pilot_ready"]
    assert not summary["lineage_and_annotation_gates"][
        "external_model_evaluation_ready"
    ]

    inventory = (output / "mendeley_file_inventory.csv").read_text(encoding="utf-8")
    assert "TEM_image.tif" in inventory
    assert "bbbbbbbbbbbbbbbb" in inventory
    snapshots = json.loads(
        (output / "mendeley_api_snapshots.json").read_text(encoding="utf-8")
    )
    encoded = json.dumps(snapshots, sort_keys=True)
    assert "temporary.example" not in encoded
    assert '"download_url": "redacted"' in encoded

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


def test_generic_archive_inventory_is_resolved_without_false_tem_claim(
    tmp_path: Path,
) -> None:
    def archives(url: str, accept: str) -> tuple[int, Mapping[str, str], Any]:
        del accept
        dataset_id = next(
            item
            for item in ("8w66synjmx", "zhnbzhjrtr", "jz9dpgwwc3")
            if item in url
        )
        if "/snapshot/" in url:
            return 200, {}, _snapshot(dataset_id)
        name = "processed data.rar" if dataset_id == "jz9dpgwwc3" else "database.rar"
        digest = "c" * 64 if dataset_id == "jz9dpgwwc3" else "a" * 64
        return 200, {}, [_file(dataset_id, name, digest, 123)]

    summary = run_mendeley_candidate_audit(
        _config(),
        tmp_path / "out",
        transport=archives,
    )
    assert summary["inventory_readiness"]["status"] == STATUS_INVENTORY_RESOLVED
    assert summary["result_counts"]["primary_tem_candidate_file_count"] == 0
    assert summary["inventory_readiness"]["duplicate_raw_record_content_identical"]
    assert "inventory the public root archive" in summary["next_action"]


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
        "api_base": "https://data.mendeley.com/public-api",
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



def test_primary_file_failure_is_blocked_when_other_records_succeed(
    tmp_path: Path,
) -> None:
    def partial(url: str, accept: str) -> tuple[int, Mapping[str, str], Any]:
        del accept
        dataset_id = next(
            item
            for item in ("8w66synjmx", "zhnbzhjrtr", "jz9dpgwwc3")
            if item in url
        )
        if "/snapshot/" in url:
            return 200, {}, _snapshot(dataset_id)
        if dataset_id == "8w66synjmx":
            return 503, {}, {"message": "primary unavailable"}
        return 200, {}, [_file(dataset_id, "database.rar", "a" * 64, 123)]

    summary = run_mendeley_candidate_audit(
        _config(),
        tmp_path / "out",
        transport=partial,
    )
    assert summary["inventory_readiness"]["status"] == STATUS_API_BLOCKED
    assert not summary["inventory_readiness"]["primary_root_files_request_succeeded"]
    assert not summary["inventory_readiness"]["primary_file_inventory_resolved"]
    assert summary["scientific_closeout"]["status"] == "Inconclusive"


def test_duplicate_identity_requires_complete_checksums(tmp_path: Path) -> None:
    def missing_checksums(
        url: str, accept: str
    ) -> tuple[int, Mapping[str, str], Any]:
        del accept
        dataset_id = next(
            item
            for item in ("8w66synjmx", "zhnbzhjrtr", "jz9dpgwwc3")
            if item in url
        )
        if "/snapshot/" in url:
            return 200, {}, _snapshot(dataset_id)
        item = _file(dataset_id, "database.rar", "a" * 64, 123)
        item["content_details"].pop("sha256_hash")
        return 200, {}, [item]

    summary = run_mendeley_candidate_audit(
        _config(),
        tmp_path / "out",
        transport=missing_checksums,
    )
    assert not summary["inventory_readiness"]["primary_checksums_and_sizes_complete"]
    assert not summary["inventory_readiness"][
        "duplicate_raw_record_checksums_and_sizes_complete"
    ]
    assert not summary["inventory_readiness"][
        "duplicate_raw_record_content_identical"
    ]


def test_configured_api_base_is_used_and_reported(tmp_path: Path) -> None:
    payload = {
        "case_id": "mendeley_cop_co2p_co3o4_tem_candidate_audit",
        "api_base": "https://api.data.mendeley.com",
        "datasets": [
            {
                "dataset_id": item.dataset_id,
                "version": item.version,
                "doi": item.doi,
                "role": item.role,
                "expected_title_fragment": item.expected_title_fragment,
            }
            for item in _config().datasets
        ],
    }
    config = AuditConfig.from_mapping(payload)
    observed_urls: list[str] = []

    def transport(url: str, accept: str) -> tuple[int, Mapping[str, str], Any]:
        observed_urls.append(url)
        return _transport(url, accept)

    summary = run_mendeley_candidate_audit(
        config,
        tmp_path / "out",
        transport=transport,
    )
    assert observed_urls
    assert all(url.startswith("https://api.data.mendeley.com/") for url in observed_urls)
    assert summary["source"]["api_base"] == "https://api.data.mendeley.com"


def test_refresh_manifest_binds_probe_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "out"
    run_mendeley_candidate_audit(_config(), output, transport=_transport)
    (output / "mendeley_public_page_probe.json").write_text(
        '{"case_id":"page-probe"}\n', encoding="utf-8"
    )
    (output / "mendeley_anonymous_public_api_probe.json").write_text(
        '{"case_id":"api-probe"}\n', encoding="utf-8"
    )
    manifest = refresh_mendeley_candidate_audit_manifest(output)
    assert manifest["artifact_count"] == 7
    paths = {record["path"] for record in manifest["artifacts"]}
    assert "mendeley_public_page_probe.json" in paths
    assert "mendeley_anonymous_public_api_probe.json" in paths
    for record in manifest["artifacts"]:
        path = output / record["path"]
        assert record["bytes"] == path.stat().st_size
        assert record["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
