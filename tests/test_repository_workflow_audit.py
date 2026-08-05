from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PUBLISH_WORKFLOW = WORKFLOWS / "publish-v0-11-0-release.yml"


def test_tracked_workflows_do_not_use_superseded_setup_python_v5() -> None:
    violations = [
        str(path.relative_to(ROOT))
        for path in sorted(WORKFLOWS.glob("*.yml"))
        if "actions/setup-python@v5" in path.read_text(encoding="utf-8")
    ]
    assert violations == []


def test_release_publish_job_sets_up_python_before_metadata_check() -> None:
    text = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
    publish = text.split("  publish-github-release:\n", maxsplit=1)[1]

    setup = publish.index("actions/setup-python@v7")
    metadata_check = publish.index("import tomllib")
    assert setup < metadata_check
    assert "permissions:\n      contents: write" in publish
    assert 'GH_TOKEN: ${{ github.token }}' in publish
