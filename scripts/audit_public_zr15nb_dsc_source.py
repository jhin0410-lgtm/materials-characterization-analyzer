"""Audit the public Zr15Nb DSC source without persisting external raw files.

The audit resolves the pinned Zenodo record, verifies the selected source files,
profiles the three-row table header and numeric columns, and records monotonic
segment evidence. It does not assign phase transformations or run the DSC
analyzer.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

API_URL = "https://zenodo.org/api/records/{record_id}"
USER_AGENT = "materials-characterization-analyzer-zr15nb-dsc-audit/1.0"


class SourceAuditError(RuntimeError):
    """Raised when the pinned public-source contract cannot be verified."""


def _request_bytes(url: str, *, timeout: int = 180) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, */*"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise SourceAuditError(f"HTTP {exc.code} while requesting source: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SourceAuditError(f"Could not reach source repository: {exc.reason}") from exc


def _load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SourceAuditError("case config must contain a JSON object")
    if payload.get("case_id") != "public_zr15nb_dsc_source_audit":
        raise SourceAuditError("unexpected case_id")
    return payload


def _record_files(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    files = payload.get("files")
    records: list[dict[str, Any]] = []
    if isinstance(files, list):
        iterable: Iterable[tuple[str | None, Any]] = ((None, item) for item in files)
    elif isinstance(files, Mapping) and isinstance(files.get("entries"), Mapping):
        iterable = files["entries"].items()
    else:
        raise SourceAuditError("Zenodo metadata did not expose a supported file inventory")

    for fallback_name, value in iterable:
        if not isinstance(value, Mapping):
            continue
        links = value.get("links") if isinstance(value.get("links"), Mapping) else {}
        name = value.get("key") or value.get("filename") or fallback_name
        checksum = value.get("checksum")
        if isinstance(checksum, Mapping):
            algorithm = checksum.get("algorithm") or checksum.get("type")
            digest = checksum.get("value") or checksum.get("checksum")
            checksum_text = f"{algorithm}:{digest}" if algorithm and digest else None
        else:
            checksum_text = checksum
        content_url = links.get("content") or links.get("self") or value.get("download")
        records.append(
            {
                "filename": str(name or ""),
                "size": value.get("size"),
                "checksum": checksum_text,
                "content_url": content_url,
                "file_id": value.get("id"),
            }
        )
    return records


def _split_checksum(value: Any) -> tuple[str | None, str | None]:
    if not isinstance(value, str) or ":" not in value:
        return None, None
    algorithm, digest = value.split(":", 1)
    return algorithm.strip().lower(), digest.strip().lower()


def _verify_bytes(
    payload: bytes,
    *,
    configured: Mapping[str, Any],
    repository_record: Mapping[str, Any],
) -> dict[str, Any]:
    configured_algorithm = str(configured.get("checksum_algorithm") or "").lower()
    configured_digest = str(configured.get("checksum") or "").lower()
    repository_algorithm, repository_digest = _split_checksum(repository_record.get("checksum"))
    if not configured_algorithm or not configured_digest:
        raise SourceAuditError("configured source checksum is incomplete")
    if repository_algorithm and repository_algorithm != configured_algorithm:
        raise SourceAuditError("repository checksum algorithm differs from pinned contract")
    if repository_digest and repository_digest != configured_digest:
        raise SourceAuditError("repository checksum differs from pinned contract")
    try:
        observed = hashlib.new(configured_algorithm, payload).hexdigest().lower()
    except ValueError as exc:
        raise SourceAuditError(f"unsupported checksum algorithm: {configured_algorithm}") from exc
    if observed != configured_digest:
        raise SourceAuditError(f"checksum mismatch for {configured['filename']}")
    repository_size = repository_record.get("size")
    if isinstance(repository_size, int) and repository_size != len(payload):
        raise SourceAuditError(f"repository byte size mismatch for {configured['filename']}")
    configured_size = configured.get("expected_size_bytes")
    if configured_size is not None and configured_size != len(payload):
        raise SourceAuditError(f"configured byte size mismatch for {configured['filename']}")
    downloaded_sha256 = hashlib.sha256(payload).hexdigest()
    expected_sha256 = configured.get("verified_sha256")
    if expected_sha256 is not None:
        if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
            raise SourceAuditError("configured verified_sha256 is invalid")
        if downloaded_sha256 != expected_sha256.lower():
            raise SourceAuditError(f"SHA-256 mismatch for {configured['filename']}")
    return {
        "filename": configured["filename"],
        "role": configured["role"],
        "bytes": len(payload),
        "source_checksum_algorithm": configured_algorithm,
        "source_checksum": configured_digest,
        "source_checksum_verified": True,
        "downloaded_sha256": downloaded_sha256,
        "verified_sha256": expected_sha256.lower() if isinstance(expected_sha256, str) else None,
        "verified_sha256_matched": expected_sha256 is None or downloaded_sha256 == expected_sha256.lower(),
    }


def _decode_text(payload: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return payload.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise SourceAuditError("source text could not be decoded")


def _detect_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:50])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        return dialect.delimiter
    except csv.Error:
        candidates = [",", ";", "\t"]
        scored = []
        for delimiter in candidates:
            widths = [len(row) for row in csv.reader(io.StringIO(sample), delimiter=delimiter)]
            nontrivial = [width for width in widths if width > 1]
            score = (len(nontrivial), max(nontrivial, default=0))
            scored.append((score, delimiter))
        return max(scored)[1]


def _parse_number(value: str, *, delimiter: str) -> float | None:
    text = value.strip().replace("\u2212", "-").replace("\u00a0", "")
    if not text:
        return None
    if delimiter != "," and text.count(",") == 1 and "." not in text:
        text = text.replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _longest_strict_run(
    values: Sequence[float | None], *, increasing: bool
) -> dict[str, int]:
    best_start = 0
    best_end = 0
    current_start: int | None = None
    previous: float | None = None
    for index, value in enumerate(values):
        if value is None:
            current_start = None
            previous = None
            continue
        if current_start is None:
            current_start = index
        elif previous is None:
            current_start = index
        else:
            valid = value > previous if increasing else value < previous
            if not valid:
                current_start = index
        previous = value
        if current_start is not None and index + 1 - current_start > best_end - best_start:
            best_start, best_end = current_start, index + 1
    return {
        "start": best_start,
        "end_exclusive": best_end,
        "length": best_end - best_start,
    }


def _profile_table(text: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    delimiter = _detect_delimiter(text)
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    if len(rows) < 4:
        raise SourceAuditError("DSC source table has fewer than four rows")
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    headers = normalized[:3]
    data_rows = normalized[3:]
    profiles: list[dict[str, Any]] = []
    for column_index in range(width):
        parsed_values = [
            _parse_number(row[column_index], delimiter=delimiter)
            for row in data_rows
        ]
        values = [number for number in parsed_values if number is not None]
        descriptor_parts = [headers[row_index][column_index].strip() for row_index in range(3)]
        descriptor = " | ".join(part for part in descriptor_parts if part)
        descriptor_folded = descriptor.casefold()
        increasing = _longest_strict_run(parsed_values, increasing=True)
        decreasing = _longest_strict_run(parsed_values, increasing=False)
        profiles.append(
            {
                "column_index": column_index,
                "method_header": headers[0][column_index].strip(),
                "quantity_header": headers[1][column_index].strip(),
                "unit_header": headers[2][column_index].strip(),
                "descriptor": descriptor,
                "numeric_value_count": len(values),
                "minimum": min(values) if values else None,
                "maximum": max(values) if values else None,
                "first_numeric_values": values[:8],
                "longest_strictly_increasing_run": increasing,
                "longest_strictly_decreasing_run": decreasing,
                "temperature_token_candidate": any(
                    token in descriptor_folded
                    for token in ("temperature", "temperatur", "temp", "°c", "degc")
                ),
                "dsc_token_candidate": any(
                    token in descriptor_folded
                    for token in ("dsc", "heat flow", "heatflow", "mw", "w/g")
                ),
            }
        )
    summary = {
        "delimiter": {",": "comma", ";": "semicolon", "\t": "tab"}[delimiter],
        "row_count_including_headers": len(normalized),
        "data_row_count": len(data_rows),
        "column_count": width,
        "header_rows": headers,
        "data_preview_rows": data_rows[:8],
        "temperature_candidate_columns": [
            item["column_index"] for item in profiles if item["temperature_token_candidate"]
        ],
        "dsc_candidate_columns": [
            item["column_index"] for item in profiles if item["dsc_token_candidate"]
        ],
    }
    return summary, profiles


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise SourceAuditError("column profile is empty")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
                    for key, value in row.items()
                }
            )


def _write_manifest(output: Path, generated: Sequence[Path]) -> None:
    records = []
    for path in generated:
        payload = path.read_bytes()
        records.append(
            {
                "path": path.name,
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = {
        "schema_version": "1.0",
        "case_id": "public_zr15nb_dsc_source_audit",
        "artifact_count": len(records),
        "artifacts": records,
    }
    (output / "source_audit_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def run(config_path: Path, output: Path) -> dict[str, Any]:
    if output.exists() and (output.is_symlink() or not output.is_dir() or any(output.iterdir())):
        raise FileExistsError("output directory must be absent or empty")
    output.mkdir(parents=True, exist_ok=True)
    config = _load_config(config_path)
    record_id = config["dataset"]["record_id"]
    metadata_payload = _request_bytes(API_URL.format(record_id=record_id))
    metadata = json.loads(metadata_payload.decode("utf-8"))
    inventory = _record_files(metadata)
    by_name = {record["filename"]: record for record in inventory}

    verified_files: list[dict[str, Any]] = []
    source_payloads: dict[str, bytes] = {}
    with tempfile.TemporaryDirectory(prefix="mca-zr15nb-dsc-"):
        for configured in config["files"]:
            name = configured["filename"]
            record = by_name.get(name)
            if record is None:
                raise SourceAuditError(f"pinned file missing from Zenodo inventory: {name}")
            content_url = record.get("content_url")
            if not isinstance(content_url, str) or not content_url.startswith("https://"):
                raise SourceAuditError(f"pinned file has no downloadable HTTPS URL: {name}")
            payload = _request_bytes(content_url)
            verified_files.append(_verify_bytes(payload, configured=configured, repository_record=record))
            source_payloads[name] = payload

    csv_text, csv_encoding = _decode_text(source_payloads["DSC_ElResistance_ThExpansion.csv"])
    readme_text, readme_encoding = _decode_text(source_payloads["ReadMe.txt"])
    table_summary, column_profiles = _profile_table(csv_text)
    table_summary["encoding"] = csv_encoding

    dsc_columns = table_summary["dsc_candidate_columns"]
    temperature_columns = table_summary["temperature_candidate_columns"]
    status = (
        "source_structure_resolved_adapter_design_ready"
        if dsc_columns and temperature_columns
        else "source_structure_resolved_manual_column_binding_required"
    )
    summary = {
        "schema_version": "1.0",
        "case_id": config["case_id"],
        "source": {
            "repository": config["dataset"]["repository"],
            "record_id": record_id,
            "doi": config["dataset"]["doi"],
            "version": config["dataset"]["version"],
            "license": config["dataset"]["license"],
            "article_doi": config["article"]["doi"],
            "files": verified_files,
        },
        "reported_acquisition_context": config["article"],
        "table_structure": table_summary,
        "readme": {
            "encoding": readme_encoding,
            "line_count": len(readme_text.splitlines()),
            "lines": readme_text.splitlines()[:100],
        },
        "readiness": {
            "status": status,
            "source_checksums_verified": True,
            "raw_source_files_persisted": False,
            "temperature_column_candidate_count": len(temperature_columns),
            "dsc_column_candidate_count": len(dsc_columns),
            "thermal_analyzer_executed": False,
            "scientific_phase_or_reaction_assignment_performed": False,
        },
        "scientific_closeout": {
            "status": "Diagnostic",
            "result": status,
            "strongest_evidence": (
                "The pinned Zenodo files were downloaded transiently, verified against source MD5, "
                "and profiled at the three-row header, unit, numeric-column, and monotonic-run levels."
            ),
            "primary_limitation": (
                "Column identity, signal normalization, replicate binding, endotherm convention, and "
                "a valid single heating segment must be resolved before the DSC analyzer can run."
            ),
        },
    }

    summary_path = output / "source_audit_summary.json"
    columns_path = output / "source_column_profile.csv"
    report_path = output / "source_audit_report.md"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(columns_path, column_profiles)
    report_path.write_text(
        "\n".join(
            [
                "# Public Zr15Nb DSC Source Audit",
                "",
                "**Evidence level:** Diagnostic",
                "",
                f"**Result:** `{status}`",
                "",
                f"- Verified source files: `{len(verified_files)}`",
                f"- Table rows: `{table_summary['data_row_count']}` data rows",
                f"- Table columns: `{table_summary['column_count']}`",
                f"- Temperature token candidates: `{temperature_columns}`",
                f"- DSC token candidates: `{dsc_columns}`",
                "- Raw source bytes persisted: `false`",
                "- Thermal analyzer executed: `false`",
                "",
                "This audit resolves source structure only. It does not assign phase transformations, "
                "reactions, onset temperatures, enthalpy, or engineering significance.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _write_manifest(output, [summary_path, columns_path, report_path])
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("case_studies/public_zr15nb_dsc/case_config.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    summary = run(args.config, args.output)
    print(
        json.dumps(
            {
                "status": summary["readiness"]["status"],
                "temperature_candidate_columns": summary["table_structure"][
                    "temperature_candidate_columns"
                ],
                "dsc_candidate_columns": summary["table_structure"]["dsc_candidate_columns"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
