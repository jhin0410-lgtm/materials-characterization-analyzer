from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from scripts import probe_srtio3_figure1_full_resolution as probe

CONFIG_PATH = Path(
    "case_studies/zenodo_srtio3_figure1_full_resolution_readiness/evidence_contract.json"
)


def _config_payload() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _png_header(width: int, height: int) -> bytes:
    return (
        probe.PNG_SIGNATURE
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + bytes([8, 6, 0, 0, 0])
        + b"\x00\x00\x00\x00"
    )


def test_contract_authorizes_only_33_byte_header_probe() -> None:
    config = probe._validate_config(_config_payload())
    operations = config["authorized_operations"]
    range_contract = config["range_contract"]

    assert operations["request_exact_candidate_full_url"] is True
    assert operations["require_http_range_response"] is True
    assert operations["read_png_signature_and_ihdr_only"] is True
    assert operations["record_http_headers_and_png_dimensions"] is True
    assert all(
        value is False
        for key, value in operations.items()
        if key
        not in {
            "request_exact_candidate_full_url",
            "require_http_range_response",
            "read_png_signature_and_ihdr_only",
            "record_http_headers_and_png_dimensions",
        }
    )
    assert range_contract["request_start_byte"] == 0
    assert range_contract["request_end_byte"] == 32
    assert range_contract["expected_response_bytes"] == 33
    assert range_contract["require_http_status"] == 206
    assert range_contract["maximum_total_response_bytes"] == 33


def test_predecessor_evidence_requires_higher_resolution_restart_condition() -> None:
    config = probe._validate_config(_config_payload())
    probe._validate_evidence(config)


def test_png_ihdr_parser_extracts_dimensions_without_pixel_decode() -> None:
    parsed = probe._parse_png_header(_png_header(2048, 1190))

    assert parsed == {
        "width": 2048,
        "height": 1190,
        "bit_depth": 8,
        "color_type": 6,
        "compression_method": 0,
        "filter_method": 0,
        "interlace_method": 0,
    }


def test_png_ihdr_parser_rejects_non_png_or_wrong_length() -> None:
    with pytest.raises(probe.FigureFullResolutionReadinessError, match="exactly 33"):
        probe._parse_png_header(_png_header(1024, 768)[:-1])

    payload = bytearray(_png_header(1024, 768))
    payload[:8] = b"not-a-png"
    with pytest.raises(probe.FigureFullResolutionReadinessError, match="PNG signature"):
        probe._parse_png_header(bytes(payload))


def test_png_ihdr_parser_rejects_non_ihdr_first_chunk() -> None:
    payload = bytearray(_png_header(1024, 768))
    payload[12:16] = b"IDAT"
    with pytest.raises(probe.FigureFullResolutionReadinessError, match="IHDR"):
        probe._parse_png_header(bytes(payload))


def test_candidate_full_url_must_remain_exact_springer_full_path(tmp_path: Path) -> None:
    config = _config_payload()
    config["source_publication"]["candidate_full_url"] = (
        "https://example.com/full/41586_2026_10823_Fig1_HTML.png"
    )
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(probe.FigureFullResolutionReadinessError, match="host"):
        probe._validate_config(probe._load_json(path))
