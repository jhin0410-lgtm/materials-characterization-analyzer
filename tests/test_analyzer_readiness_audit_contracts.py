from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from mca.analyzer_readiness import AnalyzerReadinessError, generate_analyzer_readiness_registry
from mca.analyzer_readiness_cli import build_parser


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "case_studies" / "analyzer_readiness_registry" / "readiness_registry.json"


def _write_payload(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_registry_rejects_scientific_evidence_promotion(tmp_path: Path) -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["analyzers"][0]["scientific_evidence_level"] = "Supported"
    with pytest.raises(AnalyzerReadinessError, match="must remain Diagnostic"):
        generate_analyzer_readiness_registry(
            _write_payload(tmp_path, payload), tmp_path / "output"
        )


def test_registry_rejects_scientific_status_rewrite(tmp_path: Path) -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["analyzers"][8]["scientific_validation_status"] = "validated"
    with pytest.raises(AnalyzerReadinessError, match="must remain"):
        generate_analyzer_readiness_registry(
            _write_payload(tmp_path, payload), tmp_path / "output"
        )


def test_registry_canonicalizes_tracked_case_aliases_and_preserves_supported_uses(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    generate_analyzer_readiness_registry(CONFIG, output)

    with (output / "analyzer_readiness.csv").open(encoding="utf-8", newline="") as handle:
        rows = {row["analyzer_id"]: row for row in csv.DictReader(handle)}
    assert "public_carbon_four_materials" in rows["raman"]["representative_cases"]
    assert "public_carbon_four_material|" not in rows["raman"]["representative_cases"]
    assert "public_cobalt_oxide_tem_masks" in rows["tem"]["representative_cases"]
    assert rows["xrd"]["supported_uses"]

    summary = json.loads(
        (output / "analyzer_readiness_summary.json").read_text(encoding="utf-8")
    )
    assert len(summary["analyzers"]) == 10
    assert all(row["supported_uses"] for row in summary["analyzers"])

    report = (output / "analyzer_readiness_report.md").read_text(encoding="utf-8")
    assert "**Supported uses:**" in report
    assert "public_carbon_four_materials" in report


def test_readiness_cli_requires_explicit_config() -> None:
    action = next(
        action for action in build_parser()._actions if action.dest == "config"
    )
    assert action.required is True
    assert action.default is None
