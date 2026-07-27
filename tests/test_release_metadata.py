from __future__ import annotations

import re
import tomllib
from importlib.metadata import version as installed_version
from pathlib import Path

from mca import __version__, cli_entry


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "materials-characterization-analyzer"


def _project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def _citation_version() -> str:
    text = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    match = re.search(r"(?m)^version:\s*([^\s#]+)\s*$", text)
    if match is None:
        raise AssertionError("CITATION.cff does not contain a top-level version field")
    return match.group(1).strip('"\'')


def test_public_version_metadata_is_consistent() -> None:
    expected = _project_version()
    assert __version__ == expected
    assert installed_version(PACKAGE_NAME) == expected
    assert _citation_version() == expected

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{expected}] - " in changelog


def test_cli_reports_public_version(capsys) -> None:
    assert cli_entry.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"{PACKAGE_NAME} {__version__}"


def test_short_version_flag(capsys) -> None:
    assert cli_entry.main(["-V"]) == 0
    assert capsys.readouterr().out.strip() == f"{PACKAGE_NAME} {__version__}"


def test_release_files_and_license_are_present() -> None:
    required = [
        ROOT / "CHANGELOG.md",
        ROOT / "CITATION.cff",
        ROOT / "LICENSE",
        ROOT / "docs" / "release_checklist.md",
    ]
    assert all(path.is_file() for path in required)

    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    assert "license: BSD-3-Clause" in citation
    assert "repository-code:" in citation
