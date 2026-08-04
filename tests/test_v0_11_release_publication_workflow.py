from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "publish-v0-11-0-release.yml"
RELEASE_NOTES = ROOT / "docs" / "releases" / "0.11.0.md"


def test_v0_11_publication_workflow_is_fail_closed_and_main_only() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "RELEASE_TAG: v0.11.0" in text
    assert "RELEASE_VERSION: 0.11.0" in text
    assert "python -m pytest -q" in text
    assert "python -m build" in text
    assert "dist/*.whl" in text
    assert "mca analyzer-readiness" in text
    assert "mca build-handoff --help" in text
    assert "mca validate-handoff --help" in text
    assert "independent_external_validation_ready_count" in text
    assert "engineering_decision_ready_count" in text
    assert "scientific_claims_promoted" in text
    assert "github.event_name != 'pull_request'" in text
    assert "github.ref == 'refs/heads/main'" in text
    assert "contents: write" in text
    assert "git rev-parse \"${RELEASE_TAG}^{commit}\"" in text
    assert "gh release create" in text
    assert "--verify-tag" in text
    assert "SHA256SUMS.txt" in text


def test_v0_11_release_notes_preserve_scientific_boundaries() -> None:
    text = RELEASE_NOTES.read_text(encoding="utf-8")

    assert "Release date: **2026-08-04**" in text
    assert "Independent external-validation readiness: `0/10`" in text
    assert "Engineering-decision readiness: `0/10`" in text
    assert "TEM independent in-domain segmentation performance remains `Inconclusive`" in text
    assert "SAED crystallographic performance remains `Inconclusive`" in text
    assert "No third-party raw dataset is redistributed" in text
