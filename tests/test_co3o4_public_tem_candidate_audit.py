from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "audit_co3o4_public_tem_candidates.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("co3o4_public_tem_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mendeley_config() -> dict[str, Any]:
    return {
        "sources": {
            "mendeley_palygorskite_co3o4": {
                "dataset_id": "kkk76z8g8z",
                "version": 1,
                "doi": "10.17632/kkk76z8g8z.1",
                "archive_name": "Data.rar",
                "known_snapshots": [
                    {
                        "name": "Data.rar",
                        "bytes": 16_250_421,
                        "sha256": "a" * 64,
                    }
                ],
                "provenance_policy": {
                    "same_version_identity_drift_observed": True,
                    "file_id_is_download_routing_only": True,
                    "current_api_declared_bytes_and_sha256_must_match_download": True,
                    "identity_drift_blocks_external_validation": True,
                },
            }
        }
    }


def test_mendeley_inventory_treats_file_id_as_routing_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()

    def fake_fetch(url: str, accept: str = "application/json") -> Any:
        del accept
        if "/snapshot/" in url:
            return {
                "doi": "10.17632/kkk76z8g8z.1",
                "name": "candidate",
                "licence": "CC BY 4.0",
            }
        return [
            {
                "id": "mutable-route-id",
                "filename": "Data.rar",
                "last_modified_date": "2020-12-07T03:45:06.517Z",
                "content_details": {
                    "size": 16_250_421,
                    "sha256_hash": "b" * 64,
                },
            }
        ]

    monkeypatch.setattr(module, "_fetch_json", fake_fetch)
    inventory, endpoint = module._mendeley_inventory(_mendeley_config())

    assert inventory["observed_archive"]["file_id"] == "mutable-route-id"
    assert inventory["observed_archive"]["sha256"] == "b" * 64
    assert not inventory["known_snapshot_match"]
    assert not inventory["source_identity_stable_for_version"]
    assert inventory["same_version_identity_drift_observed"]
    assert inventory["file_id_used_only_for_download_routing"]
    assert endpoint.endswith("/mutable-route-id/file_downloaded")


def _run_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "case_id": "co3o4_public_tem_candidate_audit",
                "audit_date": "2026-08-03",
            }
        ),
        encoding="utf-8",
    )
    return path


def _patch_run_dependencies(
    module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    representation: dict[str, Any],
) -> None:
    monkeypatch.setattr(module, "_zenodo_inventory", lambda config: {"record_id": "1"})
    monkeypatch.setattr(
        module,
        "_mendeley_inventory",
        lambda config: (
            {
                "observed_archive": {
                    "file_id": "route",
                    "name": "Data.rar",
                    "bytes": 10,
                    "sha256": "c" * 64,
                },
                "known_snapshot_match": False,
                "source_identity_stable_for_version": False,
                "same_version_identity_drift_observed": True,
            },
            "https://example.invalid/archive",
        ),
    )
    monkeypatch.setattr(module, "_download", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "_inspect_archive", lambda *args, **kwargs: representation)


def test_run_preserves_wrong_modality_snapshot_as_blocked_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    representation = {
        "archive_member_count": 760,
        "suffix_counts": {".png": 3},
        "decodable_image_count": 3,
        "decodable_images": [],
        "tem_or_hrtem_member_count": 0,
        "stem_member_count": 0,
        "microscopy_detector_file_count": 0,
        "tem_or_stem_candidate_paths": [],
        "microscopy_detector_members": [],
        "known_wrong_modality_representation_match": False,
    }
    _patch_run_dependencies(module, monkeypatch, representation)

    output = tmp_path / "out"
    summary = module.run(_run_config(tmp_path), output)

    assert summary["result"] == (
        "source_identity_changed_but_current_archive_remains_wrong_modality"
    )
    assert not summary["manual_review_required"]
    assert not summary["external_validation_ready"]
    assert not (output / "_transient").exists()
    assert (output / "official_source_inventory.json").is_file()
    assert (output / "co3o4_public_tem_candidate_audit_summary.json").is_file()


def test_run_requires_manual_review_when_tem_or_stem_appears(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    representation = {
        "archive_member_count": 1,
        "suffix_counts": {".dm4": 1},
        "decodable_image_count": 0,
        "decodable_images": [],
        "tem_or_hrtem_member_count": 1,
        "stem_member_count": 0,
        "microscopy_detector_file_count": 1,
        "tem_or_stem_candidate_paths": ["new/TEM/sample.dm4"],
        "microscopy_detector_members": ["new/TEM/sample.dm4"],
        "known_wrong_modality_representation_match": False,
    }
    _patch_run_dependencies(module, monkeypatch, representation)

    summary = module.run(_run_config(tmp_path), tmp_path / "out")

    assert summary["result"] == "source_representation_changed_manual_review_required"
    assert summary["manual_review_required"]
    assert not summary["external_validation_ready"]
    assert summary["scientific_closeout"]["status"] == "Inconclusive"
