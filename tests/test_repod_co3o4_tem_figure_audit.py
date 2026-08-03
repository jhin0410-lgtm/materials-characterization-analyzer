from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "case_studies" / "repod_co3o4_tem_figure_audit" / "case_config.json"
SCRIPT = ROOT / "scripts" / "audit_repod_co3o4_tem_figures.py"
SPEC = importlib.util.spec_from_file_location("repod_audit", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
repod_audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(repod_audit)


def _jpeg(size: tuple[int, int], dpi: tuple[int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (127, 127, 127)).save(buffer, format="JPEG", dpi=dpi)
    return buffer.getvalue()


def _fixture(tmp_path: Path) -> tuple[Path, dict, dict[str, bytes]]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    blobs = {
        "Figure_2.jpg": _jpeg((1430, 1117), (220, 220)),
        "Figure_6.jpg": _jpeg((925, 614), (144, 144)),
    }
    expected_by_name = {row["name"]: row for row in config["source"]["expected_files"]}
    for name, blob in blobs.items():
        expected_by_name[name]["bytes"] = len(blob)
        expected_by_name[name]["md5"] = hashlib.md5(blob).hexdigest()

    figure_contract = {
        row["name"]: row for row in config["source"]["tem_containing_figures"]
    }
    files = []
    for expected in config["source"]["expected_files"]:
        description = "non-TEM publication figure"
        if expected["name"] in figure_contract:
            description = " | ".join(figure_contract[expected["name"]]["description_contains"])
        files.append(
            {
                "restricted": False,
                "licenseName": config["source"]["file_license_name"],
                "description": description,
                "dataFile": {
                    "id": expected["id"],
                    "filename": expected["name"],
                    "filesize": expected["bytes"],
                    "contentType": expected["content_type"],
                    "checksum": {"type": "MD5", "value": expected["md5"]},
                },
            }
        )
    payload = {
        "status": "OK",
        "data": {
            "latestVersion": {
                "versionNumber": 1,
                "versionMinorNumber": 0,
                "versionState": "RELEASED",
                "files": files,
            }
        },
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path, payload, blobs


def _patch_live(monkeypatch: pytest.MonkeyPatch, payload: dict, blobs: dict[str, bytes]) -> None:
    monkeypatch.setattr(repod_audit, "_fetch_json", lambda _url: payload)

    def fake_download(_url: str, destination: Path, expected_bytes: int, expected_md5: str) -> None:
        blob = blobs[destination.name]
        assert len(blob) == expected_bytes
        assert hashlib.md5(blob).hexdigest() == expected_md5
        destination.write_bytes(blob)

    monkeypatch.setattr(repod_audit, "_download", fake_download)


def _registry_output(tmp_path: Path) -> Path:
    output = tmp_path / "registry"
    output.mkdir()
    with (output / "tem_external_validation_candidate_inventory.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "candidate_id",
                "candidate_status",
                "raw_or_lossless_tem_images_available",
                "evaluation_ready",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "candidate_id": "repod_sau9qx_co3o4_rendered_tem_figures",
                "candidate_status": "excluded_rendered_or_non_raw_representation",
                "raw_or_lossless_tem_images_available": "False",
                "evaluation_ready": "False",
            }
        )
    return output


def test_snapshot_audit_records_rendered_figures_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, payload, blobs = _fixture(tmp_path)
    _patch_live(monkeypatch, payload, blobs)
    output = tmp_path / "out"
    summary = repod_audit.run(config, output, _registry_output(tmp_path))

    assert summary["result"] == repod_audit.RESULT
    assert summary["record_file_count"] == 6
    assert summary["tem_containing_figure_count"] == 2
    assert summary["individual_tem_micrograph_count"] == 0
    assert summary["all_tem_content_is_inside_composite_jpeg_figures"]
    assert not summary["raw_or_lossless_tem_images_available"]
    assert not summary["external_validation_ready"]
    assert not (output / "_transient").exists()
    assert not list(output.glob("*.jpg"))


def test_inventory_change_fails_closed_and_cleans_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, payload, blobs = _fixture(tmp_path)
    payload["data"]["latestVersion"]["files"][0]["dataFile"]["filesize"] += 1
    _patch_live(monkeypatch, payload, blobs)
    output = tmp_path / "out"
    with pytest.raises(repod_audit.RepodAuditError, match="inventory mismatch"):
        repod_audit.run(config, output)
    assert not output.exists()


def test_image_representation_change_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, payload, blobs = _fixture(tmp_path)
    blobs["Figure_2.jpg"] = _jpeg((1200, 900), (220, 220))
    expected = next(
        row
        for row in json.loads(config.read_text())["source"]["expected_files"]
        if row["name"] == "Figure_2.jpg"
    )
    expected["bytes"] = len(blobs["Figure_2.jpg"])
    expected["md5"] = hashlib.md5(blobs["Figure_2.jpg"]).hexdigest()
    rewritten = json.loads(config.read_text())
    row = next(item for item in rewritten["source"]["expected_files"] if item["name"] == "Figure_2.jpg")
    row.update(bytes=expected["bytes"], md5=expected["md5"])
    config.write_text(json.dumps(rewritten), encoding="utf-8")
    file_row = next(item for item in payload["data"]["latestVersion"]["files"] if item["dataFile"]["filename"] == "Figure_2.jpg")
    file_row["dataFile"]["filesize"] = expected["bytes"]
    file_row["dataFile"]["checksum"]["value"] = expected["md5"]
    _patch_live(monkeypatch, payload, blobs)
    with pytest.raises(repod_audit.RepodAuditError, match="image representation mismatch"):
        repod_audit.run(config, tmp_path / "out")


def test_description_change_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, payload, blobs = _fixture(tmp_path)
    figure = next(
        row
        for row in payload["data"]["latestVersion"]["files"]
        if row["dataFile"]["filename"] == "Figure_6.jpg"
    )
    figure["description"] = "Figure 6 without panel provenance"
    _patch_live(monkeypatch, payload, blobs)
    with pytest.raises(repod_audit.RepodAuditError, match="official description changed"):
        repod_audit.run(config, tmp_path / "out")


def test_output_overwrite_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, payload, blobs = _fixture(tmp_path)
    _patch_live(monkeypatch, payload, blobs)
    output = tmp_path / "out"
    repod_audit.run(config, output)
    with pytest.raises(FileExistsError, match="absent or empty"):
        repod_audit.run(config, output)


def test_unknown_config_key_is_rejected(tmp_path: Path) -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["invented"] = True
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(repod_audit.RepodAuditError, match="top-level"):
        repod_audit.load_config(path)
