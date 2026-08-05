from __future__ import annotations

import pytest

from scripts import run_dryad_tise2_saed_hrtem_audit as runner
from scripts.audit_dryad_tise2_saed_hrtem import AuditError


def test_scalar_file_id_is_preferred() -> None:
    assert runner.record_id_with_link_fallback({"id": 4808550}) == 4808550


def test_file_id_is_resolved_from_self_link() -> None:
    record = {
        "_links": {
            "self": {"href": "/api/v2/files/4808550"},
            "stash:download": {"href": "/downloads/file_stream/4808550"},
        }
    }
    assert runner.record_id_with_link_fallback(record) == 4808550


def test_file_id_is_resolved_from_download_link() -> None:
    record = {
        "_links": {
            "stash:download": {"href": "https://datadryad.org/downloads/file_stream/4808551"}
        }
    }
    assert runner.record_id_with_link_fallback(record) == 4808551


def test_external_file_link_fails_closed() -> None:
    with pytest.raises(AuditError, match="pinned host"):
        runner.record_id_with_link_fallback(
            {"_links": {"self": {"href": "https://example.org/api/v2/files/4808550"}}}
        )
