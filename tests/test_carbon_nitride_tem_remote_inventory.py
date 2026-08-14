from __future__ import annotations

from pathlib import Path

from scripts.audit_zenodo_carbon_nitride_tem_remote_inventory import (
    _scientific_assessment,
    enrich_records,
    load_json,
    resolve_target,
    summarize_inventory,
    validate_config,
)


def _record(path: str, *, directory: bool = False) -> dict[str, object]:
    return {
        "member_path": path,
        "compressed_bytes": 10,
        "uncompressed_bytes": 20,
        "compression_method": 8,
        "crc32_hex": "00000000",
        "local_header_offset": 0,
        "unsafe_path": False,
        "is_directory": directory,
        "is_tvips": False,
        "tvips_split_prefix": None,
        "tvips_split_index": None,
        "is_tvips_split_main_file": False,
    }


def test_tracked_config_authorizes_only_central_directory_metadata() -> None:
    config = validate_config(
        load_json("case_studies/zenodo_carbon_nitride_tem_remote_inventory/case_config.json")
    )
    boundary = config["scientific_boundary"]
    assert boundary["http_range_metadata_probe_authorized"] is True
    assert boundary["central_directory_inventory_authorized"] is True
    assert boundary["source_archive_full_download_authorized"] is False
    assert boundary["member_file_content_download_authorized"] is False
    assert boundary["member_extraction_authorized"] is False
    assert boundary["pixel_array_access_authorized"] is False
    assert boundary["analyzer_inference_authorized"] is False


def test_tracked_metadata_snapshot_resolves_exact_archive() -> None:
    config_path = Path(
        "case_studies/zenodo_carbon_nitride_tem_remote_inventory/case_config.json"
    ).resolve()
    config = validate_config(load_json(config_path))
    source_path = (config_path.parent / config["source_snapshot"]).resolve(strict=True)
    target = resolve_target(config, load_json(source_path))

    assert target["key"] == "Whole dataset.zip"
    assert target["bytes"] == 561160882
    assert target["md5"] == "b608d86084ccbbea802ff54c3f98380e"
    assert target["content_url"].startswith("https://zenodo.org/")


def test_member_names_are_retained_as_path_cues_not_identity_truth() -> None:
    records = enrich_records(
        [
            _record("Dataset/Raw TEM/sample_01/image_001.tif"),
            _record("Dataset/Segmented/sample_01/mask_001.tif"),
            _record("Dataset/Annotated/sample_01/label_001.png"),
        ]
    )
    summary = summarize_inventory(records, central_sha256="a" * 64)
    assessment = _scientific_assessment(summary)

    assert summary["raw_path_cue_count"] == 1
    assert summary["segmentation_path_cue_count"] == 1
    assert summary["annotation_path_cue_count"] == 1
    assert assessment["raw_vs_annotation_path_separation"] == "Diagnostic"
    assert assessment["immutable_sample_identity"] == "Inconclusive"
    assert assessment["immutable_acquisition_identity"] == "Inconclusive"
    assert assessment["annotation_provenance"] == "Inconclusive"
    assert assessment["annotation_completeness"] == "Inconclusive"


def test_cross_material_inventory_never_becomes_co3o4_validation() -> None:
    records = enrich_records([_record("Raw TEM/image.tif")])
    summary = summarize_inventory(records, central_sha256="b" * 64)
    assessment = _scientific_assessment(summary)

    assert assessment["co3o4_domain_match"] == "Unsupported"
    assert assessment["external_validation_ready"] == "Unsupported"
    assert assessment["scientific_evidence_level"] == "Diagnostic"
