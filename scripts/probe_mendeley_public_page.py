"""Probe public Mendeley landing pages for non-authenticated file metadata paths.

This diagnostic records hashes and endpoint clues, not full HTML/JavaScript bodies
or transient signed download URLs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

DATASET_IDS = ("8w66synjmx", "zhnbzhjrtr", "jz9dpgwwc3")
UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+")
ENDPOINT_TERMS = (
    "public-files/datasets",
    "api.data.mendeley.com",
    "/datasets/publics/",
    "/datasets/",
    "file_downloaded",
    "graphql",
    "files?",
)


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[str] = []
        self.json_blocks: list[dict[str, Any]] = []
        self._json_type = False
        self._json_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script":
            src = values.get("src")
            if src:
                self.scripts.append(src)
            script_type = values.get("type", "")
            self._json_type = script_type in {"application/json", "application/ld+json"}
            self._json_buffer = []

    def handle_data(self, data: str) -> None:
        if self._json_type:
            self._json_buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._json_type:
            raw = "".join(self._json_buffer).strip()
            if raw:
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = {"unparsed_sha256": hashlib.sha256(raw.encode()).hexdigest()}
                self.json_blocks.append(_sanitize(payload))
            self._json_type = False
            self._json_buffer = []


def _fetch(url: str) -> tuple[int, str, dict[str, str], bytes]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/javascript,*/*;q=0.8",
            "User-Agent": "materials-characterization-analyzer-mendeley-probe/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.status, response.geturl(), dict(response.headers.items()), response.read()


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
    if isinstance(value, str):
        if "X-Amz-" in value or "Signature=" in value:
            return "redacted_ephemeral_url"
    return value


def _clues(text: str, dataset_id: str) -> dict[str, Any]:
    uuids = sorted(set(UUID_PATTERN.findall(text)))
    urls = sorted(
        url.rstrip(".,);]")
        for url in set(URL_PATTERN.findall(text))
        if dataset_id in url or "mendeley" in url.lower()
    )
    endpoint_snippets: list[str] = []
    lowered = text.lower()
    for term in ENDPOINT_TERMS:
        start = 0
        while True:
            index = lowered.find(term.lower(), start)
            if index < 0:
                break
            snippet = text[max(0, index - 120) : min(len(text), index + 220)]
            snippet = re.sub(r"[?&](?:token|signature|x-amz-[^=&]+)=[^&\s\"']+", "&redacted=1", snippet, flags=re.I)
            endpoint_snippets.append(snippet)
            start = index + len(term)
            if len(endpoint_snippets) >= 50:
                break
        if len(endpoint_snippets) >= 50:
            break
    return {
        "uuid_count": len(uuids),
        "uuids": uuids[:200],
        "relevant_urls": urls[:100],
        "endpoint_snippets": endpoint_snippets,
    }


def probe(output: Path) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    assets_seen: set[str] = set()
    assets: list[dict[str, Any]] = []
    for dataset_id in DATASET_IDS:
        url = f"https://data.mendeley.com/datasets/{dataset_id}/1"
        status, final_url, headers, body = _fetch(url)
        text = body.decode("utf-8", errors="replace")
        parser = PageParser()
        parser.feed(text)
        script_urls = [urllib.parse.urljoin(final_url, src) for src in parser.scripts]
        pages.append(
            {
                "dataset_id": dataset_id,
                "status": status,
                "final_url": final_url,
                "content_type": headers.get("Content-Type", ""),
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
                "script_count": len(script_urls),
                "script_urls": script_urls,
                "json_blocks": parser.json_blocks,
                "clues": _clues(text, dataset_id),
            }
        )
        for script_url in script_urls:
            if script_url in assets_seen or len(assets) >= 80:
                continue
            assets_seen.add(script_url)
            try:
                asset_status, asset_final, asset_headers, asset_body = _fetch(script_url)
            except Exception as exc:  # diagnostic evidence, not a fatal source audit
                assets.append({"url": script_url, "error": type(exc).__name__})
                continue
            asset_text = asset_body.decode("utf-8", errors="replace")
            clue = _clues(asset_text, dataset_id)
            if clue["uuid_count"] or clue["endpoint_snippets"] or clue["relevant_urls"]:
                assets.append(
                    {
                        "url": script_url,
                        "final_url": asset_final,
                        "status": asset_status,
                        "content_type": asset_headers.get("Content-Type", ""),
                        "bytes": len(asset_body),
                        "sha256": hashlib.sha256(asset_body).hexdigest(),
                        "clues": clue,
                    }
                )
    result = {
        "schema_version": "1.0",
        "case_id": "mendeley_public_page_endpoint_probe",
        "pages": pages,
        "matching_assets": assets,
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
                "page_count": len(result["pages"]),
                "matching_asset_count": len(result["matching_assets"]),
                "page_uuid_counts": {
                    page["dataset_id"]: page["clues"]["uuid_count"]
                    for page in result["pages"]
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
