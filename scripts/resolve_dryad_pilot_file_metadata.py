#!/usr/bin/env python3
"""Enrich Dryad individual-file API JSON with DOI-version MD5 metadata."""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping

BASE_URL = "https://datadryad.org"


def _fetch(url: str, attempts: int = 5) -> Mapping[str, Any]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "materials-characterization-analyzer/0.9"},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError("Dryad API response must be an object.")
            return payload
        except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise RuntimeError(f"failed to fetch {url}") from last_error


def _link(payload: Mapping[str, Any], base_url: str, *names: str) -> str | None:
    links = payload.get("_links")
    if not isinstance(links, Mapping):
        return None
    for name in names:
        value = links.get(name)
        href: Any = value.get("href") if isinstance(value, Mapping) else value
        if isinstance(href, str) and href.strip():
            resolved = urllib.parse.urljoin(base_url, href.strip())
            if not resolved.startswith("https://datadryad.org/"):
                raise ValueError(f"unexpected Dryad link host: {resolved}")
            return resolved
    return None


def _records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    direct = payload.get("files")
    if isinstance(direct, list):
        return [item for item in direct if isinstance(item, Mapping)]
    for key in ("data", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    embedded = payload.get("_embedded")
    if isinstance(embedded, Mapping):
        for key, value in embedded.items():
            if isinstance(value, list) and "file" in str(key).lower():
                return [item for item in value if isinstance(item, Mapping)]
    raise ValueError("Dryad version files response does not contain a file list.")


def _id(record: Mapping[str, Any]) -> int | None:
    value = record.get("id", record.get("fileId"))
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _name(record: Mapping[str, Any]) -> str | None:
    for key in ("path", "filename", "fileName", "name"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value).name
    return None


def _digest(record: Mapping[str, Any]) -> Any:
    for key in ("digest", "checksum", "md5"):
        value = record.get(key)
        if value is not None:
            return value
    return None


def _dataset_url(doi: str) -> str:
    normalized = doi.strip()
    if normalized.lower().startswith("doi:"):
        normalized = normalized[4:]
    if not normalized:
        raise ValueError("DOI cannot be empty.")
    identifier = urllib.parse.quote(f"doi:{normalized}", safe="")
    return f"{BASE_URL}/api/v2/datasets/{identifier}"


def _version_url(dataset_payload: Mapping[str, Any], dataset_url: str) -> str:
    url = _link(dataset_payload, dataset_url, "stash:version", "version")
    if url is None:
        raise ValueError("Dryad dataset metadata does not link to its latest version.")
    return url


def _files_url(version_payload: Mapping[str, Any], version_url: str) -> str:
    url = _link(version_payload, version_url, "stash:files", "files")
    if url is not None:
        return url
    return version_url.rstrip("/") + "/files"


def _file_pages(start_url: str) -> tuple[list[tuple[str, Mapping[str, Any]]], list[Mapping[str, Any]]]:
    pages: list[tuple[str, Mapping[str, Any]]] = []
    records: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    url: str | None = start_url
    while url is not None:
        if url in seen:
            raise ValueError(f"Dryad file pagination cycle detected at {url}")
        seen.add(url)
        payload = _fetch(url)
        pages.append((url, payload))
        records.extend(_records(payload))
        url = _link(payload, url, "next", "stash:next")
    if not records:
        raise ValueError("Dryad version file inventory is empty.")
    return pages, records


def _parse_file_binding(value: str) -> tuple[int, Path]:
    identifier, separator, path_text = value.partition("=")
    if not separator or not path_text:
        raise argparse.ArgumentTypeError("file bindings must use FILE_ID=PATH")
    try:
        file_id = int(identifier)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Dryad file ID must be an integer") from exc
    if file_id <= 0:
        raise argparse.ArgumentTypeError("Dryad file ID must be positive")
    return file_id, Path(path_text)


def resolve(
    doi: str,
    bindings: Iterable[tuple[int, Path]],
    output_dir: Path,
) -> None:
    source_bindings = list(bindings)
    source_payloads = [
        json.loads(path.read_text(encoding="utf-8")) for _, path in source_bindings
    ]
    if not all(isinstance(payload, Mapping) for payload in source_payloads):
        raise ValueError("all Dryad individual-file responses must be objects.")
    expected_ids = [file_id for file_id, _ in source_bindings]
    if len(set(expected_ids)) != len(expected_ids):
        raise ValueError("Dryad endpoint file IDs must be unique.")

    dataset_url = _dataset_url(doi)
    dataset_payload = _fetch(dataset_url)
    version_url = _version_url(dataset_payload, dataset_url)
    version_payload = _fetch(version_url)
    files_url = _files_url(version_payload, version_url)
    pages, records = _file_pages(files_url)

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("dryad-dataset-api.json", dataset_payload),
        ("dryad-version-api.json", version_payload),
    ):
        (output_dir / name).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    for index, (url, payload) in enumerate(pages, start=1):
        page_record = {"request_url": url, "response": payload}
        (output_dir / f"dryad-version-files-page-{index:03d}.json").write_text(
            json.dumps(page_record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    (output_dir / "dryad-version-files-inventory.json").write_text(
        json.dumps(
            {
                "page_count": len(pages),
                "file_record_count": len(records),
                "records": records,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    for (expected_id, path), payload in zip(source_bindings, source_payloads):
        response_id = _id(payload)
        if response_id is not None and response_id != expected_id:
            raise ValueError(
                f"individual Dryad response ID mismatch: {response_id} != {expected_id}"
            )
        expected_name = _name(payload)
        if expected_name is None:
            raise ValueError(f"individual Dryad response has no filename: {path}")
        name_matches = [record for record in records if _name(record) == expected_name]
        matches = [
            record
            for record in name_matches
            if _id(record) in (None, expected_id)
        ]
        if len(matches) != 1:
            raise ValueError(
                f"expected exactly one version-file record for endpoint ID {expected_id} "
                f"and name {expected_name!r}; found {len(matches)} across {len(pages)} "
                f"pages and {len(records)} records"
            )
        record_id = _id(matches[0])
        if record_id is not None and record_id != expected_id:
            raise ValueError(
                f"version-file record ID mismatch: {record_id} != {expected_id}"
            )
        digest = _digest(matches[0])
        if digest is None:
            raise ValueError(f"version-file record lacks checksum for {expected_name}.")
        enriched = dict(payload)
        enriched["id"] = expected_id
        enriched["digest"] = digest
        enriched["dataset_api_url"] = dataset_url
        enriched["version_api_url"] = version_url
        enriched["version_files_api_url"] = files_url
        enriched["version_files_page_count"] = len(pages)
        enriched["endpoint_file_id_source"] = "workflow_pinned_request_path"
        enriched["version_file_record"] = dict(matches[0])
        path.write_text(
            json.dumps(enriched, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {"file_id": expected_id, "name": expected_name, "digest": digest}
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doi", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("files", nargs="+", type=_parse_file_binding)
    args = parser.parse_args()
    resolve(args.doi, args.files, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
