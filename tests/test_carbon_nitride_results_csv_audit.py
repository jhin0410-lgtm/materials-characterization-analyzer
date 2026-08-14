from __future__ import annotations

import csv
import io
import json
import zlib
from pathlib import Path

import pytest

from scripts.audit_zenodo_carbon_nitride_results_csv import (
    CarbonNitrideResultsCsvAuditError,
    classify_csv_semantics,
    decompress_selected_member,
    load_json,
    parse_csv,
    parse_local_header,
    validate_config,
)


def _config() -> dict[str, object]:
    return validate_config(
        load_json("case_studies/zenodo_carbon_nitride_tem_results_csv_audit/case_config.json")
    )


def test_tracked_config_authorizes_only_one_csv_member() -> None:
    config = _config()
    boundary = config["scientific_boundary"]
    assert boundary["http_range_member_probe_authorized"] is True
    assert boundary["selected_csv_member_content_authorized"] is True
    assert boundary["source_archive_full_download_authorized"] is False
    assert boundary["other_member_content_authorized"] is False
    assert boundary["image_member_content_authorized"] is False
    assert boundary["pixel_array_access_authorized"] is False
    assert boundary["analyzer_inference_authorized"] is False


def test_selected_member_identity_is_pinned_to_central_directory_metadata() -> None:
    member = _config()["selected_member"]
    assert member == {
        "member_path": "Zenodo/Segmented images/CN-1-Na_20000x/results.csv",
        "local_header_offset": 480651532,
        "compression_method": 8,
        "compressed_bytes": 10881,
        "uncompressed_bytes": 35135,
        "crc32_hex": "62f263da",
    }


def test_encrypted_local_header_is_rejected() -> None:
    # Local header: signature, version, flags(encrypted), method=8, time/date, crc/sizes, name/extra lengths.
    import struct

    header = struct.pack(
        "<IHHHHHIIIHH",
        0x04034B50,
        20,
        1,
        8,
        0,
        0,
        0,
        0,
        0,
        10,
        0,
    )
    with pytest.raises(CarbonNitrideResultsCsvAuditError, match="encrypted"):
        parse_local_header(
            header,
            expected_member=_config()["selected_member"],
            limits=_config()["limits"],
        )


def test_deflated_member_requires_exact_length_and_crc() -> None:
    raw = b"label,area\n1,20\n2,30\n"
    compressor = zlib.compressobj(level=6, wbits=-zlib.MAX_WBITS)
    compressed = compressor.compress(raw) + compressor.flush()
    member = {
        "compression_method": 8,
        "uncompressed_bytes": len(raw),
        "crc32_hex": f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}",
    }
    assert decompress_selected_member(compressed, member=member) == raw

    bad = dict(member)
    bad["crc32_hex"] = "00000000"
    with pytest.raises(CarbonNitrideResultsCsvAuditError, match="CRC32 mismatch"):
        decompress_selected_member(compressed, member=bad)


def test_object_measurement_csv_is_diagnostic_not_ground_truth() -> None:
    text = "label,area,centroid-0,centroid-1,eccentricity\n1,20,2.0,3.0,0.5\n"
    parsed = parse_csv(text.encode(), limits=_config()["limits"])
    assessment = classify_csv_semantics(parsed)

    assert assessment["csv_role_as_segmentation_object_measurement_output"] == "Supported"
    assert assessment["independent_human_annotation_protocol"] == "Inconclusive"
    assert assessment["independent_ground_truth_mask_status"] == "Inconclusive"
    assert assessment["annotation_completeness_across_15_raw_groups"] == "Unsupported"
    assert assessment["co3o4_external_validation_use"] == "Unsupported"


def test_csv_parser_rejects_duplicate_column_names() -> None:
    raw = b"area,area\n1,2\n"
    with pytest.raises(CarbonNitrideResultsCsvAuditError, match="duplicate column"):
        parse_csv(raw, limits=_config()["limits"])


def test_csv_parser_retains_bounded_first_row_without_guessing_units() -> None:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["object", "area_px", "mean_intensity"])
    writer.writerow(["1", "10", "0.2"])
    parsed = parse_csv(output.getvalue().encode(), limits=_config()["limits"])

    assert parsed["columns"] == ["object", "area_px", "mean_intensity"]
    assert parsed["row_count"] == 1
    assert parsed["first_row"] == {
        "object": "1",
        "area_px": "10",
        "mean_intensity": "0.2",
    }
