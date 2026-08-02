from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from mca.saed_bir_metadata_audit import (
    BIRMetadataContractError,
    RESULT,
    audit_bir_metadata,
    cli_main,
    load_config,
    load_record,
)


def _config_payload() -> dict:
    return {
        "case_id": "saed_bir_200kev_metadata_audit",
        "search_date": "2026-08-03",
        "source": {
            "record_id": "10999587",
            "doi": "10.5281/zenodo.10999587",
            "record_url": "https://zenodo.org/records/10999587",
            "title": (
                "BIR-MicroED: selected area electron diffraction datasets from "
                "static microcrystals (AVAAGA, thiostrepton, proteinase K) at 200 keV"
            ),
            "publication_doi": "10.1107/S2052252524012132",
            "expected_files": [
                {
                    "name": "AVAAGA_200kV_100K.zip",
                    "md5": "5550d6e7fa1db57c70dcc35ade92135e",
                    "material_group": "AVAAGA",
                    "temperature_k": 100,
                },
                {
                    "name": "AVAAGA_200kV_293K.zip",
                    "md5": "f800d8b28b1b93f074b8a1d7c19dc930",
                    "material_group": "AVAAGA",
                    "temperature_k": 293,
                },
                {
                    "name": "proK_200kV_100K.zip",
                    "md5": "c172f50d6c4d9db984354e84b64d36fe",
                    "material_group": "proteinase K",
                    "temperature_k": 100,
                },
                {
                    "name": "thiostrepton_200kV_100K.zip",
                    "md5": "2094a5a07d233fe0f6c04f6955e97009",
                    "material_group": "thiostrepton",
                    "temperature_k": 100,
                },
            ],
        },
        "publication_evidence": {
            "microscope": "Talos F200C",
            "detector": "DE Apollo direct electron detector",
            "detector_native_frame_rate_hz": 60,
            "integrated_native_frames_per_output": 30,
            "output_frame_rate_hz": 2.0,
            "output_shape": [2048, 2048],
            "output_format": "MRC",
            "stage_rotation_during_stationary_series": False,
            "selected_area_aperture_um": 100,
            "projected_selected_area_diameter_um": 2.0,
            "illuminated_area_diameter_um": 5.0,
            "small_molecule_duration_s": 300,
            "macromolecule_duration_s": 150,
            "source_preprocessing": [
                "native_frame_integration",
                "spatial_binning",
            ],
        },
        "readiness_contract": {
            "minimum_independent_series": 2,
            "require_raw_or_demonstrably_lossless": True,
            "require_immutable_sample_ids": True,
            "require_immutable_acquisition_ids": True,
            "require_traceable_pattern_center": True,
            "require_traceable_reciprocal_calibration": True,
            "require_explicit_reuse_terms": True,
            "require_analyzer_development_nonuse": True,
        },
    }


def _record_payload(*, rights: list | None = None) -> dict:
    config = _config_payload()
    sizes = {
        "AVAAGA_200kV_100K.zip": 15_300_000_000,
        "AVAAGA_200kV_293K.zip": 2_200_000_000,
        "proK_200kV_100K.zip": 6_100_000_000,
        "thiostrepton_200kV_100K.zip": 13_300_000_000,
    }
    return {
        "id": "10999587",
        "created": "2024-04-19T00:00:00+00:00",
        "updated": "2024-04-19T00:00:00+00:00",
        "pids": {
            "doi": {
                "identifier": "10.5281/zenodo.10999587",
                "provider": "datacite",
            }
        },
        "metadata": {
            "title": config["source"]["title"],
            "rights": [] if rights is None else rights,
        },
        "files": {
            "enabled": True,
            "entries": {
                item["name"]: {
                    "key": item["name"],
                    "size": sizes[item["name"]],
                    "checksum": f"md5:{item['md5']}",
                    "mimetype": "application/zip",
                    "links": {
                        "content": (
                            "https://zenodo.org/api/records/10999587/files/"
                            f"{item['name']}/content?token=do-not-persist"
                        )
                    },
                }
                for item in config["source"]["expected_files"]
            },
        },
    }


def _write_inputs(
    tmp_path: Path,
    *,
    config: dict | None = None,
    record: dict | None = None,
) -> tuple[Path, Path]:
    config_path = tmp_path / "config.json"
    record_path = tmp_path / "record.json"
    config_path.write_text(
        json.dumps(_config_payload() if config is None else config),
        encoding="utf-8",
    )
    record_path.write_text(
        json.dumps(_record_payload() if record is None else record),
        encoding="utf-8",
    )
    return config_path, record_path


def test_pinned_metadata_audit_fails_closed(tmp_path: Path) -> None:
    config_path, record_path = _write_inputs(tmp_path)
    output = tmp_path / "out"
    summary = audit_bir_metadata(
        load_config(config_path),
        load_record(record_path),
        output,
    )
    assert summary["result"] == RESULT
    assert summary["source"]["archive_count"] == 4
    assert summary["source"]["total_archive_bytes"] == 36_900_000_000
    assert summary["publication_evidence"]["microscope"] == "Talos F200C"
    assert summary["publication_evidence"]["detector_native_frame_rate_hz"] == 60
    assert summary["publication_evidence"]["integrated_native_frames_per_output"] == 30
    assert summary["publication_evidence"]["output_shape"] == [2048, 2048]
    gates = summary["evidence_gates"]
    assert gates["record_identity_verified"]
    assert gates["archive_level_md5_values_verified"]
    assert gates["static_selected_area_acquisition_supported_by_publication"]
    assert not gates["native_detector_frames_released"]
    assert not gates["released_representation_is_demonstrably_lossless_to_native_frames"]
    assert not gates["ready_for_bounded_archive_download"]
    assert not gates["ready_for_saed_validation_intake"]
    assert not gates["ready_for_predeclared_external_evaluation"]


def test_smallest_archive_is_selected_without_authorizing_download(
    tmp_path: Path,
) -> None:
    config_path, record_path = _write_inputs(tmp_path)
    output = tmp_path / "out"
    audit_bir_metadata(load_config(config_path), load_record(record_path), output)
    plan = json.loads(
        (output / "bir_bounded_subset_plan.json").read_text(encoding="utf-8")
    )
    assert plan["selected_archive"] == "AVAAGA_200kV_293K.zip"
    assert plan["selected_archive_bytes"] == 2_200_000_000
    assert plan["download_authorized_now"] is False
    assert plan["full_record_download_prohibited"] is True
    assert plan["minimum_independent_series"] == 2


def test_inventory_preserves_official_archive_md5_values(tmp_path: Path) -> None:
    config_path, record_path = _write_inputs(tmp_path)
    output = tmp_path / "out"
    audit_bir_metadata(load_config(config_path), load_record(record_path), output)
    with (output / "bir_archive_inventory.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = {row["name"]: row for row in csv.DictReader(handle)}
    assert rows["AVAAGA_200kV_100K.zip"]["md5"] == (
        "5550d6e7fa1db57c70dcc35ade92135e"
    )
    assert rows["AVAAGA_200kV_293K.zip"]["bounded_subset_selected"] == "True"
    assert all(
        row["archive_member_count_verified"] == "False"
        for row in rows.values()
    )


def test_raw_record_links_and_tokens_are_not_persisted(tmp_path: Path) -> None:
    config_path, record_path = _write_inputs(tmp_path)
    output = tmp_path / "out"
    audit_bir_metadata(load_config(config_path), load_record(record_path), output)
    persisted = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output.iterdir()
        if path.is_file()
    )
    assert "do-not-persist" not in persisted
    assert "/files/" not in persisted
    assert "links" not in persisted


def test_manifest_binds_outputs_to_canonical_record_metadata(tmp_path: Path) -> None:
    config_path, record_path = _write_inputs(tmp_path)
    record = load_record(record_path)
    output = tmp_path / "out"
    audit_bir_metadata(load_config(config_path), record, output)
    expected_record_sha = hashlib.sha256(
        (
            json.dumps(
                record,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()
    manifest = json.loads(
        (output / "bir_metadata_audit_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["record_metadata_sha256"] == expected_record_sha
    assert manifest["artifact_count"] == 6
    for item in manifest["artifacts"]:
        path = output / item["path"]
        assert item["bytes"] == path.stat().st_size
        assert item["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_explicit_rights_do_not_bypass_calibration_and_lineage_gates(
    tmp_path: Path,
) -> None:
    config_path, record_path = _write_inputs(
        tmp_path,
        record=_record_payload(rights=[{"id": "cc-by-4.0"}]),
    )
    summary = audit_bir_metadata(
        load_config(config_path), load_record(record_path), tmp_path / "out"
    )
    assert summary["evidence_gates"]["explicit_reuse_terms_verified"]
    assert not summary["evidence_gates"]["ready_for_bounded_archive_download"]
    assert "pattern_center_not_traceable" in summary["blockers"]
    assert "reciprocal_calibration_not_traceable" in summary["blockers"]
    assert "reuse terms" not in summary["scientific_closeout"]["primary_limitation"]
    request = (tmp_path / "out" / "bir_author_metadata_request.md").read_text(
        encoding="utf-8"
    )
    assert "Provide explicit data reuse terms" not in request
    plan = json.loads(
        (tmp_path / "out" / "bir_bounded_subset_plan.json").read_text(
            encoding="utf-8"
        )
    )
    assert "reuse terms" not in plan["selection_basis"]


def test_legacy_zenodo_file_list_schema_is_supported(tmp_path: Path) -> None:
    record = _record_payload()
    record["files"] = [
        {
            "filename": item["key"],
            "filesize": item["size"],
            "checksum": item["checksum"],
            "type": item["mimetype"],
        }
        for item in record["files"]["entries"].values()
    ]
    config_path, record_path = _write_inputs(tmp_path, record=record)
    summary = audit_bir_metadata(
        load_config(config_path), load_record(record_path), tmp_path / "out"
    )
    assert summary["source"]["archive_count"] == 4


def test_wrong_archive_checksum_fails_closed(tmp_path: Path) -> None:
    record = _record_payload()
    record["files"]["entries"]["AVAAGA_200kV_293K.zip"]["checksum"] = (
        "md5:00000000000000000000000000000000"
    )
    config_path, record_path = _write_inputs(tmp_path, record=record)
    with pytest.raises(BIRMetadataContractError, match="MD5 mismatch"):
        audit_bir_metadata(
            load_config(config_path), load_record(record_path), tmp_path / "out"
        )
    assert not (tmp_path / "out").exists()


def test_unexpected_record_file_fails_closed(tmp_path: Path) -> None:
    record = _record_payload()
    record["files"]["entries"]["unexpected.zip"] = {
        "key": "unexpected.zip",
        "size": 100,
        "checksum": "md5:11111111111111111111111111111111",
    }
    config_path, record_path = _write_inputs(tmp_path, record=record)
    with pytest.raises(BIRMetadataContractError, match="inventory mismatch"):
        audit_bir_metadata(
            load_config(config_path), load_record(record_path), tmp_path / "out"
        )


def test_unknown_config_field_fails_closed(tmp_path: Path) -> None:
    payload = _config_payload()
    payload["source"]["invented"] = True
    config_path, _ = _write_inputs(tmp_path, config=payload)
    with pytest.raises(BIRMetadataContractError, match="unknown source field"):
        load_config(config_path)


def test_duplicate_record_key_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    path.write_text('{"id":"10999587","id":"other"}', encoding="utf-8")
    with pytest.raises(BIRMetadataContractError, match="duplicate JSON"):
        load_record(path)


def test_output_overwrite_is_refused(tmp_path: Path) -> None:
    config_path, record_path = _write_inputs(tmp_path)
    config = load_config(config_path)
    record = load_record(record_path)
    output = tmp_path / "out"
    audit_bir_metadata(config, record, output)
    with pytest.raises(FileExistsError, match="absent or empty"):
        audit_bir_metadata(config, record, output)


def test_transactional_cleanup_on_late_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mca.saed_bir_metadata_audit as audit

    config_path, record_path = _write_inputs(tmp_path)
    original = audit._write_json
    calls = 0

    def fail_second(path: Path, payload: dict) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated late failure")
        original(path, payload)

    monkeypatch.setattr(audit, "_write_json", fail_second)
    output = tmp_path / "out"
    with pytest.raises(OSError, match="late failure"):
        audit_bir_metadata(
            load_config(config_path), load_record(record_path), output
        )
    assert not output.exists()


def test_cli_writes_metadata_only_outputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path, record_path = _write_inputs(tmp_path)
    output = tmp_path / "cli-out"
    assert (
        cli_main(
            [
                "--config",
                str(config_path),
                "--record-json",
                str(record_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    printed = json.loads(capsys.readouterr().out)
    assert printed["result"] == RESULT
    assert printed["archive_count"] == 4
    assert printed["ready_for_bounded_archive_download"] is False
    assert not any(
        path.suffix.lower() in {".zip", ".mrc", ".tif", ".tiff", ".tvips"}
        for path in output.rglob("*")
    )
