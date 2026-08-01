from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "audit_public_zr15nb_dsc_source.py"
SPEC = importlib.util.spec_from_file_location("audit_public_zr15nb_dsc_source", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_record_files_supports_current_entries_shape() -> None:
    payload = {
        "files": {
            "entries": {
                "data.csv": {
                    "id": "file-1",
                    "size": 12,
                    "checksum": "md5:" + "a" * 32,
                    "links": {"content": "https://example.invalid/data.csv"},
                }
            }
        }
    }
    records = MODULE._record_files(payload)
    assert records == [
        {
            "filename": "data.csv",
            "size": 12,
            "checksum": "md5:" + "a" * 32,
            "content_url": "https://example.invalid/data.csv",
            "file_id": "file-1",
        }
    ]


def test_profile_table_resolves_three_row_headers_and_monotonic_runs() -> None:
    text = "\n".join(
        [
            "DSC,DSC,Resistance",
            "Temperature,Heat Flow,Resistance",
            "degC,mW,relative",
            "20,0.1,1.0",
            "25,0.2,0.9",
            "30,0.3,0.8",
        ]
    )
    summary, profiles = MODULE._profile_table(text)
    assert summary["delimiter"] == "comma"
    assert summary["data_row_count"] == 3
    assert summary["temperature_candidate_columns"] == [0]
    assert summary["dsc_candidate_columns"] == [0, 1]
    assert profiles[0]["longest_strictly_increasing_run"]["length"] == 3
    assert profiles[2]["longest_strictly_decreasing_run"]["length"] == 3


def test_verify_bytes_rejects_checksum_drift() -> None:
    payload = b"real source bytes"
    configured = {
        "filename": "data.csv",
        "role": "source",
        "expected_size_bytes": None,
        "checksum_algorithm": "md5",
        "checksum": hashlib.md5(payload).hexdigest(),
    }
    repository = {
        "size": len(payload),
        "checksum": "md5:" + hashlib.md5(payload).hexdigest(),
    }
    verified = MODULE._verify_bytes(
        payload,
        configured=configured,
        repository_record=repository,
    )
    assert verified["source_checksum_verified"]
    assert verified["downloaded_sha256"] == hashlib.sha256(payload).hexdigest()

    changed = dict(configured, checksum="0" * 32)
    with pytest.raises(MODULE.SourceAuditError, match="repository checksum differs"):
        MODULE._verify_bytes(
            payload,
            configured=changed,
            repository_record=repository,
        )


def test_longest_strict_run_does_not_sort_or_bridge_discontinuities() -> None:
    values = [20.0, 25.0, 30.0, 29.0, 31.0, 32.0]
    result = MODULE._longest_strict_run(values, increasing=True)
    assert result == {"start": 0, "end_exclusive": 3, "length": 3}
