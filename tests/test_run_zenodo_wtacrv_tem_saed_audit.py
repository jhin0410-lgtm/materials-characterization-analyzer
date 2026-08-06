from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import run_zenodo_wtacrv_tem_saed_audit as runner


def test_bounded_dm3_header_does_not_use_path_read_bytes(
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


def test_bounded_dm4_header_uses_version_specific_offsets(tmp_path: Path) -> None:
    path = tmp_path / "pattern.dm4"
    declared_payload_bytes = 17_395_058
    path.write_bytes(
        b"\x00\x00\x00\x04"
        + declared_payload_bytes.to_bytes(8, "big")
        + b"\x00\x00\x00\x01"
        + b"z" * 32
    )
    result = runner.bounded_header(path)
    assert result["digital_micrograph_version_big_endian"] == 4
    assert (
        result["digital_micrograph_declared_payload_bytes_big_endian"]
        == declared_payload_bytes
    )
    assert result["digital_micrograph_byte_order_marker"] == 1


def test_unirradiated_path_is_not_double_classified() -> None:
    cues = set(
        runner.precise_microscopy_cues(
            "D_Kalita_NME/TEM/SAED_HF_unirradiated area.dm4"
        )
    )
    assert "as_deposited_condition_cue" in cues
    assert "irradiated_condition_cue" not in cues
    assert "saed_name_cue" in cues


def test_irradiated_path_remains_irradiated() -> None:
    cues = set(
        runner.precise_microscopy_cues(
            "D_Kalita_NME/TEM/SAED_HF_irradiated area.dm4"
        )
    )
    assert "irradiated_condition_cue" in cues
    assert "as_deposited_condition_cue" not in cues


def test_repository_config_uses_official_zenodo_license_identifier() -> None:
    config_path = (
        Path(__file__).resolve().parents[1]
        / "case_studies"
        / "zenodo_wtacrv_tem_saed_source_audit"
        / "case_config.json"
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["source"]["allowed_license_ids"] == ["odc-odbl"]
