from __future__ import annotations

import pytest

from scripts import run_mendeley_lunar_tem_saed_audit as runner
from scripts.audit_mendeley_lunar_tem_saed import MendeleyAuditError


def test_visible_text_excludes_script_and_style_content() -> None:
    raw = (
        b"<html><head><style>hidden-style</style><script>hidden-script</script></head>"
        b"<body><h1>Dataset title</h1><p>CC BY 4.0</p></body></html>"
    )
    text = runner.visible_text(raw)
    assert "Dataset title" in text
    assert "CC BY 4.0" in text
    assert "hidden-style" not in text
    assert "hidden-script" not in text


@pytest.mark.parametrize(
    ("status", "content_type", "sample", "expected"),
    [
        (401, "application/json", b'{"message":"Unauthorized"}', "oauth_authorization_required"),
        (403, "text/html", b"<html></html>", "forbidden"),
        (404, "application/json", b"{}", "not_found"),
        (200, "application/json", b"{}", "json_response"),
        (200, "text/html", b"<html></html>", "html_response"),
        (307, "application/octet-stream", b"", "other_success_response"),
    ],
)
def test_api_response_classification(
    status: int, content_type: str, sample: bytes, expected: str
) -> None:
    assert runner._classification(status, content_type, sample) == expected


def test_documented_endpoint_set_is_complete() -> None:
    source = {"dataset_id": "fcwyz3kv3k", "version": 1}
    endpoints = dict(runner._api_endpoints(source))
    assert set(endpoints) == {
        "dataset_metadata",
        "dataset_snapshot",
        "dataset_versions",
        "public_files",
        "public_folders",
        "zip_metadata",
        "zip_download_redirect",
    }
    assert all(url.startswith("https://api.data.mendeley.com/") for url in endpoints.values())


def test_untrusted_landing_url_fails_closed() -> None:
    with pytest.raises(MendeleyAuditError, match="untrusted Mendeley landing"):
        runner._trusted_landing_url("https://example.org/datasets/x/1")
