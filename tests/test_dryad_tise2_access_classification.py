from __future__ import annotations

from scripts import run_dryad_tise2_saed_hrtem_audit as runner


def test_html_bytes_are_classified_without_text_decoding() -> None:
    assert runner._classification(
        200, "text/html; charset=utf-8", b"<!DOCTYPE html><html></html>"
    ) == "html_interstitial_not_archive"


def test_zip_magic_is_classified_as_archive_bytes() -> None:
    assert runner._classification(
        200, "application/octet-stream", b"PK\x03\x04fixture"
    ) == "archive_bytes_available"


def test_auth_and_forbidden_statuses_take_precedence() -> None:
    assert runner._classification(401, "text/html", b"<html>") == "authentication_required"
    assert runner._classification(403, "text/html", b"<html>") == "forbidden_to_automated_runner"
