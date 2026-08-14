from __future__ import annotations

from mca.handoff_validation.evidence_binding import _collect_source_record_sha256_values


AUDIT_DIGEST = "b" * 64
SOURCE_DIGEST = "a" * 64


def test_root_audit_file_checksum_is_not_feature_source_digest() -> None:
    source = {
        "audit": {
            "path": "audit.json",
            "sha256": AUDIT_DIGEST,
        },
        "xrd": {
            "path": "measurement.asc",
            "sha256": SOURCE_DIGEST,
        },
    }

    assert _collect_source_record_sha256_values(source) == {SOURCE_DIGEST}


def test_root_single_file_source_manifest_remains_supported() -> None:
    source = {
        "path": "measurement.csv",
        "sha256": SOURCE_DIGEST,
    }

    assert _collect_source_record_sha256_values(source) == {SOURCE_DIGEST}
