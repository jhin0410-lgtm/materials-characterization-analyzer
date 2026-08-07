from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import pytest

from scripts import audit_zenodo_bir_300kev_tvips_header_prefix as audit


def _valid_header() -> bytes:
    values = [
        256,
        2,
        512,
        512,
        16,
        0,
        0,
        1,
        1,
        10,
        300000,
        1000,
        60,
    ]
    dummy = (b"TVIPS " * 34)[:204].ljust(204, b" ")
    return struct.pack("<13I204s", *values, dummy)


def _raw_deflate(payload: bytes) -> bytes:
    compressor = zlib.compressobj(level=6, wbits=-15)
    return compressor.compress(payload) + compressor.flush()


def test_tvips_header_matches_pinned_structural_contract() -> None:
    parser = {
        "general_header_uint32_fields": [
            "size",
            "version",
            "dimx",
            "dimy",
            "bitsperpixel",
            "offsetx",
            "offsety",
            "binx",
            "biny",
            "pixelsize",
            "ht",
            "magtotal",
            "frameheaderbytes",
        ],
        "general_header_bytes": 256,
        "allowed_versions": [1, 2],
        "allowed_bits_per_pixel": [8, 16],
        "frame_header_core_bytes": 60,
    }
    result = audit._parse_tvips_header(_valid_header(), parser)
    assert result["structural_match"] is True
    assert result["fields"]["version"] == 2
    assert result["fields"]["ht"] == 300000
    assert result["checks"]["frame_header_core_compatible"] is True
    assert result["dummy_tvips_token_count"] > 0


def test_invalid_header_dimensions_do_not_get_promoted() -> None:
    payload = bytearray(_valid_header())
    payload[8:12] = (0).to_bytes(4, "little")
    parser = {
        "general_header_uint32_fields": [
            "size",
            "version",
            "dimx",
            "dimy",
            "bitsperpixel",
            "offsetx",
            "offsety",
            "binx",
            "biny",
            "pixelsize",
            "ht",
            "magtotal",
            "frameheaderbytes",
        ],
        "general_header_bytes": 256,
        "allowed_versions": [1, 2],
        "allowed_bits_per_pixel": [8, 16],
        "frame_header_core_bytes": 60,
    }
    result = audit._parse_tvips_header(bytes(payload), parser)
    assert result["structural_match"] is False
    assert result["checks"]["dimensions_positive"] is False


def test_selected_deflate_member_reads_only_bounded_prefix(monkeypatch) -> None:
    member_path = "A/series1.tvips"
    compressed = _raw_deflate(_valid_header() + b"pixel-payload-must-not-be-decoded" * 1000)
    filename = member_path.encode("utf-8")
    local = struct.pack(
        "<4s5H3I2H",
        b"PK\x03\x04",
        20,
        0x0800,
        8,
        0,
        0,
        0,
        len(compressed),
        999999,
        len(filename),
        0,
    ) + filename + compressed
    archive = b"x" * 100 + local + b"z" * 100

    def fake_fetch(_url: str, *, start: int, end: int, expected_total: int) -> bytes:
        assert expected_total == len(archive)
        return archive[start : end + 1]

    monkeypatch.setattr(audit.remote, "fetch_range", fake_fetch)
    target = {"bytes": len(archive), "content_url": "https://zenodo.org/fake"}
    record = {
        "local_header_offset": 100,
        "member_path": member_path,
        "compression_method": 8,
        "compressed_bytes": len(compressed),
        "uncompressed_bytes": 999999,
        "crc32_hex": "00000000",
    }
    config = {
        "range_limits": {
            "maximum_compressed_prefix_bytes": min(4096, len(compressed)),
            "required_decompressed_header_bytes": 256,
            "maximum_local_filename_bytes": 4096,
            "maximum_local_extra_bytes": 65535,
        }
    }
    header, evidence = audit._read_local_member_prefix(
        target=target,
        record=record,
        config=config,
    )
    assert header == _valid_header()
    assert evidence["compression_supported_for_bounded_prefix"] is True
    assert evidence["decompressed_bytes_produced"] == 256
    assert evidence["compressed_prefix_bytes_read"] <= 4096


def test_unsupported_compression_stops_before_member_prefix(monkeypatch) -> None:
    member_path = "A/series1.tvips"
    filename = member_path.encode("utf-8")
    local = struct.pack(
        "<4s5H3I2H",
        b"PK\x03\x04",
        20,
        0x0800,
        12,
        0,
        0,
        0,
        1000,
        2000,
        len(filename),
        0,
    ) + filename
    archive = b"x" * 50 + local + b"payload-that-must-not-be-read"
    calls: list[tuple[int, int]] = []

    def fake_fetch(_url: str, *, start: int, end: int, expected_total: int) -> bytes:
        calls.append((start, end))
        return archive[start : end + 1]

    monkeypatch.setattr(audit.remote, "fetch_range", fake_fetch)
    header, evidence = audit._read_local_member_prefix(
        target={"bytes": len(archive), "content_url": "https://zenodo.org/fake"},
        record={
            "local_header_offset": 50,
            "member_path": member_path,
            "compression_method": 12,
            "compressed_bytes": 1000,
            "uncompressed_bytes": 2000,
            "crc32_hex": "00000000",
        },
        config={
            "range_limits": {
                "maximum_compressed_prefix_bytes": 256,
                "required_decompressed_header_bytes": 256,
                "maximum_local_filename_bytes": 4096,
                "maximum_local_extra_bytes": 65535,
            }
        },
    )
    assert header is None
    assert evidence["compression_supported_for_bounded_prefix"] is False
    assert evidence["compressed_prefix_bytes_read"] == 0
    assert len(calls) == 2


def test_repository_config_remains_fail_closed() -> None:
    config = audit.validate_config(
        json.loads(
            Path("case_studies/zenodo_bir_300kev_saed_header_prefix/case_config.json").read_text(
                encoding="utf-8"
            )
        )
    )
    assert config["range_limits"]["required_decompressed_header_bytes"] == 256
    assert config["scientific_boundary"]["diffraction_pixel_array_decode_authorized"] is False
    assert config["scientific_boundary"]["analyzer_inference_authorized"] is False
    assert config["parser_contract"]["source_repository"] == "hyperspy/rosettasciio"


def test_config_rejects_stronger_boundary() -> None:
    payload = json.loads(
        Path("case_studies/zenodo_bir_300kev_saed_header_prefix/case_config.json").read_text(
            encoding="utf-8"
        )
    )
    payload["scientific_boundary"]["diffraction_pixel_array_decode_authorized"] = True
    with pytest.raises(audit.Bir300TvipsHeaderPrefixError, match="must remain disabled"):
        audit.validate_config(payload)
