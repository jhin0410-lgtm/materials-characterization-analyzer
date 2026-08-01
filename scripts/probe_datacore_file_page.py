"""Record safe link and form metadata from a DataCORE file-set page."""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

USER_AGENT = "materials-characterization-analyzer-datacore-page-probe/1.0"
ALLOWED_HOST = "datacore.iu.edu"


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self.forms: list[dict[str, str]] = []
        self.inputs: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "a" and values.get("href"):
            self.links.append({"href": values["href"]})
        elif tag == "form":
            self.forms.append(
                {
                    "action": values.get("action", ""),
                    "method": values.get("method", "get").lower(),
                }
            )
        elif tag == "input":
            self.inputs.append(
                {
                    "name": values.get("name", ""),
                    "type": values.get("type", ""),
                    "value": values.get("value", ""),
                }
            )


def _safe_url(base: str, value: str) -> str | None:
    resolved = urllib.parse.urljoin(base, value)
    parsed = urllib.parse.urlsplit(resolved)
    if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
        return None
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.query, "")
    )


def run(*, url: str, output: Path) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = response.read()
        final_url = response.geturl()
        metadata = {
            "status": int(getattr(response, "status", 200)),
            "content_type": response.headers.get_content_type(),
            "content_length_header": response.headers.get("Content-Length"),
        }
    text = payload.decode("utf-8", errors="replace")
    parser = _Parser()
    parser.feed(text)

    links = sorted(
        {
            safe
            for item in parser.links
            if (safe := _safe_url(final_url, item["href"])) is not None
        }
    )
    forms = sorted(
        {
            (safe, item["method"])
            for item in parser.forms
            if (safe := _safe_url(final_url, item["action"] or final_url))
            is not None
        }
    )
    safe_inputs = [
        item
        for item in parser.inputs
        if item["type"] not in {"hidden", "password"}
        and item["name"] not in {"authenticity_token"}
    ]
    result = {
        "schema_version": "1.0",
        "case_id": "datacore_saed_file_page_probe",
        "requested_url": url.split("?", 1)[0],
        "resolved_url": final_url.split("?", 1)[0],
        "response": metadata,
        "html_bytes": len(payload),
        "html_sha256": hashlib.sha256(payload).hexdigest(),
        "same_origin_links": links,
        "same_origin_forms": [
            {"action": action, "method": method} for action, method in forms
        ],
        "nonsecret_inputs": safe_inputs[:100],
        "raw_html_persisted": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(url=args.url, output=args.output)
    print(
        json.dumps(
            {
                "links": len(result["same_origin_links"]),
                "forms": len(result["same_origin_forms"]),
            }
        )
    )


if __name__ == "__main__":
    main()
