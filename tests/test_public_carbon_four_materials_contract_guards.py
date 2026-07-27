from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.run_public_carbon_four_materials_case as four


CONFIG_PATH = Path("case_studies/public_carbon_four_materials/case_config.json")


def test_four_material_contract_requires_exact_sample_set() -> None:
    config = four.load_json(CONFIG_PATH)

    missing = copy.deepcopy(config)
    missing["samples"] = missing["samples"][:3]
    with pytest.raises(ValueError, match="exactly four samples"):
        four._require_unique_samples(missing)

    relabeled = copy.deepcopy(config)
    relabeled["samples"][0]["source_label"] = "NOT-DWCNT"
    with pytest.raises(ValueError, match="fixed contract"):
        four._require_unique_samples(relabeled)


@pytest.mark.parametrize(
    "unsafe_id",
    ["../escape", "/absolute", r"..\\escape", ".", "..", "bad/name"],
)
def test_four_material_contract_rejects_unsafe_sample_ids(unsafe_id: str) -> None:
    config = four.load_json(CONFIG_PATH)
    broken = copy.deepcopy(config)
    broken["samples"][0]["sample_id"] = unsafe_id

    with pytest.raises(ValueError, match="path-safe identifier"):
        four._require_unique_samples(broken)


def test_safe_sample_root_rejects_traversal_even_after_validation_boundary(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="escapes the output directory"):
        four._safe_sample_root(tmp_path, "../escape")


def test_dataset_version_must_match_configured_release() -> None:
    payload = {
        "data": {
            "latestVersion": {
                "versionNumber": 1,
                "versionMinorNumber": 0,
                "files": [],
            }
        }
    }

    assert four._verify_dataset_version(payload, "1.0") == "1.0"
    with pytest.raises(ValueError, match="version mismatch"):
        four._verify_dataset_version(payload, "2.0")


def test_download_rejects_supplied_unsupported_checksum_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(four.discover, "_request_bytes", lambda _: b"public-source")
    destination = tmp_path / "source.tab"
    record = {
        "datafile_id": 123,
        "filename": "source.tab",
        "checksum_type": "SHA-512",
        "checksum_value": "abc",
        "content_type": "text/plain",
    }

    with pytest.raises(ValueError, match="could not be verified"):
        four._download_exact_source(record, destination, cache={})

    assert not destination.exists()


def test_sample_specific_report_does_not_claim_dwcnt_for_flg(tmp_path: Path) -> None:
    config = four.load_json(CONFIG_PATH)
    flg = next(sample for sample in config["samples"] if sample["sample_id"] == "public-flg")
    resolved = four.build_sample_config(config, flg)
    analyses = {
        name: {"analysis_result": SimpleNamespace(warnings=[])}
        for name in four.EXECUTED_MODALITIES
    }
    report_path = tmp_path / "case_validation_report.md"
    four._material_case_report(
        report_path,
        resolved,
        tmp_path / "source.json",
        tmp_path / "comparability.csv",
        analyses,
        {"image_shape": [10, 10], "image_dtype": "uint8"},
    )

    report = report_path.read_text(encoding="utf-8")
    assert "# Public FLG Multimodal Validation Report" in report
    assert "# Public DWCNT Multimodal Validation Report" not in report
    assert "intertwined nanotubes" not in report
    assert "few-layer graphene" in report


def test_workflow_tracks_exercised_analyzer_modules() -> None:
    workflow = Path(".github/workflows/public-carbon-four-materials.yml").read_text(
        encoding="utf-8"
    )
    for path in (
        "src/mca/raman.py",
        "src/mca/ftir.py",
        "src/mca/xps.py",
        "src/mca/thermal.py",
        "src/mca/handoff_bundle.py",
    ):
        assert workflow.count(f'"{path}"') == 2


def test_configured_version_is_persisted_in_resolved_sample_config() -> None:
    config = four.load_json(CONFIG_PATH)
    sample = config["samples"][0]
    resolved = four.build_sample_config(config, sample)

    assert resolved["dataset"]["version"] == "1.0"
    assert resolved["primary_sample"]["source_label"] == "DWCNT"
    assert (
        resolved["suitability_gates"]["tem_quantitative_segmentation"]["status"]
        == "blocked_method_mismatch"
    )
