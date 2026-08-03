from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image

USER_AGENT = "materials-characterization-analyzer-source-audit/1.0"
RESULT = "exact_material_but_rendered_multi_panel_figures_not_validation_data"
EXPECTED_TOP_LEVEL = {
    "case_id",
    "audit_date",
    "source",
    "expected_registry_candidate_id",
    "scientific_boundary",
}
EXPECTED_SOURCE_KEYS = {
    "repository",
    "persistent_id",
    "doi",
    "record_url",
    "api_base",
    "version_number",
    "version_minor_number",
    "version_state",
    "file_license_name",
    "expected_files",
    "tem_containing_figures",
}


class RepodAuditError(RuntimeError):
    """Raised when the public-source contract cannot be verified."""


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if set(payload) != EXPECTED_TOP_LEVEL:
        raise RepodAuditError("unexpected top-level config keys")
    if set(payload["source"]) != EXPECTED_SOURCE_KEYS:
        raise RepodAuditError("unexpected source config keys")
    return payload


def _fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def _download(url: str, destination: Path, expected_bytes: int, expected_md5: str) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.md5()
    observed_bytes = 0
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as handle:
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)
            digest.update(chunk)
            observed_bytes += len(chunk)
    if observed_bytes != expected_bytes:
        raise RepodAuditError(
            f"download byte mismatch for {destination.name}: {observed_bytes} != {expected_bytes}"
        )
    if digest.hexdigest() != expected_md5:
        raise RepodAuditError(f"download MD5 mismatch for {destination.name}")


def _normalize_inventory(latest: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in latest.get("files", []):
        data_file = item.get("dataFile") or {}
        checksum = data_file.get("checksum") or {}
        rows.append(
            {
                "id": data_file.get("id"),
                "name": data_file.get("filename"),
                "bytes": data_file.get("filesize"),
                "md5": checksum.get("value"),
                "checksum_type": checksum.get("type"),
                "content_type": data_file.get("contentType"),
                "description": item.get("description") or "",
                "restricted": item.get("restricted"),
                "license_name": item.get("licenseName"),
            }
        )
    return sorted(rows, key=lambda row: str(row["name"]))


def _verify_inventory(config: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("status") != "OK":
        raise RepodAuditError("Dataverse API status is not OK")
    latest = payload.get("data", {}).get("latestVersion")
    if not isinstance(latest, dict):
        raise RepodAuditError("latestVersion is missing")
    source = config["source"]
    if latest.get("versionNumber") != source["version_number"]:
        raise RepodAuditError("major version mismatch")
    if latest.get("versionMinorNumber") != source["version_minor_number"]:
        raise RepodAuditError("minor version mismatch")
    if latest.get("versionState") != source["version_state"]:
        raise RepodAuditError("version state mismatch")

    observed = _normalize_inventory(latest)
    expected = sorted(source["expected_files"], key=lambda row: row["name"])
    if len(observed) != len(expected):
        raise RepodAuditError("file-count mismatch")
    for expected_row, observed_row in zip(expected, observed, strict=True):
        for key in ("id", "name", "bytes", "md5", "content_type"):
            if observed_row[key] != expected_row[key]:
                raise RepodAuditError(
                    f"inventory mismatch for {expected_row['name']} field {key}"
                )
        if observed_row["checksum_type"] != "MD5":
            raise RepodAuditError("unsupported checksum type")
        if observed_row["restricted"] is not False:
            raise RepodAuditError("expected a public file")
        if observed_row["license_name"] != source["file_license_name"]:
            raise RepodAuditError("file licence mismatch")
    return observed


def _inspect_figure(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        return {
            "name": path.name,
            "format": image.format,
            "mode": image.mode,
            "size": [image.width, image.height],
            "frames": getattr(image, "n_frames", 1),
            "dpi": list(image.info.get("dpi", ())),
            "progressive": bool(
                image.info.get("progressive") or image.info.get("progression")
            ),
            "exif_bytes": len(image.info.get("exif", b"")),
            "icc_profile_bytes": len(image.info.get("icc_profile", b"")),
        }


def _verify_figure(
    expected: dict[str, Any], observed: dict[str, Any], description: str
) -> None:
    for key in ("image_format", "mode", "size", "frames", "dpi"):
        observed_key = "format" if key == "image_format" else key
        if observed[observed_key] != expected[key]:
            raise RepodAuditError(f"image representation mismatch for {expected['name']}: {key}")
    for phrase in expected["description_contains"]:
        if phrase not in description:
            raise RepodAuditError(
                f"official description changed for {expected['name']}: {phrase}"
            )


def _verify_registry(output: Path, candidate_id: str) -> None:
    inventory = output / "tem_external_validation_candidate_inventory.csv"
    if not inventory.is_file():
        raise RepodAuditError("registry inventory is missing")
    with inventory.open(encoding="utf-8", newline="") as handle:
        rows = {row["candidate_id"]: row for row in csv.DictReader(handle)}
    candidate = rows.get(candidate_id)
    if candidate is None:
        raise RepodAuditError("RepOD candidate is missing from registry")
    if candidate["candidate_status"] != "excluded_rendered_figure_representation":
        raise RepodAuditError("RepOD candidate status mismatch")
    if candidate["raw_or_lossless_tem_images_available"] != "False":
        raise RepodAuditError("registry incorrectly marks raw/lossless TEM available")
    if candidate["evaluation_ready"] != "False":
        raise RepodAuditError("registry incorrectly marks candidate evaluation-ready")


def _write_manifest(output: Path, artifact_names: list[str]) -> None:
    artifacts = []
    for name in artifact_names:
        path = output / name
        blob = path.read_bytes()
        artifacts.append(
            {"path": name, "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
        )
    (output / "repod_co3o4_tem_figure_audit_manifest.json").write_text(
        json.dumps(
            {"schema_version": "1.0", "artifact_count": len(artifacts), "artifacts": artifacts},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def run(config_path: Path, output: Path, registry_output: Path | None = None) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("output directory must be absent or empty")
    output.mkdir(parents=True, exist_ok=True)
    transient = output / "_transient"
    transient.mkdir()
    succeeded = False
    try:
        config = load_config(config_path)
        source = config["source"]
        metadata_url = (
            f"{source['api_base']}/api/datasets/:persistentId/?"
            + urllib.parse.urlencode({"persistentId": source["persistent_id"]})
        )
        payload = _fetch_json(metadata_url)
        inventory = _verify_inventory(config, payload)
        by_name = {row["name"]: row for row in inventory}

        inspected: list[dict[str, Any]] = []
        for expected in source["tem_containing_figures"]:
            row = by_name[expected["name"]]
            path = transient / expected["name"]
            _download(
                f"{source['api_base']}/api/access/datafile/{row['id']}",
                path,
                row["bytes"],
                row["md5"],
            )
            image = _inspect_figure(path)
            _verify_figure(expected, image, row["description"])
            inspected.append({**row, **image, "composite_publication_figure": True})

        if registry_output is not None:
            _verify_registry(registry_output, config["expected_registry_candidate_id"])

        summary = {
            "schema_version": "1.0",
            "case_id": config["case_id"],
            "result": RESULT,
            "record_file_count": len(inventory),
            "tem_containing_figure_count": len(inspected),
            "individual_tem_micrograph_count": 0,
            "raw_or_lossless_tem_images_available": False,
            "all_tem_content_is_inside_composite_jpeg_figures": True,
            "source_figures_retained": False,
            "panel_cropping_performed": False,
            "model_inference_performed": False,
            "annotation_performed": False,
            "external_validation_ready": False,
            "inspected_figures": inspected,
            "scientific_closeout": {
                "status": "Supported",
                "strongest_evidence": "Official descriptions identify multi-panel publication figures, and checksum-bound files decode as single-frame RGB JPEGs.",
                "primary_limitation": "Individual detector or demonstrably lossless TEM micrographs and acquisition lineage were not deposited.",
                "not_suitable_for": [
                    "segmentation annotation",
                    "model inference",
                    "model retraining",
                    "external performance claims",
                ],
            },
        }
        inventory_payload = {
            "schema_version": "1.0",
            "case_id": config["case_id"],
            "repository": source["repository"],
            "doi": source["doi"],
            "version": [source["version_number"], source["version_minor_number"]],
            "file_license_name": source["file_license_name"],
            "files": inventory,
        }
        (output / "official_source_inventory.json").write_text(
            json.dumps(inventory_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (output / "repod_co3o4_tem_figure_audit_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        report = (
            "# RepOD Co3O4 TEM Figure Audit\n\n"
            f"- Result: `{RESULT}`\n"
            f"- Official files: {len(inventory)}\n"
            f"- TEM-containing composite JPEG figures: {len(inspected)}\n"
            "- Individual raw/lossless TEM micrographs: 0\n"
            "- External validation ready: false\n\n"
            "The deposited TEM content is embedded in multi-panel RGB JPEG publication figures. "
            "No panel cropping, annotation, inference or performance evaluation was performed.\n"
        )
        (output / "repod_co3o4_tem_figure_audit_report.md").write_text(
            report, encoding="utf-8"
        )
        _write_manifest(
            output,
            [
                "official_source_inventory.json",
                "repod_co3o4_tem_figure_audit_summary.json",
                "repod_co3o4_tem_figure_audit_report.md",
            ],
        )
        succeeded = True
        return summary
    finally:
        shutil.rmtree(transient, ignore_errors=True)
        if not succeeded and output.exists():
            shutil.rmtree(output, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--registry-output", type=Path)
    args = parser.parse_args()
    summary = run(args.config, args.output, args.registry_output)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
