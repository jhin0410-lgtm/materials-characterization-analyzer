#!/usr/bin/env python3
"""Enrich Dryad individual-file API JSON with version-list MD5 metadata."""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping


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


def _link(payload: Mapping[str, Any], *names: str) -> str | None:
    links = payload.get("_links")
    if not isinstance(links, Mapping):
        return None
    for name in names:
        value = links.get(name)
        if isinstance(value, Mapping):
            href = value.get("href")
            if isinstance(href, str) and href.startswith("https://"):
                return href
        if isinstance(value, str) and value.startswith("https://"):
            return value
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
            if isinstance(value, list) and ("file" in str(key).lower()):
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


def _version_url(payload: Mapping[str, Any]) -> str:
    url = _link(payload, "stash:version", "version")
    if url is None:
        raise ValueError("Dryad file metadata does not link to its dataset version.")
    return url


def _files_url(version_payload: Mapping[str, Any], version_url: str) -> str:
    url = _link(version_payload, "stash:files", "files")
    if url is not None:
        return url
    return version_url.rstrip("/") + "/files"


def resolve(paths: Iterable[Path], output_dir: Path) -> None:
    source_payloads = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    if not all(isinstance(payload, Mapping) for payload in source_payloads):
        raise ValueError("all Dryad individual-file responses must be objects.")
    version_urls = {_version_url(payload) for payload in source_payloads}
    if len(version_urls) != 1:
        raise ValueError(f"pilot files do not resolve to one Dryad version: {version_urls}")
    version_url = next(iter(version_urls))
    version_payload = _fetch(version_url)
    files_url = _files_url(version_payload, version_url)
    files_payload = _fetch(files_url)
    records = _records(files_payload)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "dryad-version-api.json").write_text(
        json.dumps(version_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "dryad-version-files-api.json").write_text(
        json.dumps(files_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    for path, payload in zip(paths, source_payloads):
        expected_id = _id(payload)
        expected_name = _name(payload)
        matches = [
            record
            for record in records
            if _id(record) == expected_id and _name(record) == expected_name
        ]
        if len(matches) != 1:
            raise ValueError(
                f"expected exactly one version-file record for {expected_id} {expected_name!r}; "
                f"found {len(matches)}"
            )
        digest = _digest(matches[0])
        if digest is None:
            raise ValueError(f"version-file record lacks checksum for {expected_name}.")
        enriched = dict(payload)
        enriched["digest"] = digest
        enriched["version_api_url"] = version_url
        enriched["version_files_api_url"] = files_url
        enriched["version_file_record"] = dict(matches[0])
        path.write_text(
            json.dumps(enriched, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"file_id": expected_id, "name": expected_name, "digest": digest}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    resolve(args.files, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
