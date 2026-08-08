from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from mca.analyzer_readiness import (
    EXPECTED_ANALYZER_IDS,
    AnalyzerReadinessError,
    generate_analyzer_readiness_registry,
)
from mca.analyzer_readiness_cli import main as readiness_cli_main


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "case_studies" / "analyzer_readiness_registry" / "readiness_registry.json"


def test_pinned_registry_generates_fail_closed_readiness_evidence(tmp_path: Path) -> None:
    output = tmp_path / "readiness"
    result = generate_analyzer_readiness_registry(CONFIG, output)

    assert result["analyzer_count"] == 10
    assert result["independent_external_validation_ready_count"] == 0
    assert result["engineering_decision_ready_count"] == 0

    summary = json.loads((output / "analyzer_readiness_summary.json").read_text(encoding="utf-8"))
    assert summary["snapshot_date"] == "2026-08-09"
    assert summary["software_supported_count"] == 10
    assert summary["public_real_data_exercised_count"] == 10
    assert summary["independent_external_validation_ready_count"] == 0
    assert summary["engineering_decision_ready_count"] == 0
    assert summary["scientific_evidence_level_counts"] == {
        "Diagnostic": 8,
        "Inconclusive": 2,
    }

    with (output / "analyzer_readiness.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert tuple(row["analyzer_id"] for row in rows) == EXPECTED_ANALYZER_IDS
    assert all(row["independent_external_validation_ready"] == "False" for row in rows)
    assert all(row["engineering_decision_ready"] == "False" for row in rows)

    report = (output / "analyzer_readiness_report.md").read_text(encoding="utf-8")
    assert "Passing software tests does not establish scientific validity" in report
    assert "Transmission electron microscopy" in report
    assert "Selected-area electron diffraction" in report
    assert "2048 by 2048 float64 source TIFF pixels" in report
    assert "do not acquire more SAED pixels" in report
    assert "cross-material source-format evidence" in report

    manifest = json.loads(
        (output / "analyzer_readiness_artifact_manifest.json").read_text(encoding="utf-8")
    )
    assert len(manifest["artifacts"]) == 3
    assert manifest["scientific_boundary"]["scientific_claims_promoted"] is False
    assert manifest["scientific_boundary"]["missing_metadata_inferred"] is False


def test_registry_keeps_recent_tem_and_saed_evidence_bounded() -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    rows = {row["analyzer_id"]: row for row in payload["analyzers"]}

    tem = rows["tem"]
    assert tem["scientific_evidence_level"] == "Inconclusive"
    assert "cross-material DM3/DM4 sources" in tem["primary_limitation"]
    assert "exact-Co3O4 institutional source remains access-blocked" in tem["primary_limitation"]
    assert "Do not substitute cross-material source-format evidence" in tem["next_required_evidence"]

    saed = rows["saed"]
    assert saed["scientific_evidence_level"] == "Inconclusive"
    assert "23 K, 91 K, and 172 K temperature semantics" in saed["primary_limitation"]
    assert "Diagnostic source-pattern-family correspondence" in saed["primary_limitation"]
    assert "BIR 300 keV" in saed["primary_limitation"]
    assert "do not acquire more SAED pixels" in saed["next_required_evidence"]
    assert saed["independent_external_validation_ready"] is False
    assert saed["engineering_decision_ready"] is False


def test_registry_rejects_any_promoted_external_or_engineering_readiness(
    tmp_path: Path,
) -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["analyzers"][0]["independent_external_validation_ready"] = True
    config = tmp_path / "promoted.json"
    config.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AnalyzerReadinessError, match="must remain false"):
        generate_analyzer_readiness_registry(config, tmp_path / "output")


def test_registry_rejects_missing_analyzer_and_leaves_no_output(tmp_path: Path) -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["analyzers"] = payload["analyzers"][:-1]
    config = tmp_path / "missing.json"
    config.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "output"

    with pytest.raises(AnalyzerReadinessError, match="exactly 10"):
        generate_analyzer_readiness_registry(config, output)
    assert not output.exists()
    assert not (tmp_path / ".output.building").exists()


def test_registry_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    config = tmp_path / "duplicate.json"
    config.write_text('{"schema_version":"1.0","schema_version":"1.0"}', encoding="utf-8")

    with pytest.raises(AnalyzerReadinessError, match="duplicate JSON key"):
        generate_analyzer_readiness_registry(config, tmp_path / "output")


def test_registry_refuses_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        generate_analyzer_readiness_registry(CONFIG, output)


def test_installed_cli_generates_registry(tmp_path: Path, capsys) -> None:
    output = tmp_path / "cli"
    assert readiness_cli_main(
        ["--config", str(CONFIG), "--output", str(output)]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "analyzer_readiness_registry_generated"
    assert (output / "analyzer_readiness_report.md").is_file()
