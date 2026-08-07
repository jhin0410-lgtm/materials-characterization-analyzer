from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from scripts import audit_zenodo_srtio3_saed_tiff_metadata as audit


def _config() -> dict:
    return audit._validate_config(
        json.loads(
            Path("case_studies/zenodo_srtio3_saed_tiff_metadata/case_config.json").read_text(
                encoding="utf-8"
            )
        )
    )


def _little_tiff(*, first_ifd_offset: int = 8) -> bytes:
    header = b"II" + struct.pack("<H", 42) + struct.pack("<I", first_ifd_offset)
    if first_ifd_offset != 8:
        return header + b"\x00" * 128
    entries = [
        (256, 4, 1, 4096),  # ImageWidth LONG
        (257, 4, 1, 4096),  # ImageLength LONG
        (258, 3, 1, 16),    # BitsPerSample SHORT
        (259, 3, 1, 1),     # TIFF Compression = none
        (262, 3, 1, 1),     # BlackIsZero
        (270, 2, 20, 512),  # ImageDescription out of line; must not be followed
        (273, 4, 1, 272),   # StripOffsets inline (metadata only, do not follow)
        (277, 3, 1, 1),     # SamplesPerPixel
        (278, 4, 1, 4096),  # RowsPerStrip
        (279, 4, 1, 33554432),
        (339, 3, 1, 1),     # unsigned integer sample format
    ]
    body = struct.pack("<H", len(entries))
    for tag, type_id, count, value in entries:
        if type_id == 3 and count == 1:
            raw_value = struct.pack("<H", value) + b"\x00\x00"
        else:
            raw_value = struct.pack("<I", value)
        body += struct.pack("<HHI", tag, type_id, count) + raw_value
    body += struct.pack("<I", 0)
    return header + body


def test_parse_first_ifd_supports_inline_dimensions_without_following_offsets() -> None:
    config = _config()
    payload = _little_tiff()
    parsed = audit._parse_tiff_ifd(payload, config)
    tags = parsed["recorded_tags"]
    assert tags["ImageWidth"]["value"] == 4096
    assert tags["ImageLength"]["value"] == 4096
    assert tags["BitsPerSample"]["value"] == 16
    assert tags["SamplesPerPixel"]["value"] == 1
    assert tags["SampleFormat"]["value"] == 1
    assert tags["ImageDescription"]["storage"] == "out_of_line"
    assert tags["ImageDescription"]["value"] is None
    assert tags["ImageDescription"]["value_offset_if_out_of_line"] == 512
    assert tags["ImageDescription"]["out_of_line_value_followed"] is False
    assert parsed["page_count_evidence"]["page_count_if_supported"] == 1
    assert parsed["out_of_line_values_followed"] is False


def test_required_ifd_bytes_decompresses_only_exact_metadata_extent() -> None:
    config = _config()
    payload = _little_tiff() + b"\x7f" * 10000
    metadata, evidence = audit._required_ifd_bytes(
        payload,
        compression=0,
        config=config,
    )
    expected = 8 + 2 + 11 * 12 + 4
    assert len(metadata) == expected
    assert evidence["maximum_metadata_prefix_bytes_decompressed"] == expected
    assert evidence["pixel_array_decoded"] is False


def test_non_immediate_first_ifd_is_rejected_before_broader_decompression() -> None:
    config = _config()
    with pytest.raises(audit.SrTiO3SaedTiffMetadataError, match="immediately after"):
        audit._required_ifd_bytes(
            _little_tiff(first_ifd_offset=1024),
            compression=0,
            config=config,
        )


def test_out_of_line_values_are_never_followed() -> None:
    config = _config()
    parsed = audit._parse_tiff_ifd(_little_tiff(), config)
    description = parsed["recorded_tags"]["ImageDescription"]
    assert description["storage"] == "out_of_line"
    assert description["value"] is None
    assert description["out_of_line_value_followed"] is False


def test_config_prohibits_pixel_and_four_d_stem_access() -> None:
    config = _config()
    boundary = config["scientific_boundary"]
    assert boundary["pixel_array_decode_authorized"] is False
    assert boundary["follow_out_of_line_ifd_values_authorized"] is False
    assert boundary["four_d_stem_download_authorized"] is False
    assert boundary["full_member_download_authorized"] is False
    assert boundary["full_archive_download_authorized"] is False


def test_config_rejects_pixel_authorization() -> None:
    payload = json.loads(
        Path("case_studies/zenodo_srtio3_saed_tiff_metadata/case_config.json").read_text(
            encoding="utf-8"
        )
    )
    payload["scientific_boundary"]["pixel_array_decode_authorized"] = True
    with pytest.raises(audit.SrTiO3SaedTiffMetadataError, match="stronger TIFF/source/analyzer"):
        audit._validate_config(payload)
