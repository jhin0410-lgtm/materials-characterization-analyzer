from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class FigshareRruffAnnotationInventoryError(RuntimeError):
    """Raised when the bounded RRUFF experimental-annotation inventory contract is violated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FigshareRruffAnnotationInventoryError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise FigshareRruffAnnotationInventoryError(f"invalid JSON: {resolved}") from exc
    if not isinstance(payload, dict):
        raise FigshareRruffAnnotationInventoryError(f"JSON root must be an object: {resolved}")
    return payload


def _resolve_repo_path(value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise FigshareRruffAnnotationInventoryError("repository evidence path must be a string")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise FigshareRruffAnnotationInventoryError("configured repository evidence path is unsafe")
    resolved = (PROJECT_ROOT / candidate).resolve(strict=True)
    if PROJECT_ROOT not in resolved.parents:
        raise FigshareRruffAnnotationInventoryError("repository evidence resolved outside project root")
    return resolved


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _md5_bytes(payload: bytes) -> str:
    try:
        digest = hashlib.md5(usedforsecurity=False)
    except TypeError:  # pragma: no cover
        digest = hashlib.md5()
    digest.update(payload)
    return digest.hexdigest()


def _validate_contract(config: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "case_id",
        "predeclared_at",
        "source_metadata_snapshot",
        "publication_evidence",
        "target_file",
        "authorized_operations",
        "decision_rules",
    }
    if set(config) != required or config.get("schema_version") != "1.0":
        raise FigshareRruffAnnotationInventoryError("annotation inventory contract keys/schema mismatch")
    if config.get("case_id") != "figshare_rruff_experimental_annotation_inventory":
        raise FigshareRruffAnnotationInventoryError("annotation inventory case identity drifted")

    source_snapshot = _resolve_repo_path(config.get("source_metadata_snapshot"))
    publication_evidence = _resolve_repo_path(config.get("publication_evidence"))
    if source_snapshot.name != "verified_figshare_metadata_snapshot.json":
        raise FigshareRruffAnnotationInventoryError("source metadata snapshot drifted")
    if publication_evidence.name != "publication_evidence.json":
        raise FigshareRruffAnnotationInventoryError("publication evidence path drifted")

    target = config.get("target_file")
    expected_target = {
        "figshare_article_id": 7427393,
        "figshare_version": 2,
        "file_id": 13752833,
        "name": "Experimental Data.json",
        "download_url": "https://ndownloader.figshare.com/files/13752833",
        "expected_bytes": 24595,
        "expected_md5": "5397f81312a454f6255b65a1d6d9529e",
        "maximum_response_bytes": 24595,
    }
    if target != expected_target:
        raise FigshareRruffAnnotationInventoryError("target experimental JSON identity drifted")

    operations = config.get("authorized_operations")
    allowed_true = {
        "download_exact_experimental_json",
        "verify_size_and_md5_before_parse",
        "parse_json_structure",
        "inventory_record_keys_and_types",
        "inventory_rruff_ids",
        "inventory_peak_counts_and_wavenumber_ranges",
        "inventory_noise_start_and_missingness",
        "inventory_duplicate_rruff_ids",
    }
    if not isinstance(operations, dict):
        raise FigshareRruffAnnotationInventoryError("authorized_operations must be an object")
    if any(operations.get(key) is not True for key in allowed_true):
        raise FigshareRruffAnnotationInventoryError("required annotation inventory operation is disabled")
    if any(value is not False for key, value in operations.items() if key not in allowed_true):
        raise FigshareRruffAnnotationInventoryError("analyzer/source-spectrum/selection actions must remain disabled")

    rules = config.get("decision_rules")
    if not isinstance(rules, dict) or not rules or any(value is not True for value in rules.values()):
        raise FigshareRruffAnnotationInventoryError("all fail-closed annotation rules must be enabled")
    return config


def _validate_upstream_evidence(config: Mapping[str, Any]) -> dict[str, Any]:
    snapshot_path = _resolve_repo_path(config["source_metadata_snapshot"])
    publication_path = _resolve_repo_path(config["publication_evidence"])
    snapshot = _load_json(snapshot_path)
    publication = _load_json(publication_path)

    target = config["target_file"]
    article = snapshot.get("article")
    license_value = snapshot.get("license")
    files = snapshot.get("files")
    candidate = snapshot.get("experimental_reference_candidate")
    readiness = snapshot.get("readiness")
    if not isinstance(article, Mapping) or article.get("id") != target["figshare_article_id"]:
        raise FigshareRruffAnnotationInventoryError("upstream Figshare article identity drifted")
    if article.get("version") != target["figshare_version"]:
        raise FigshareRruffAnnotationInventoryError("upstream Figshare version drifted")
    if not isinstance(license_value, Mapping) or license_value.get("name") != "CC BY 4.0":
        raise FigshareRruffAnnotationInventoryError("upstream Figshare dataset license drifted")
    if not isinstance(files, list):
        raise FigshareRruffAnnotationInventoryError("upstream Figshare file inventory is invalid")
    matches = [record for record in files if isinstance(record, Mapping) and record.get("id") == target["file_id"]]
    if len(matches) != 1:
        raise FigshareRruffAnnotationInventoryError("target file is not uniquely present upstream")
    record = matches[0]
    for key, expected in (
        ("name", target["name"]),
        ("size", target["expected_bytes"]),
        ("computed_md5", target["expected_md5"]),
        ("supplied_md5", target["expected_md5"]),
    ):
        if record.get(key) != expected:
            raise FigshareRruffAnnotationInventoryError(f"upstream target file {key} drifted")
    if not isinstance(candidate, Mapping) or candidate.get("id") != target["file_id"]:
        raise FigshareRruffAnnotationInventoryError("upstream experimental reference candidate drifted")
    if not isinstance(readiness, Mapping) or readiness.get("experimental_json_download_authorized") is not False:
        raise FigshareRruffAnnotationInventoryError("metadata stage unexpectedly authorized payload download")

    unresolved = publication.get("unresolved_reference_provenance")
    if not isinstance(unresolved, Mapping):
        raise FigshareRruffAnnotationInventoryError("publication provenance is malformed")
    if unresolved.get("suitability_as_authoritative_physical_peak_truth") != "Inconclusive":
        raise FigshareRruffAnnotationInventoryError("publication peak truth was prematurely promoted")
    return {
        "metadata_snapshot_sha256": _sha256_file(snapshot_path),
        "publication_evidence_sha256": _sha256_file(publication_path),
        "dataset_license": "CC BY 4.0",
        "target_file_id": target["file_id"],
        "target_file_md5": target["expected_md5"],
    }


def _download_exact_file(target: Mapping[str, Any]) -> tuple[bytes, dict[str, Any]]:
    url = str(target["download_url"])
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "ndownloader.figshare.com":
        raise FigshareRruffAnnotationInventoryError("target file URL is outside trusted Figshare downloader")
    if parsed.path != "/files/13752833" or parsed.query or parsed.fragment:
        raise FigshareRruffAnnotationInventoryError("target file URL path drifted")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "materials-characterization-analyzer-figshare-annotation-inventory/1.0",
            "Accept": "application/json,application/octet-stream;q=0.9,*/*;q=0.1",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        status = getattr(response, "status", None) or response.getcode()
        if status != 200:
            raise FigshareRruffAnnotationInventoryError(f"experimental JSON returned HTTP {status}")
        final_url = response.geturl()
        final = urllib.parse.urlparse(final_url)
        if final.scheme != "https" or final.hostname not in {
            "ndownloader.figshare.com",
            "figshare.com",
            "www.figshare.com",
        }:
            raise FigshareRruffAnnotationInventoryError(
                f"experimental JSON redirected outside trusted Figshare hosts: {final.hostname}"
            )
        payload = response.read(int(target["maximum_response_bytes"]) + 1)
        content_type = response.headers.get_content_type()
    if len(payload) != int(target["expected_bytes"]):
        raise FigshareRruffAnnotationInventoryError(
            f"experimental JSON byte count drifted: {len(payload)} != {target['expected_bytes']}"
        )
    observed_md5 = _md5_bytes(payload)
    if observed_md5 != target["expected_md5"]:
        raise FigshareRruffAnnotationInventoryError("experimental JSON MD5 differs from pinned Figshare metadata")
    return payload, {
        "status": int(status),
        "final_url": final_url,
        "content_type": content_type,
        "bytes": len(payload),
        "md5": observed_md5,
        "sha256": _sha256_bytes(payload),
    }


def _find_rruff_records(value: Any, path: str = "$", found: list[tuple[str, Mapping[str, Any]]] | None = None) -> list[tuple[str, Mapping[str, Any]]]:
    if found is None:
        found = []
    if isinstance(value, Mapping):
        if "RRUFF_id" in value:
            found.append((path, value))
            return found
        for key, child in value.items():
            _find_rruff_records(child, f"{path}.{key}", found)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _find_rruff_records(child, f"{path}[{index}]", found)
    return found


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _numeric_list(value: Any) -> list[float] | None:
    if not isinstance(value, list):
        return None
    result: list[float] = []
    for item in value:
        number = _finite_number(item)
        if number is None:
            return None
        result.append(number)
    return result


def _summarize_records(records: list[tuple[str, Mapping[str, Any]]]) -> dict[str, Any]:
    if not records:
        raise FigshareRruffAnnotationInventoryError("no RRUFF_id records found in experimental JSON")
    required_fields = ("RRUFF_id", "formula", "type", "noise", "start", "wavenumbers", "intensities", "mp_id")
    field_presence = Counter()
    record_key_sets = Counter()
    ids: list[str] = []
    peak_counts: list[int] = []
    all_peaks: list[float] = []
    noises: list[float] = []
    starts: list[float] = []
    invalid_records: list[dict[str, Any]] = []
    peak_intensity_length_mismatch_count = 0

    for path, record in records:
        record_key_sets["|".join(sorted(str(key) for key in record))] += 1
        for field in required_fields:
            if field in record:
                field_presence[field] += 1
        rruff_id = record.get("RRUFF_id")
        if isinstance(rruff_id, str) and rruff_id.strip():
            ids.append(rruff_id.strip())
        else:
            invalid_records.append({"path": path, "reason": "invalid_rruff_id"})
        peaks = _numeric_list(record.get("wavenumbers"))
        intensities = _numeric_list(record.get("intensities"))
        if peaks is None or not peaks:
            invalid_records.append({"path": path, "reason": "invalid_or_empty_wavenumbers"})
        else:
            peak_counts.append(len(peaks))
            all_peaks.extend(peaks)
        if intensities is None:
            invalid_records.append({"path": path, "reason": "invalid_intensities"})
        elif peaks is not None and len(intensities) != len(peaks):
            peak_intensity_length_mismatch_count += 1
        noise = _finite_number(record.get("noise"))
        start = _finite_number(record.get("start"))
        if noise is not None:
            noises.append(noise)
        if start is not None:
            starts.append(start)

    id_counts = Counter(ids)
    duplicate_ids = sorted(key for key, count in id_counts.items() if count > 1)
    unique_ids = sorted(id_counts)
    record_count = len(records)
    missingness = {
        field: record_count - field_presence[field]
        for field in required_fields
    }
    summary: dict[str, Any] = {
        "record_count": record_count,
        "unique_rruff_id_count": len(unique_ids),
        "rruff_ids": unique_ids,
        "duplicate_rruff_ids": duplicate_ids,
        "duplicate_rruff_id_count": len(duplicate_ids),
        "required_field_missing_counts": missingness,
        "record_key_set_counts": dict(sorted(record_key_sets.items())),
        "invalid_record_count": len(invalid_records),
        "invalid_records": invalid_records,
        "peak_intensity_length_mismatch_count": peak_intensity_length_mismatch_count,
        "peak_count": {
            "record_count_with_numeric_peaks": len(peak_counts),
            "total_peaks": sum(peak_counts),
            "min": min(peak_counts) if peak_counts else None,
            "median": statistics.median(peak_counts) if peak_counts else None,
            "max": max(peak_counts) if peak_counts else None,
        },
        "wavenumber_cm_1": {
            "min": min(all_peaks) if all_peaks else None,
            "max": max(all_peaks) if all_peaks else None,
        },
        "noise": {
            "numeric_count": len(noises),
            "min": min(noises) if noises else None,
            "max": max(noises) if noises else None,
        },
        "start_cm_1": {
            "numeric_count": len(starts),
            "min": min(starts) if starts else None,
            "max": max(starts) if starts else None,
        },
    }
    return summary


def run_inventory(*, config_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = _validate_contract(_load_json(config_resolved))
    upstream = _validate_upstream_evidence(config)
    payload, download = _download_exact_file(config["target_file"])
    try:
        parsed = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FigshareRruffAnnotationInventoryError("experimental annotation payload is not valid UTF-8 JSON") from exc
    records = _find_rruff_records(parsed)
    summary = _summarize_records(records)

    result = {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "execution_status": "figshare_rruff_experimental_annotation_inventory_completed",
        "contract_sha256": _sha256_file(config_resolved),
        "upstream_evidence": upstream,
        "source_file": {
            "figshare_article_id": config["target_file"]["figshare_article_id"],
            "figshare_version": config["target_file"]["figshare_version"],
            "file_id": config["target_file"]["file_id"],
            "name": config["target_file"]["name"],
            **download,
            "raw_payload_retained": False,
        },
        "annotation_inventory": summary,
        "evidence_assessment": {
            "source_file_identity": "Supported",
            "json_structure_readiness": "Supported" if summary["invalid_record_count"] == 0 else "Diagnostic",
            "rruff_id_inventory": "Supported",
            "published_peak_annotation_inventory": "Diagnostic",
            "independent_authoritative_peak_position_truth": "Inconclusive",
            "raman_peak_localization_validation_readiness": "Inconclusive",
            "scientific_evidence_level": "Diagnostic",
        },
        "readiness": {
            "annotation_inventory_ready": True,
            "raw_annotation_payload_retained": False,
            "rruff_spectrum_download_authorized": False,
            "final_validation_subset_selection_authorized": False,
            "raman_analyzer_execution_authorized": False,
            "parameter_tuning_authorized": False,
            "model_fit_or_training_authorized": False,
            "authoritative_peak_truth_claim_authorized": False,
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "next_evidence": {
            "priority": 1,
            "requirement": "predeclare_target_blind_reference_subset_and_peak_matching_protocol_before_any_rruff_spectrum_or_mca_output_access",
            "why": (
                "The frozen published annotation file can now be inventoried independently of MCA. "
                "The next scientific risk is post-hoc spectrum/subset/tolerance selection, so reference IDs and "
                "matching rules must be frozen before source spectra or MCA peak outputs are viewed."
            ),
        },
        "scientific_boundary": [
            "Only Figshare file 13752833 was downloaded and parsed after exact size/MD5 verification.",
            "No RRUFF source spectrum, computational Raman data, CIF archive, Materials Project match, or MCA Raman output was accessed for selection or scoring.",
            "Published peak locations remain Diagnostic annotations rather than authoritative physical truth.",
            "No final validation subset, tolerance, Raman analyzer execution, tuning, external-validation claim, or engineering decision is authorized."
        ],
    }

    output = Path(output_path).expanduser().resolve(strict=False)
    if output.exists():
        raise FigshareRruffAnnotationInventoryError(f"refusing to overwrite output: {output}")
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
            "Download and inventory only the checksum-bound Figshare RRUFF experimental annotation JSON "
            "without accessing source spectra or running the MCA Raman analyzer."
        )
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = run_inventory(config_path=args.config, output_path=args.output)
    except (FigshareRruffAnnotationInventoryError, FileNotFoundError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
