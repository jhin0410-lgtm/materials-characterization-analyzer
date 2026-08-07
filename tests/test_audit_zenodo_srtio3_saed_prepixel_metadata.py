from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import audit_zenodo_srtio3_saed_prepixel_metadata as audit


def _config_payload() -> dict:
    return json.loads(
        Path("case_studies/zenodo_srtio3_saed_prepixel_metadata/case_config.json").read_text(
            encoding="utf-8"
        )
    )


def test_repository_contract_ends_before_verified_pixel_strip() -> None:
    config = audit._validate_config(_config_payload())
    strip = config["pixel_boundary"]["verified_first_strip_offset"]
    prefix = config["pixel_boundary"]["maximum_decompressed_prefix_bytes"]
    assert strip == 272
    assert prefix == 262
    assert prefix < strip
    assert config["authorized_text_tags"] == [
        {"name": "ImageDescription", "offset": 194, "bytes": 24},
        {"name": "Software", "offset": 250, "bytes": 12},
    ]
    assert all(tag["offset"] + tag["bytes"] <= prefix for tag in config["authorized_text_tags"])


def test_ascii_decoder_records_text_and_hash_without_raw_bytes() -> None:
    result = audit._decode_ascii(b"ImageJ=1.54\x00\x00")
    assert result["ascii_valid"] is True
    assert result["text"] == "ImageJ=1.54"
    assert result["raw_length"] == 13
    assert result["stripped_length"] == 11
    assert len(result["sha256"]) == 64


def test_non_ascii_text_is_not_silently_replaced() -> None:
    result = audit._decode_ascii(b"abc\xff\x00")
    assert result["ascii_valid"] is False
    assert result["text"] is None
    assert len(result["sha256"]) == 64


def test_config_rejects_prefix_at_or_beyond_pixel_strip() -> None:
    payload = _config_payload()
    payload["pixel_boundary"]["maximum_decompressed_prefix_bytes"] = 272
    with pytest.raises(audit.SrTiO3SaedPrePixelMetadataError, match="262 bytes"):
        audit._validate_config(payload)


def test_config_rejects_pixel_authorization() -> None:
    payload = _config_payload()
    payload["scientific_boundary"]["pixel_array_decode_authorized"] = True
    with pytest.raises(audit.SrTiO3SaedPrePixelMetadataError, match="must remain disabled"):
        audit._validate_config(payload)


def test_config_rejects_additional_text_range() -> None:
    payload = _config_payload()
    payload["authorized_text_tags"].append({"name": "Other", "offset": 262, "bytes": 10})
    with pytest.raises(audit.SrTiO3SaedPrePixelMetadataError, match="ranges drifted"):
        audit._validate_config(payload)
