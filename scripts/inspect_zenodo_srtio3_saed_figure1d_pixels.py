from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PIXEL_OFFSET = 272
PREVIEW_SIZE = 512


class SrTiO3FigurePixelInventoryError(RuntimeError):
    """Raised when the predeclared Figure 1d pixel-access contract is violated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SrTiO3FigurePixelInventoryError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise SrTiO3FigurePixelInventoryError(f"invalid JSON: {resolved}") from exc
    if not isinstance(payload, dict):
        raise SrTiO3FigurePixelInventoryError(f"JSON root must be an object: {resolved}")
    return payload


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _md5_bytes(payload: bytes) -> str:
    return hashlib.md5(payload, usedforsecurity=False).hexdigest()


def _resolve_repo_path(value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise SrTiO3FigurePixelInventoryError("evidence path must be a non-empty string")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise SrTiO3FigurePixelInventoryError("configured evidence path is unsafe")
    resolved = (PROJECT_ROOT / candidate).resolve(strict=True)
    if PROJECT_ROOT not in resolved.parents:
        raise SrTiO3FigurePixelInventoryError("evidence path resolved outside project root")
    return resolved


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "case_id",
        "predeclared_at",
        "objective",
        "source_archive",
        "authorized_source_members",
        "publication_figure",
        "evidence_inputs",
        "authorized_operations",
        "decision_rules",
        "expected_closeout_states",
    }
    if set(config) != required or config.get("schema_version") != "1.0":
        raise SrTiO3FigurePixelInventoryError("Figure 1d contract keys/schema mismatch")

    archive = config.get("source_archive")
    if not isinstance(archive, dict):
        raise SrTiO3FigurePixelInventoryError("source_archive must be an object")
    expected_archive = {
        "doi": "10.5281/zenodo.20300700",
        "key": "SAED.zip",
        "content_url": "https://zenodo.org/api/records/20300700/files/SAED.zip/content",
        "bytes": 25850906,
        "md5": "0c830a9b276a491e91037872891cb440",
        "maximum_download_bytes": 30000000,
    }
    if archive != expected_archive:
        raise SrTiO3FigurePixelInventoryError("source_archive drifted from predeclared identity")

    members = config.get("authorized_source_members")
    if not isinstance(members, list) or len(members) != 3:
        raise SrTiO3FigurePixelInventoryError("exactly three source TIFFs must be authorized")
    expected = {
        "SAED/23K.tif": 23,
        "SAED/91K.tif": 91,
        "SAED/172K.tif": 172,
    }
    observed: dict[str, int] = {}
    for member in members:
        if not isinstance(member, dict):
            raise SrTiO3FigurePixelInventoryError("authorized member must be an object")
        if set(member) != {
            "path",
            "temperature_k",
            "expected_uncompressed_bytes",
            "expected_shape",
            "expected_storage",
        }:
            raise SrTiO3FigurePixelInventoryError("authorized member contract fields drifted")
        path = member.get("path")
        temperature = member.get("temperature_k")
        if not isinstance(path, str) or not isinstance(temperature, int):
            raise SrTiO3FigurePixelInventoryError("authorized member types are invalid")
        if member.get("expected_uncompressed_bytes") != 33554704:
            raise SrTiO3FigurePixelInventoryError("authorized TIFF byte count drifted")
        if member.get("expected_shape") != [2048, 2048]:
            raise SrTiO3FigurePixelInventoryError("authorized TIFF shape drifted")
        if member.get("expected_storage") != "float64":
            raise SrTiO3FigurePixelInventoryError("authorized TIFF storage drifted")
        observed[path] = temperature
    if observed != expected:
        raise SrTiO3FigurePixelInventoryError("authorized TIFF identity/temperature mapping drifted")

    figure = config.get("publication_figure")
    if not isinstance(figure, dict):
        raise SrTiO3FigurePixelInventoryError("publication_figure must be an object")
    if figure.get("doi") != "10.1038/s41586-026-10823-x":
        raise SrTiO3FigurePixelInventoryError("publication DOI drifted")
    if figure.get("figure") != "1" or figure.get("panel") != "d":
        raise SrTiO3FigurePixelInventoryError("publication figure/panel drifted")
    image_url = figure.get("image_url")
    if not isinstance(image_url, str):
        raise SrTiO3FigurePixelInventoryError("publication figure image URL is missing")
    parsed = urllib.parse.urlparse(image_url)
    if parsed.scheme != "https" or parsed.hostname != "media.springernature.com":
        raise SrTiO3FigurePixelInventoryError("publication figure host is not trusted")
    if not parsed.path.endswith("/41586_2026_10823_Fig1_HTML.png"):
        raise SrTiO3FigurePixelInventoryError("publication figure image path drifted")
    if figure.get("maximum_download_bytes") != 5000000:
        raise SrTiO3FigurePixelInventoryError("publication figure byte ceiling drifted")
    if figure.get("authoritative_panel_temperatures_k") != [23, 91, 172]:
        raise SrTiO3FigurePixelInventoryError("publication figure temperatures drifted")
    if figure.get("authoritative_display_scale_bar_inv_angstrom") != 0.1:
        raise SrTiO3FigurePixelInventoryError("publication scale-bar fact drifted")

    inputs = config.get("evidence_inputs")
    if not isinstance(inputs, dict) or len(inputs) != 6:
        raise SrTiO3FigurePixelInventoryError("evidence_inputs contract drifted")
    for path in inputs.values():
        _resolve_repo_path(path)

    operations = config.get("authorized_operations")
    if not isinstance(operations, dict):
        raise SrTiO3FigurePixelInventoryError("authorized_operations must be an object")
    required_true = {
        "download_exact_saed_archive",
        "verify_archive_md5_before_member_decode",
        "decode_exact_three_saed_tiff_arrays",
        "download_exact_publication_figure_png",
        "record_source_and_figure_sha256",
        "record_array_shape_dtype_finite_range",
        "create_display_only_linear_minmax_uint8_previews",
        "manual_panel_localization_for_identity_review",
        "record_descriptive_identity_mapping_decision",
    }
    if any(operations.get(key) is not True for key in required_true):
        raise SrTiO3FigurePixelInventoryError("required bounded pixel operations are not authorized")
    if any(value is not False for key, value in operations.items() if key not in required_true):
        raise SrTiO3FigurePixelInventoryError("stronger image/analyzer operations must remain disabled")

    rules = config.get("decision_rules")
    if not isinstance(rules, dict) or not rules or any(value is not True for value in rules.values()):
        raise SrTiO3FigurePixelInventoryError("all fail-closed mapping rules must be enabled")
    return config


def _validate_evidence_chain(config: Mapping[str, Any]) -> dict[str, str]:
    paths = {name: _resolve_repo_path(path) for name, path in config["evidence_inputs"].items()}
    docs = {name: _load_json(path) for name, path in paths.items()}

    metadata = docs["metadata_snapshot"]
    archive = metadata.get("saed_archive")
    if metadata.get("execution_status") != "metadata_audit_completed" or not isinstance(archive, Mapping):
        raise SrTiO3FigurePixelInventoryError("metadata evidence is not a completed SAED source audit")
    contract_archive = config["source_archive"]
    if archive.get("content_url") != contract_archive["content_url"]:
        raise SrTiO3FigurePixelInventoryError("Zenodo archive URL differs from metadata evidence")
    if archive.get("bytes") != contract_archive["bytes"] or archive.get("md5") != contract_archive["md5"]:
        raise SrTiO3FigurePixelInventoryError("Zenodo archive identity differs from metadata evidence")

    remote = docs["remote_inventory_snapshot"]
    if remote.get("execution_status") != "remote_central_directory_inventory_completed":
        raise SrTiO3FigurePixelInventoryError("remote inventory evidence is not completed")
    if remote.get("target_archive", {}).get("repository_md5") != contract_archive["md5"]:
        raise SrTiO3FigurePixelInventoryError("remote inventory archive MD5 drifted")

    tiff = docs["tiff_metadata_snapshot"]
    if tiff.get("case_id") != "zenodo_srtio3_saed_tiff_metadata":
        raise SrTiO3FigurePixelInventoryError("TIFF metadata evidence identity drifted")
    common = tiff.get("common_tiff_structure")
    if not isinstance(common, Mapping):
        raise SrTiO3FigurePixelInventoryError("TIFF common structure is invalid")
    if common.get("ImageWidth") != 2048 or common.get("ImageLength") != 2048:
        raise SrTiO3FigurePixelInventoryError("TIFF shape differs from prior evidence")
    if common.get("BitsPerSample") != 64 or common.get("SampleFormat") != 3:
        raise SrTiO3FigurePixelInventoryError("TIFF storage differs from prior evidence")
    if common.get("Compression") != 1 or common.get("StripOffsets") != PIXEL_OFFSET:
        raise SrTiO3FigurePixelInventoryError("TIFF pixel layout differs from prior evidence")

    prepixel = docs["prepixel_metadata_snapshot"]
    if prepixel.get("range_evidence", {}).get("pixel_bytes_decompressed") != 0:
        raise SrTiO3FigurePixelInventoryError("pre-pixel predecessor unexpectedly accessed pixels")

    publication = docs["publication_provenance_snapshot"]
    readiness = publication.get("readiness")
    if not isinstance(readiness, Mapping):
        raise SrTiO3FigurePixelInventoryError("publication provenance readiness is invalid")
    if readiness.get("temperature_semantics_resolved") is not True:
        raise SrTiO3FigurePixelInventoryError("publication evidence does not resolve temperature semantics")
    if readiness.get("bounded_source_to_published_figure_mapping_can_be_predeclared") is not True:
        raise SrTiO3FigurePixelInventoryError("publication evidence does not authorize mapping predeclaration")
    if readiness.get("saed_tiff_pixel_access_authorized") is not False:
        raise SrTiO3FigurePixelInventoryError("predecessor publication audit crossed pixel boundary")

    claims = docs["publication_claims_snapshot"].get("claims")
    if not isinstance(claims, Mapping):
        raise SrTiO3FigurePixelInventoryError("publication claims snapshot is invalid")
    if claims.get("figure_1d_temperatures_k") != [23, 91, 172]:
        raise SrTiO3FigurePixelInventoryError("publication temperature claims drifted")
    if claims.get("figure_1d_reciprocal_scale_bar_inv_angstrom") != 0.1:
        raise SrTiO3FigurePixelInventoryError("publication scale-bar claim drifted")

    return {name: _sha256_file(path) for name, path in paths.items()}


def _download_bytes(url: str, maximum_bytes: int, *, source_kind: str) -> tuple[bytes, str, str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise SrTiO3FigurePixelInventoryError("download URL must use HTTPS")
    if source_kind == "zenodo":
        if parsed.hostname != "zenodo.org":
            raise SrTiO3FigurePixelInventoryError("Zenodo request host drifted")
        allowed_final_hosts = {"zenodo.org", "files.zenodo.org"}
    elif source_kind == "figure":
        if parsed.hostname != "media.springernature.com":
            raise SrTiO3FigurePixelInventoryError("figure request host drifted")
        allowed_final_hosts = {"media.springernature.com"}
    else:
        raise SrTiO3FigurePixelInventoryError("unsupported download source kind")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"
            ),
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        status = getattr(response, "status", None) or response.getcode()
        if status != 200:
            raise SrTiO3FigurePixelInventoryError(f"{source_kind} download returned HTTP {status}")
        final_url = response.geturl()
        final = urllib.parse.urlparse(final_url)
        if final.scheme != "https" or final.hostname not in allowed_final_hosts:
            raise SrTiO3FigurePixelInventoryError(f"{source_kind} redirected outside trusted host")
        content_type = response.headers.get_content_type()
        payload = response.read(maximum_bytes + 1)
    if len(payload) > maximum_bytes:
        raise SrTiO3FigurePixelInventoryError(f"{source_kind} download exceeded byte ceiling")
    return payload, final_url, content_type


def _decode_authorized_tiff(payload: bytes, member: Mapping[str, Any]) -> np.ndarray:
    shape = member.get("expected_shape")
    if not isinstance(shape, list) or len(shape) != 2 or any(not isinstance(v, int) for v in shape):
        raise SrTiO3FigurePixelInventoryError("TIFF expected_shape is invalid")
    if member.get("expected_storage") != "float64":
        raise SrTiO3FigurePixelInventoryError("only predeclared float64 TIFF storage is supported")
    if len(payload) != member.get("expected_uncompressed_bytes"):
        raise SrTiO3FigurePixelInventoryError("TIFF uncompressed byte count drifted")
    if payload[:4] != b"II*\x00":
        raise SrTiO3FigurePixelInventoryError("TIFF is no longer little-endian classic TIFF")
    pixel_count = int(shape[0]) * int(shape[1])
    required = PIXEL_OFFSET + pixel_count * 8
    if len(payload) != required:
        raise SrTiO3FigurePixelInventoryError("TIFF payload size does not match predeclared pixel layout")
    array = np.frombuffer(payload, dtype="<f8", count=pixel_count, offset=PIXEL_OFFSET)
    return array.reshape((int(shape[0]), int(shape[1])))


def _array_summary(array: np.ndarray) -> dict[str, Any]:
    finite = np.isfinite(array)
    finite_count = int(finite.sum())
    if finite_count == 0:
        raise SrTiO3FigurePixelInventoryError("SAED TIFF contains no finite pixel values")
    values = array[finite]
    return {
        "shape": [int(v) for v in array.shape],
        "dtype": str(array.dtype),
        "finite_count": finite_count,
        "nonfinite_count": int(array.size - finite_count),
        "finite_min": float(values.min()),
        "finite_max": float(values.max()),
    }


def _preview_uint8(array: np.ndarray) -> np.ndarray:
    finite = np.isfinite(array)
    if not finite.any():
        raise SrTiO3FigurePixelInventoryError("cannot preview an array with no finite pixels")
    values = array[finite]
    lower = float(values.min())
    upper = float(values.max())
    safe = np.where(finite, array, lower)
    if upper <= lower:
        scaled = np.zeros(array.shape, dtype=np.uint8)
    else:
        scaled = np.clip((safe - lower) / (upper - lower), 0.0, 1.0)
        scaled = np.rint(scaled * 255.0).astype(np.uint8)
    return cv2.resize(scaled, (PREVIEW_SIZE, PREVIEW_SIZE), interpolation=cv2.INTER_AREA)


def _write_png(path: Path, image: np.ndarray) -> None:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise SrTiO3FigurePixelInventoryError(f"could not encode preview: {path.name}")
    path.write_bytes(encoded.tobytes())


def run_inventory(*, config_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = _validate_config(_load_json(config_resolved))
    evidence_sha256 = _validate_evidence_chain(config)

    output = Path(output_dir).expanduser().resolve(strict=False)
    if output.exists():
        raise SrTiO3FigurePixelInventoryError(f"refusing to overwrite output directory: {output}")
    output.mkdir(parents=True)

    archive_contract = config["source_archive"]
    archive_bytes, archive_final_url, archive_content_type = _download_bytes(
        str(archive_contract["content_url"]),
        int(archive_contract["maximum_download_bytes"]),
        source_kind="zenodo",
    )
    if len(archive_bytes) != archive_contract["bytes"]:
        raise SrTiO3FigurePixelInventoryError("downloaded SAED.zip byte count drifted")
    if _md5_bytes(archive_bytes) != archive_contract["md5"]:
        raise SrTiO3FigurePixelInventoryError("downloaded SAED.zip MD5 drifted")

    source_records: list[dict[str, Any]] = []
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        names = set(archive.namelist())
        for member in config["authorized_source_members"]:
            path = str(member["path"])
            if path not in names:
                raise SrTiO3FigurePixelInventoryError(f"authorized TIFF missing from archive: {path}")
            info = archive.getinfo(path)
            if info.file_size != member["expected_uncompressed_bytes"]:
                raise SrTiO3FigurePixelInventoryError(f"authorized TIFF size drifted: {path}")
            payload = archive.read(path)
            array = _decode_authorized_tiff(payload, member)
            summary = _array_summary(array)
            preview_name = f"source_{int(member['temperature_k'])}K_preview.png"
            _write_png(output / preview_name, _preview_uint8(array))
            source_records.append(
                {
                    "path": path,
                    "temperature_k": int(member["temperature_k"]),
                    "member_uncompressed_bytes": len(payload),
                    "member_sha256": _sha256_bytes(payload),
                    "array": summary,
                    "preview_file": preview_name,
                    "display_normalization": "finite_minmax_linear_uint8_then_area_resize_512x512",
                }
            )
            del array
            del payload

    figure_contract = config["publication_figure"]
    figure_bytes, figure_final_url, figure_content_type = _download_bytes(
        str(figure_contract["image_url"]),
        int(figure_contract["maximum_download_bytes"]),
        source_kind="figure",
    )
    if figure_content_type != "image/png":
        raise SrTiO3FigurePixelInventoryError(
            f"publication figure content type is not image/png: {figure_content_type}"
        )
    figure = cv2.imdecode(np.frombuffer(figure_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if figure is None or figure.ndim not in {2, 3}:
        raise SrTiO3FigurePixelInventoryError("publication Figure 1 PNG could not be decoded")
    figure_name = "publication_figure1.png"
    (output / figure_name).write_bytes(figure_bytes)

    result = {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "execution_status": "bounded_source_and_figure_pixel_inventory_completed",
        "config_sha256": _sha256_file(config_resolved),
        "evidence_input_sha256": evidence_sha256,
        "source_archive": {
            "request_url": archive_contract["content_url"],
            "final_url": archive_final_url,
            "content_type": archive_content_type,
            "bytes": len(archive_bytes),
            "md5": _md5_bytes(archive_bytes),
            "sha256": _sha256_bytes(archive_bytes),
            "archive_retained": False,
        },
        "source_tiffs": source_records,
        "publication_figure": {
            "request_url": figure_contract["image_url"],
            "final_url": figure_final_url,
            "content_type": figure_content_type,
            "bytes": len(figure_bytes),
            "sha256": _sha256_bytes(figure_bytes),
            "decoded_shape": [int(v) for v in figure.shape],
            "decoded_dtype": str(figure.dtype),
            "artifact_file": figure_name,
            "figure_image_retained_in_git": False,
        },
        "analysis_actions": {
            "manual_identity_review_ready": True,
            "identity_mapping_performed": False,
            "automatic_registration_performed": False,
            "reciprocal_pixel_scale_inference_performed": False,
            "pattern_center_inference_performed": False,
            "peak_detection_performed": False,
            "phase_indexing_performed": False,
            "analyzer_execution_performed": False,
            "parameter_tuning_performed": False,
            "four_d_stem_accessed": False,
        },
        "scientific_evidence_level": "Diagnostic",
        "scientific_boundary": (
            "This run authorizes source/figure pixel access only to create an immutable inventory "
            "and display previews for a subsequent predeclared identity review. It does not itself "
            "map panels, infer reciprocal calibration or pattern centre, index phases, tune an "
            "analyzer, or establish external-validation evidence."
        ),
    }
    (output / "pixel_access_inventory.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download exactly the predeclared SrTiO3 SAED source archive and Nature Figure 1, "
            "decode only the three authorized TIFF arrays, and emit display-only inventory artifacts."
        )
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = run_inventory(config_path=args.config, output_dir=args.output)
    except (SrTiO3FigurePixelInventoryError, FileNotFoundError, OSError, zipfile.BadZipFile) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
