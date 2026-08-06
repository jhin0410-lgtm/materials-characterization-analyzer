from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import run_zenodo_wtacrv_tem_saed_audit as runner


def test_bounded_header_does_not_use_path_read_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "large.dm3"
    path.write_bytes(b"\x00\x00\x00\x03" + b"x" * 4 + b"\x00\x00\x00\x01" + b"z" * 100)

    def forbidden_read_bytes(self: Path) -> bytes:
        raise AssertionError("full-file read is forbidden")

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
    result = runner.bounded_header(path)
    assert result["header_bytes"] == 32
    assert result["digital_micrograph_version_big_endian"] == 3
    assert result["digital_micrograph_byte_order_marker"] == 1


def test_repository_config_uses_official_zenodo_license_identifier() -> None:
    config_path = (
        Path(__file__).resolve().parents[1]
        / "case_studies"
        / "zenodo_wtacrv_tem_saed_source_audit"
        / "case_config.json"
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["source"]["allowed_license_ids"] == ["odc-odbl"]
