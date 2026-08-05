from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PUBLISH_WORKFLOW = WORKFLOWS / "publish-v0-11-0-release.yml"


def test_tracked_workflows_do_not_use_superseded_action_majors() -> None:
    superseded = (
        "actions/checkout@v4",
        "actions/setup-python@v5",
        "actions/upload-artifact@v4",
    )
    violations: list[str] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        for token in superseded:
            if token in text:
                violations.append(f"{path.relative_to(ROOT)}: {token}")
    assert violations == []


def test_release_publish_job_sets_up_python_before_metadata_check() -> None:
    text = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
    publish = text.split("  publish-github-release:\n", maxsplit=1)[1]

    setup = publish.index("actions/setup-python@v7")
    metadata_check = publish.index("import tomllib")
    assert setup < metadata_check
    assert "permissions:\n      contents: write" in publish
    assert 'GH_TOKEN: ${{ github.token }}' in publish
