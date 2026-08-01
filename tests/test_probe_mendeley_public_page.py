from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "probe_mendeley_public_page.py"
SPEC = importlib.util.spec_from_file_location("probe_mendeley_public_page", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_sanitize_url_removes_query_and_fragment() -> None:
    value = MODULE._sanitize_url(
        "https://data.mendeley.com/public-files/datasets/8w66synjmx/file?"
        "X-Amz-Signature=secret&token=also-secret#fragment"
    )
    assert value == (
        "https://data.mendeley.com/public-files/datasets/8w66synjmx/file"
    )


def test_relevant_url_clues_never_store_signed_query_values() -> None:
    text = (
        "https://data.mendeley.com/public-files/datasets/8w66synjmx/file?"
        "X-Amz-Signature=secret&X-Amz-Credential=credential"
    )
    clues = MODULE._clues(text, "8w66synjmx")
    encoded = " ".join(clues["relevant_urls"])
    assert "?" not in encoded
    assert "secret" not in encoded
    assert "Credential" not in encoded
