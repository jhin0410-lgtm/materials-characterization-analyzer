from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class SrTiO3NotebookProvenanceError(RuntimeError):
    """Raised when the bounded SrTiO3 notebook provenance contract is violated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SrTiO3NotebookProvenanceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise SrTiO3NotebookProvenanceError(f"invalid JSON: {resolved}") from exc
    if not isinstance(value, dict):
        raise SrTiO3NotebookProvenanceError("JSON root must be an object")
    return value


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _md5_bytes(payload: bytes) -> str:
    try:
        digest = hashlib.md5(usedforsecurity=False)
    except TypeError:  # pragma: no cover - compatibility fallback
        digest = hashlib.md5()
    digest.update(payload)
    return digest.hexdigest()


def _resolve_repo_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise SrTiO3NotebookProvenanceError("configured repository path is unsafe")
    return (PROJECT_ROOT / candidate).resolve(strict=True)


def _trusted_zenodo_url(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise SrTiO3NotebookProvenanceError("Zenodo content URL is missing")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in {"zenodo.org", "www.zenodo.org"}:
        raise SrTiO3NotebookProvenanceError("content URL is outside trusted Zenodo")
    return value


def _validate_config(value: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "case_id",
        "audit_date",
        "metadata_snapshot",
        "source_file",
        "search_terms",
        "scientific_boundary",
        "decision_rules",
    }
    if set(value) != required or value.get("schema_version") != "1.0":
        raise SrTiO3NotebookProvenanceError("notebook provenance config keys/schema do not match")
    source = value["source_file"]
    if not isinstance(source, dict) or set(source) != {
        "key",
        "expected_bytes",
        "expected_md5",
        "maximum_download_bytes",
    }:
        raise SrTiO3NotebookProvenanceError("source_file contract is invalid")
    if source.get("key") != "Kikuchi_COM.ipynb":
        raise SrTiO3NotebookProvenanceError("source file must remain the pinned notebook")
    if source.get("expected_bytes") != 1711932:
        raise SrTiO3NotebookProvenanceError("notebook byte count contract drifted")
    if source.get("expected_md5") != "56383d23c198347220ed751ddb3dbae5":
        raise SrTiO3NotebookProvenanceError("notebook MD5 contract drifted")
    if not isinstance(source.get("maximum_download_bytes"), int) or not (
        source["expected_bytes"] <= source["maximum_download_bytes"] <= 2_000_000
    ):
        raise SrTiO3NotebookProvenanceError("notebook download ceiling is invalid")

    search_terms = value["search_terms"]
    required_categories = {
        "saed_identity",
        "representation_and_export",
        "preprocessing",
        "calibration",
        "diffraction_context",
    }
    if not isinstance(search_terms, dict) or set(search_terms) != required_categories:
        raise SrTiO3NotebookProvenanceError("search term categories do not match contract")
    for category, terms in search_terms.items():
        if not isinstance(terms, list) or not terms:
            raise SrTiO3NotebookProvenanceError(f"search terms are invalid: {category}")
        if any(not isinstance(term, str) or not term.strip() for term in terms):
            raise SrTiO3NotebookProvenanceError(f"search term is invalid: {category}")

    boundary = value["scientific_boundary"]
    true_keys = {
        "download_verified_notebook_authorized",
        "parse_notebook_markdown_and_code_text_authorized",
    }
    if not isinstance(boundary, dict) or any(boundary.get(key) is not True for key in true_keys):
        raise SrTiO3NotebookProvenanceError("required text provenance operations are not authorized")
    if any(item is not False for key, item in boundary.items() if key not in true_keys):
        raise SrTiO3NotebookProvenanceError("notebook-output/pixel/analyzer actions must remain disabled")
    rules = value["decision_rules"]
    if not isinstance(rules, dict) or any(item is not True for item in rules.values()):
        raise SrTiO3NotebookProvenanceError("all fail-closed notebook rules must be enabled")
    return value


def _resolve_source(config: Mapping[str, Any], metadata: Mapping[str, Any]) -> dict[str, Any]:
    if metadata.get("execution_status") != "metadata_audit_completed":
        raise SrTiO3NotebookProvenanceError("metadata snapshot is not completed")
    source = metadata.get("source")
    if not isinstance(source, Mapping) or source.get("record_id") != 20300700:
        raise SrTiO3NotebookProvenanceError("metadata snapshot is not the pinned SrTiO3 record")
    if source.get("license_id") != "cc-by-4.0":
        raise SrTiO3NotebookProvenanceError("dataset license differs from pinned evidence")
    inventory = metadata.get("file_inventory")
    if not isinstance(inventory, list):
        raise SrTiO3NotebookProvenanceError("metadata file inventory is invalid")
    expected = config["source_file"]
    matches = [
        item
        for item in inventory
        if isinstance(item, Mapping) and item.get("key") == expected["key"]
    ]
    if len(matches) != 1:
        raise SrTiO3NotebookProvenanceError("notebook is not uniquely present in metadata snapshot")
    record = dict(matches[0])
    if record.get("bytes") != expected["expected_bytes"]:
        raise SrTiO3NotebookProvenanceError("notebook byte count differs from pinned contract")
    if record.get("md5") != expected["expected_md5"]:
        raise SrTiO3NotebookProvenanceError("notebook MD5 differs from pinned contract")
    _trusted_zenodo_url(record.get("content_url"))
    return record


def _download_notebook(url: str, *, expected_bytes: int, maximum_bytes: int) -> bytes:
    request = urllib.request.Request(
        _trusted_zenodo_url(url),
        headers={
            "User-Agent": "materials-characterization-analyzer-notebook-provenance/1.0",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        status = getattr(response, "status", None) or response.getcode()
        if status != 200:
            raise SrTiO3NotebookProvenanceError(f"notebook source returned HTTP {status}")
        final = urllib.parse.urlparse(response.geturl())
        if final.scheme != "https" or final.hostname not in {"zenodo.org", "www.zenodo.org"}:
            raise SrTiO3NotebookProvenanceError("notebook download redirected outside trusted Zenodo")
        payload = response.read(maximum_bytes + 1)
    if len(payload) > maximum_bytes:
        raise SrTiO3NotebookProvenanceError("notebook exceeds configured download ceiling")
    if len(payload) != expected_bytes:
        raise SrTiO3NotebookProvenanceError(
            f"notebook byte count differs from pinned source: {len(payload)} != {expected_bytes}"
        )
    return payload


def _cell_source_text(cell: Mapping[str, Any]) -> str:
    source = cell.get("source")
    if isinstance(source, str):
        return source
    if isinstance(source, list) and all(isinstance(item, str) for item in source):
        return "".join(source)
    raise SrTiO3NotebookProvenanceError("notebook cell source is not a supported string/list")


def _excerpt(line: str, term: str, *, maximum: int = 240) -> str:
    normalized = line.strip().replace("\t", " ")
    if len(normalized) <= maximum:
        return normalized
    lower = normalized.casefold()
    position = lower.find(term.casefold())
    if position < 0:
        return normalized[: maximum - 1] + "…"
    half = maximum // 2
    start = max(0, position - half)
    end = min(len(normalized), start + maximum)
    start = max(0, end - maximum)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(normalized) else ""
    return prefix + normalized[start:end] + suffix


def _search_cells(
    notebook: Mapping[str, Any],
    terms_by_category: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, int], dict[str, Any]]:
    cells = notebook.get("cells")
    if not isinstance(cells, list):
        raise SrTiO3NotebookProvenanceError("notebook cells are missing")
    hits: list[dict[str, Any]] = []
    category_counts = {str(category): 0 for category in terms_by_category}
    term_counts = {
        f"{category}:{term}": 0
        for category, terms in terms_by_category.items()
        for term in terms
    }
    cell_counts = {"code": 0, "markdown": 0, "raw": 0, "other": 0}
    ignored_output_cells = 0
    for cell_index, raw_cell in enumerate(cells):
        if not isinstance(raw_cell, Mapping):
            raise SrTiO3NotebookProvenanceError("notebook cell is not an object")
        cell_type = raw_cell.get("cell_type")
        key = cell_type if cell_type in {"code", "markdown", "raw"} else "other"
        cell_counts[str(key)] += 1
        if cell_type == "code" and raw_cell.get("outputs"):
            ignored_output_cells += 1
        if cell_type not in {"code", "markdown"}:
            continue
        text = _cell_source_text(raw_cell)
        cell_sha = _sha256_bytes(text.encode("utf-8"))
        for line_number, line in enumerate(text.splitlines(), start=1):
            folded = line.casefold()
            for category, terms in terms_by_category.items():
                for term in terms:
                    if term.casefold() not in folded:
                        continue
                    category_counts[str(category)] += 1
                    term_counts[f"{category}:{term}"] += 1
                    hits.append(
                        {
                            "category": str(category),
                            "term": str(term),
                            "cell_index": int(cell_index),
                            "cell_type": str(cell_type),
                            "line_number": int(line_number),
                            "line_excerpt": _excerpt(line, str(term)),
                            "cell_source_sha256": cell_sha,
                        }
                    )
    inventory = {
        "total_cells": int(len(cells)),
        "cell_type_counts": cell_counts,
        "code_cells_with_ignored_outputs": int(ignored_output_cells),
        "notebook_outputs_inspected": False,
    }
    return hits, category_counts, term_counts, inventory


def run_audit(*, config_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    config_resolved = Path(config_path).expanduser().resolve(strict=True)
    config = _validate_config(_load_json(config_resolved))
    metadata_path = _resolve_repo_path(str(config["metadata_snapshot"]))
    metadata = _load_json(metadata_path)
    source = _resolve_source(config, metadata)
    expected = config["source_file"]
    payload = _download_notebook(
        str(source["content_url"]),
        expected_bytes=int(expected["expected_bytes"]),
        maximum_bytes=int(expected["maximum_download_bytes"]),
    )
    observed_md5 = _md5_bytes(payload)
    if observed_md5 != expected["expected_md5"]:
        raise SrTiO3NotebookProvenanceError("downloaded notebook MD5 differs from repository metadata")
    try:
        notebook = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SrTiO3NotebookProvenanceError("downloaded notebook is not valid UTF-8 JSON") from exc
    if not isinstance(notebook, Mapping):
        raise SrTiO3NotebookProvenanceError("notebook JSON root is not an object")
    nbformat = notebook.get("nbformat")
    if not isinstance(nbformat, int) or nbformat <= 0:
        raise SrTiO3NotebookProvenanceError("notebook nbformat is invalid")

    hits, category_counts, term_counts, cell_inventory = _search_cells(
        notebook,
        config["search_terms"],
    )
    saed_mentions = category_counts["saed_identity"]
    preprocessing_mentions = category_counts["preprocessing"]
    calibration_mentions = category_counts["calibration"]
    representation_mentions = category_counts["representation_and_export"]

    result = {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "audit_date": config["audit_date"],
        "execution_status": "verified_notebook_text_provenance_audit_completed",
        "config_sha256": _sha256_file(config_resolved),
        "source": {
            "record_id": 20300700,
            "doi": "10.5281/zenodo.20300700",
            "license_id": "cc-by-4.0",
            "metadata_snapshot_sha256": _sha256_file(metadata_path),
            "file_key": source["key"],
            "bytes": int(source["bytes"]),
            "repository_md5": source["md5"],
            "downloaded_md5": observed_md5,
            "downloaded_sha256": _sha256_bytes(payload),
        },
        "notebook": {
            "nbformat": int(nbformat),
            "nbformat_minor": notebook.get("nbformat_minor"),
            **cell_inventory,
            "full_notebook_retained": False,
            "notebook_outputs_inspected": False,
        },
        "search": {
            "category_hit_counts": category_counts,
            "term_hit_counts": term_counts,
            "hit_count": int(len(hits)),
            "hits": hits,
            "search_scope": "markdown_and_code_cell_source_only",
        },
        "evidence_assessment": {
            "notebook_file_identity": "Supported",
            "notebook_text_provenance": "Supported",
            "saed_or_temperature_text_mentions": "Diagnostic" if saed_mentions else "Inconclusive",
            "representation_or_export_text_mentions": "Diagnostic" if representation_mentions else "Inconclusive",
            "preprocessing_text_mentions": "Diagnostic" if preprocessing_mentions else "Inconclusive",
            "calibration_text_mentions": "Diagnostic" if calibration_mentions else "Inconclusive",
            "filename_k_suffix_temperature_semantics": "Inconclusive",
            "saed_tiff_preprocessing_lineage": "Inconclusive",
            "pattern_center_and_reciprocal_calibration": "Inconclusive",
            "external_validation_readiness": "Inconclusive",
            "scientific_evidence_level": "Diagnostic",
        },
        "readiness": {
            "notebook_text_audit_ready": True,
            "saed_tiff_pixel_access_authorized": False,
            "four_d_stem_download_authorized": False,
            "analyzer_execution_authorized": False,
            "phase_indexing_authorized": False,
            "external_validation_ready": False,
            "engineering_decision_ready": False,
        },
        "scientific_boundary": [
            "The exact repository notebook was downloaded only after byte-count and MD5 binding; the full notebook is not retained as audit output.",
            "Only markdown/code cell source text was searched. Notebook outputs were ignored and are not evidence in this audit.",
            "Keyword hits are Diagnostic leads, not proof of preprocessing, calibration, temperature semantics or SAED lineage without contextual support.",
            "Absence of a keyword hit is not evidence that the underlying experiment lacked that property.",
            "No 4D-STEM or SAED pixel data was accessed and no analyzer inference was run."
        ],
    }
    output = Path(output_path).expanduser().resolve(strict=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit the verified SrTiO3 notebook for textual SAED/preprocessing/calibration provenance."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("case_studies/zenodo_srtio3_notebook_provenance/case_config.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/zenodo_srtio3_notebook_provenance/notebook_provenance_snapshot.json"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = run_audit(config_path=args.config, output_path=args.output)
    except (OSError, ValueError, SrTiO3NotebookProvenanceError) as exc:
        print(f"SrTiO3 notebook provenance audit failed: {exc}")
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
