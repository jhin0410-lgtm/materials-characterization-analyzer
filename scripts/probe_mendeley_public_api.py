"""Probe the anonymous public API used by Mendeley Data landing pages.

The script records response status, content hashes, and sanitized JSON. It does
not download dataset file bytes or persist transient signed URLs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

DATASET_IDS = ("8w66synjmx", "zhnbzhjrtr", "jz9dpgwwc3")
BASE = "https://data.mendeley.com/public-api"


def _fetch(url: str, accept: str = "application/json") -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": "materials-characterization-analyzer-public-api-probe/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
            return _record(response.status, response.geturl(), response.headers, raw)
    except urllib.error.HTTPError as exc:
        return _record(exc.code, url, exc.headers, exc.read())
    except urllib.error.URLError as exc:
        return {
            "status": 0,
            "url_path": urllib.parse.urlsplit(url).path,
            "error": str(exc.reason),
        }


def _record(status: int, final_url: str, headers: Mapping[str, str], raw: bytes) -> dict[str, Any]:
    content_type = headers.get("Content-Type", "")
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {"non_json": True}
    return {
        "status": status,
        "url_path": urllib.parse.urlsplit(final_url).path,
        "content_type": content_type,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "payload": _sanitize(payload),
    }


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("download_url", "view_url", "expiry", "token")):
                result[key] = "redacted"
            else:
                result[key] = _sanitize(item)
        return result
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str) and ("X-Amz-" in value or "Signature=" in value):
        return "redacted_ephemeral_url"
    return value


def probe(output: Path) -> dict[str, Any]:
    datasets: list[dict[str, Any]] = []
    for dataset_id in DATASET_IDS:
        calls = {
            "snapshot": _fetch(f"{BASE}/datasets/{dataset_id}/snapshot/1"),
            "versions": _fetch(f"{BASE}/datasets/{dataset_id}/versions"),
            "files_omitted_folder": _fetch(
                f"{BASE}/datasets/{dataset_id}/files?version=1",
                "application/vnd.mendeley-public-dataset.1+json, application/json",
            ),
            "files_empty_folder": _fetch(
                f"{BASE}/datasets/{dataset_id}/files?folder_id=&version=1",
                "application/vnd.mendeley-public-dataset.1+json, application/json",
            ),
        }
        datasets.append({"dataset_id": dataset_id, "calls": calls})
    result = {
        "schema_version": "1.0",
        "case_id": "mendeley_anonymous_public_api_probe",
        "base": BASE,
        "datasets": datasets,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = probe(args.output)
    print(
        json.dumps(
            {
                dataset["dataset_id"]: {
                    name: record["status"]
                    for name, record in dataset["calls"].items()
                }
                for dataset in result["datasets"]
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
