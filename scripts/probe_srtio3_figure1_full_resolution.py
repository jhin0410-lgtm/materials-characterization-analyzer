from __future__ import annotations

import argparse
import json
import struct
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
EXPECTED_IHDR_LENGTH = 13


class FigureFullResolutionReadinessError(RuntimeError):
    """Raised when the predeclared bounded Figure 1 readiness probe is violated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FigureFullResolutionReadinessError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise FigureFullResolutionReadinessError(f"invalid JSON: {resolved}") from exc
    if not isinstance(payload, dict):
        raise FigureFullResolutionReadinessError(f"JSON root must be an object: {resolved}")
    return payload


def _resolve_repo_path(value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise FigureFullResolutionReadinessError("evidence path must be a non-empty string")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise FigureFullResolutionReadinessError("configured evidence path is unsafe")
    resolved = (PROJECT_ROOT / candidate).resolve(strict=True)
    if PROJECT_ROOT not in resolved.parents:
        raise FigureFullResolutionReadinessError("evidence path resolved outside project root")
    return resolved


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "case_id",
        "predeclared_at",
        "objective",
        "source_publication",
        "evidence_inputs",
        "authorized_operations",
        "range_contract",
        "decision_rules",
        "expected_closeout_states",
    }
    if set(config) != required or config.get("schema_version") != "1.0":
        raise FigureFullResolutionReadinessError("readiness config keys/schema mismatch")

    source = config.get("source_publication")
    if not isinstance(source, dict):
        raise FigureFullResolutionReadinessError("source_publication must be an object")
    if source.get("doi") != "10.1038/s41586-026-10823-x" or source.get("figure") != "1":
        raise FigureFullResolutionReadinessError("publication identity drifted")
    if source.get("known_lw685_shape") != [398, 685, 4]:
        raise FigureFullResolutionReadinessError("known lw685 shape drifted")
    if source.get("known_lw685_sha256") != (
        "3ac7a9ba3f349ca74020008319f3994cc6dfe2e3b9653075a369eabf47a1a426"
    ):
        raise FigureFullResolutionReadinessError("known lw685 identity drifted")
    candidate_url = source.get("candidate_full_url")
    if not isinstance(candidate_url, str):
        raise FigureFullResolutionReadinessError("candidate full URL is missing")
    parsed = urllib.parse.urlparse(candidate_url)
    if parsed.scheme != "https" or parsed.hostname != "media.springernature.com":
        raise FigureFullResolutionReadinessError("candidate full URL host is not trusted")
    if "/full/springer-static/image/" not in parsed.path:
        raise FigureFullResolutionReadinessError("candidate URL is not the predeclared full asset path")
    if not parsed.path.endswith("/41586_2026_10823_Fig1_HTML.png"):
        raise FigureFullResolutionReadinessError("candidate full asset filename drifted")

    evidence = config.get("evidence_inputs")
    if not isinstance(evidence, dict) or len(evidence) != 4:
        raise FigureFullResolutionReadinessError("evidence_inputs contract drifted")
    for value in evidence.values():
        _resolve_repo_path(value)

    operations = config.get("authorized_operations")
    required_true = {
        "request_exact_candidate_full_url",
        "require_http_range_response",
        "read_png_signature_and_ihdr_only",
        "record_http_headers_and_png_dimensions",
    }
    if not isinstance(operations, dict):
        raise FigureFullResolutionReadinessError("authorized_operations must be an object")
    if any(operations.get(key) is not True for key in required_true):
        raise FigureFullResolutionReadinessError("required bounded operations are not authorized")
    if any(value is not False for key, value in operations.items() if key not in required_true):
        raise FigureFullResolutionReadinessError("pixel/analysis operations must remain disabled")

    range_contract = config.get("range_contract")
    expected_range = {
        "request_start_byte": 0,
        "request_end_byte": 32,
        "expected_response_bytes": 33,
        "require_http_status": 206,
        "require_content_type": "image/png",
        "require_png_signature": True,
        "require_first_chunk_type": "IHDR",
        "maximum_total_response_bytes": 33,
    }
    if range_contract != expected_range:
        raise FigureFullResolutionReadinessError("range contract drifted")

    rules = config.get("decision_rules")
    if not isinstance(rules, dict) or not rules or any(value is not True for value in rules.values()):
        raise FigureFullResolutionReadinessError("all fail-closed decision rules must be enabled")
    return config


def _validate_evidence(config: Mapping[str, Any]) -> None:
    docs = {
        name: _load_json(_resolve_repo_path(path))
        for name, path in config["evidence_inputs"].items()
    }
    claims = docs["publication_claims_snapshot"].get("claims")
    provenance = docs["publication_provenance_snapshot"].get("readiness")
    pixel = docs["pixel_source_snapshot"].get("publication_figure")
    review = docs["manual_identity_review"].get("next_evidence_requirement")
    if not isinstance(claims, Mapping) or claims.get("figure_1d_temperatures_k") != [23, 91, 172]:
        raise FigureFullResolutionReadinessError("publication claim evidence drifted")
    if not isinstance(provenance, Mapping) or provenance.get("temperature_semantics_resolved") is not True:
        raise FigureFullResolutionReadinessError("publication provenance evidence drifted")
    if not isinstance(pixel, Mapping) or pixel.get("sha256") != config["source_publication"]["known_lw685_sha256"]:
        raise FigureFullResolutionReadinessError("known lw685 pixel source evidence drifted")
    if not isinstance(review, Mapping):
        raise FigureFullResolutionReadinessError("manual identity review is invalid")
    if review.get("requirement") != "authoritative_higher_resolution_figure1d_or_explicit_source_to_panel_mapping":
        raise FigureFullResolutionReadinessError("manual review does not request higher-resolution evidence")
    if review.get("automatic_registration_authorized") is not False:
        raise FigureFullResolutionReadinessError("manual review unexpectedly authorized registration")
    if review.get("reciprocal_scale_inference_authorized") is not False:
        raise FigureFullResolutionReadinessError("manual review unexpectedly authorized scale inference")


def _parse_png_header(payload: bytes) -> dict[str, int]:
    if len(payload) != 33:
        raise FigureFullResolutionReadinessError("PNG header probe must contain exactly 33 bytes")
    if payload[:8] != PNG_SIGNATURE:
        raise FigureFullResolutionReadinessError("candidate response is not a PNG signature")
    chunk_length = struct.unpack(">I", payload[8:12])[0]
    chunk_type = payload[12:16]
    if chunk_length != EXPECTED_IHDR_LENGTH or chunk_type != b"IHDR":
        raise FigureFullResolutionReadinessError("first PNG chunk is not the expected IHDR")
    width, height = struct.unpack(">II", payload[16:24])
    bit_depth = payload[24]
    color_type = payload[25]
    compression_method = payload[26]
    filter_method = payload[27]
    interlace_method = payload[28]
    if width <= 0 or height <= 0:
        raise FigureFullResolutionReadinessError("PNG dimensions are invalid")
    if compression_method != 0 or filter_method != 0:
        raise FigureFullResolutionReadinessError("PNG IHDR uses unsupported compression/filter method")
    return {
        "width": width,
        "height": height,
        "bit_depth": bit_depth,
        "color_type": color_type,
        "compression_method": compression_method,
        "filter_method": filter_method,
        "interlace_method": interlace_method,
    }


def _probe_range(url: str) -> tuple[bytes, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"
            ),
            "Accept": "image/png,image/*;q=0.8",
            "Accept-Encoding": "identity",
            "Range": "bytes=0-32",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        status = getattr(response, "status", None) or response.getcode()
        final_url = response.geturl()
        parsed = urllib.parse.urlparse(final_url)
        if parsed.scheme != "https" or parsed.hostname != "media.springernature.com":
            raise FigureFullResolutionReadinessError("candidate probe redirected outside trusted host")
        if status != 206:
            raise FigureFullResolutionReadinessError(
                f"candidate probe requires HTTP 206; got {status}; response body was not read"
            )
        content_type = response.headers.get_content_type()
        if content_type != "image/png":
            raise FigureFullResolutionReadinessError(
                f"candidate probe content type is not image/png: {content_type}"
            )
        content_range = response.headers.get("Content-Range")
        if content_range is None or not content_range.startswith("bytes 0-32/"):
            raise FigureFullResolutionReadinessError("candidate probe Content-Range is invalid")
        payload = response.read(34)
        if len(payload) != 33:
            raise FigureFullResolutionReadinessError("candidate probe returned unexpected byte count")
        headers = {
            "status": status,
            "final_url": final_url,
            "content_type": content_type,
            "content_range": content_range,
            "content_length": response.headers.get("Content-Length"),
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
        }
    return payload, headers


def run_probe(*, config_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = _validate_config(_load_json(config_resolved))
    _validate_evidence(config)

    source = config["source_publication"]
    payload, headers = _probe_range(str(source["candidate_full_url"]))
    png = _parse_png_header(payload)
    lw_height, lw_width = source["known_lw685_shape"][:2]
    higher = png["width"] > lw_width and png["height"] > lw_height

    result = {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "execution_status": "full_resolution_candidate_header_probe_completed",
        "candidate_url": source["candidate_full_url"],
        "http": headers,
        "bytes_read": len(payload),
        "png_ihdr": png,
        "known_lw685_dimensions": {"width": lw_width, "height": lw_height},
        "candidate_full_asset_availability": "Supported",
        "materially_higher_resolution_than_lw685": "Supported" if higher else "Unsupported",
        "full_image_download_authorized": False,
        "source_to_panel_identity": "Inconclusive",
        "source_tiff_reciprocal_calibration": "Inconclusive",
        "external_validation_readiness": "Inconclusive",
        "scientific_evidence_level": "Diagnostic",
        "next_action": (
            "Predeclare a separate full-image review contract before downloading the candidate asset."
            if higher
            else "Do not download the candidate full asset; it does not improve both raster dimensions."
        ),
        "scientific_boundary": (
            "Only the PNG signature and IHDR were read. No publication image pixel raster, SAED source, "
            "registration, reciprocal-scale inference, pattern-centre inference, indexing, analyzer "
            "execution, or external-validation claim is authorized by this probe."
        ),
    }

    output = Path(output_path).expanduser().resolve(strict=False)
    if output.exists():
        raise FigureFullResolutionReadinessError(f"refusing to overwrite output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Probe exactly 33 bytes of the predeclared Springer Nature full-size Figure 1 candidate "
            "to determine PNG dimensions without downloading the pixel raster."
        )
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = run_probe(config_path=args.config, output_path=args.output)
    except (FigureFullResolutionReadinessError, FileNotFoundError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
