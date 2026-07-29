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


def resolve(doi: str, paths: Iterable[Path], output_dir: Path) -> None:
    source_paths = list(paths)
    source_payloads = [json.loads(path.read_text(encoding="utf-8")) for path in source_paths]
    if not all(isinstance(payload, Mapping) for payload in source_payloads):
        raise ValueError("all Dryad individual-file responses must be objects.")

    dataset_url = _dataset_url(doi)
    dataset_payload = _fetch(dataset_url)
    version_url = _version_url(dataset_payload, dataset_url)
    version_payload = _fetch(version_url)
    files_url = _files_url(version_payload, version_url)
    files_payload = _fetch(files_url)
    records = _records(files_payload)

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("dryad-dataset-api.json", dataset_payload),
        ("dryad-version-api.json", version_payload),
        ("dryad-version-files-api.json", files_payload),
    ):
        (output_dir / name).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    for path, payload in zip(source_paths, source_payloads):
        source_id = _id(payload)
        expected_name = _name(payload)
        if expected_name is None:
            raise ValueError(f"individual Dryad response has no filename: {path}")
        name_matches = [record for record in records if _name(record) == expected_name]
        matches = (
            [record for record in name_matches if _id(record) == source_id]
            if source_id is not None
            else name_matches
        )
        if len(matches) != 1:
            raise ValueError(
                f"expected exactly one version-file record for {source_id} {expected_name!r}; "
                f"found {len(matches)}"
            )
        resolved_id = _id(matches[0])
        if resolved_id is None:
            raise ValueError(f"version-file record lacks ID for {expected_name}.")
        digest = _digest(matches[0])
        if digest is None:
            raise ValueError(f"version-file record lacks checksum for {expected_name}.")
        enriched = dict(payload)
        enriched["id"] = resolved_id
        enriched["digest"] = digest
        enriched["dataset_api_url"] = dataset_url
        enriched["version_api_url"] = version_url
        enriched["version_files_api_url"] = files_url
        enriched["version_file_record"] = dict(matches[0])
        path.write_text(
            json.dumps(enriched, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {"file_id": resolved_id, "name": expected_name, "digest": digest}
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doi", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    resolve(args.doi, args.files, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
