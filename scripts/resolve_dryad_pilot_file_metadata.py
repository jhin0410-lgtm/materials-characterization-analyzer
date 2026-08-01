#!/usr/bin/env python3
"""Enrich Dryad file metadata while preserving raw individual responses."""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping

from mca.tem_external_validation_pilot_contract import SOURCE_DOI, SOURCE_VERSION_ID

BASE_URL = "https://datadryad.org"


def _fetch(url: str, attempts: int = 5) -> Mapping[str, Any]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "materials-characterization-analyzer/0.10"},
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
            if urllib.parse.urlsplit(resolved).netloc != "datadryad.org":
                raise ValueError(f"unexpected Dryad link host: {resolved}")
            return resolved
    return None


def _records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    direct = payload.get("files")
    if isinstance(direct, list):
        return [item for item in direct if isinstance(item, Mapping)]
    embedded = payload.get("_embedded")
    if isinstance(embedded, Mapping):
        for key, value in embedded.items():
            if isinstance(value, list) and "file" in str(key).lower():
                return [item for item in value if isinstance(item, Mapping)]
    for key in ("data", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    raise ValueError("Dryad version files response does not contain a file list.")


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


def _name(record: Mapping[str, Any]) -> str | None:
    for key in ("path", "filename", "fileName", "name"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value).name
    return None


def _digest(record: Mapping[str, Any]) -> Any:
    for key in ("digest", "checksum", "md5", "sha256"):
        if record.get(key) is not None:
            return record[key]
    return None


def _normalize_doi(value: str) -> str:
    text = value.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break
    return text.upper()


def _find_doi(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if "doi" in str(key).lower() and isinstance(item, str) and "10." in item:
                return item
        for item in value.values():
            found = _find_doi(item)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_doi(item)
            if found is not None:
                return found
    return None


def _verify_dataset_identity(
    version_payload: Mapping[str, Any], version_url: str, doi: str
) -> Mapping[str, Any] | None:
    observed = _find_doi(version_payload)
    dataset_payload: Mapping[str, Any] | None = None
    if observed is None:
        dataset_url = _link(version_payload, version_url, "stash:dataset", "dataset")
        if dataset_url is None:
            raise ValueError("Dryad source version lacks verifiable dataset DOI identity.")
        dataset_payload = _fetch(dataset_url)
        observed = _find_doi(dataset_payload)
    if observed is None or _normalize_doi(observed) != _normalize_doi(doi):
        raise ValueError(f"Dryad dataset DOI mismatch: {observed!r} != {doi!r}")
    return dataset_payload


def resolve(
    doi: str,
    expected_version_id: int,
    bindings: Iterable[tuple[int, Path]],
    output_dir: Path,
) -> None:
    if _normalize_doi(doi) != _normalize_doi(SOURCE_DOI):
        raise ValueError(f"unexpected Dryad DOI: {doi!r}")
    if expected_version_id != SOURCE_VERSION_ID:
        raise ValueError(
            f"unexpected Dryad source version: {expected_version_id} != {SOURCE_VERSION_ID}"
        )
    source_bindings = list(bindings)
    payloads = [json.loads(path.read_text(encoding="utf-8")) for _, path in source_bindings]
    if not all(isinstance(payload, Mapping) for payload in payloads):
        raise ValueError("all individual-file responses must be objects.")

    version_urls = {
        _link(payload, f"{BASE_URL}/api/v2/files/{file_id}", "stash:version", "version")
        for (file_id, _), payload in zip(source_bindings, payloads)
    }
    if None in version_urls or len(version_urls) != 1:
        raise ValueError(f"pilot files do not resolve to one source version: {version_urls}")
    version_url = next(iter(version_urls))
    version_id = int(version_url.rstrip("/").rsplit("/", 1)[-1])
    if version_id != expected_version_id:
        raise ValueError(
            f"Dryad source-version mismatch: {version_id} != {expected_version_id}"
        )
    version_payload = _fetch(version_url)
    dataset_payload = _verify_dataset_identity(version_payload, version_url, doi)
    files_url = _link(version_payload, version_url, "stash:files", "files")
    if files_url is None:
        files_url = version_url.rstrip("/") + "/files"
    pages, records = _file_pages(files_url)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "dryad-source-version-api.json").write_text(
        json.dumps(version_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if dataset_payload is not None:
        (output_dir / "dryad-source-dataset-api.json").write_text(
            json.dumps(dataset_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    for index, (url, payload) in enumerate(pages, start=1):
        (output_dir / f"dryad-source-version-files-page-{index:03d}.json").write_text(
            json.dumps({"request_url": url, "response": payload}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    (output_dir / "dryad-source-version-files-inventory.json").write_text(
        json.dumps(
            {"version_id": version_id, "dataset_doi": doi, "page_count": len(pages), "file_record_count": len(records), "records": records},
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    for (expected_id, path), payload in zip(source_bindings, payloads):
        expected_name = _name(payload)
        if expected_name is None:
            raise ValueError(f"individual Dryad response has no filename: {path}")
        matches = [record for record in records if _name(record) == expected_name]
        if len(matches) != 1:
            raise ValueError(
                f"expected one source-version record for {expected_name!r}; found {len(matches)}"
            )
        digest = _digest(matches[0])
        if digest is None:
            raise ValueError(f"source-version record lacks checksum for {expected_name}.")
        download_url = _link(
            payload,
            f"{BASE_URL}/api/v2/files/{expected_id}",
            "stash:download",
            "download",
        )
        if download_url is None:
            raise ValueError(f"individual Dryad response lacks download link for {expected_name}.")
        enriched = dict(payload)
        enriched.update(
            {
                "id": expected_id,
                "digest": digest,
                "source_version_id": version_id,
                "source_version_api_url": version_url,
                "source_version_files_api_url": files_url,
                "source_version_files_page_count": len(pages),
                "downloadUrl": download_url,
                "endpoint_file_id_source": "workflow_pinned_request_path",
                "source_version_file_record": dict(matches[0]),
                "dataset_doi": doi,
            }
        )
        destination = output_dir / f"dryad-file-{expected_id}-enriched.json"
        destination.write_text(
            json.dumps(enriched, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"file_id": expected_id, "name": expected_name, "source_version_id": version_id, "digest": digest, "download_url": download_url, "enriched_path": str(destination)}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doi", default=SOURCE_DOI)
    parser.add_argument("--expected-version-id", type=int, default=SOURCE_VERSION_ID)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("files", nargs="+", type=_parse_file_binding)
    args = parser.parse_args()
    resolve(args.doi, args.expected_version_id, args.files, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
