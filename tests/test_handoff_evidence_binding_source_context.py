from __future__ import annotations

from mca.handoff_validation.evidence_binding import _collect_source_record_sha256_values


CONFIG_DIGEST = "b" * 64
SOURCE_DIGEST = "a" * 64


def test_nist_case_config_checksum_is_not_feature_source_digest() -> None:
    source = {
        "tracked_inputs": {
            "case_config": {
                "path": "case_config.json",
                "sha256": CONFIG_DIGEST,
            },
            "measurement_source": {
                "path": "measurements.csv",
                "sha256": SOURCE_DIGEST,
            },
        }
    }

    assert _collect_source_record_sha256_values(source) == {SOURCE_DIGEST}


def test_rwgs_root_modality_record_is_feature_source_digest() -> None:
    source = {
        "xrd": {
            "path": "xrd_5wt.asc",
            "sha256": SOURCE_DIGEST,
        }
    }

    assert _collect_source_record_sha256_values(source) == {SOURCE_DIGEST}


def test_public_carbon_downloaded_bytes_digest_is_feature_source_digest() -> None:
    source = {
        "downloads": {
            "raman": {
                "status": "downloaded",
                "local_path": "raw/raman_source.txt",
                "download_url": "https://example.invalid/file",
                "downloaded_sha256": SOURCE_DIGEST,
            }
        }
    }

    assert _collect_source_record_sha256_values(source) == {SOURCE_DIGEST}
