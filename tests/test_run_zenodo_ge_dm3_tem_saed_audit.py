from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts import run_zenodo_ge_dm3_tem_saed_audit as runner
from scripts.audit_zenodo_ge_dm3_tem_saed import ZenodoGeDm3AuditError


def _dm3_bytes() -> bytes:
    return (
        b"\x00\x00\x00\x03"
        b"\x00\x00\x00\x0c"
        b"\x00\x00\x00\x01"
        b"dm3-payload"
    )


def test_exiftool_exit_one_with_complete_system_json_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "selected"
    source = root / "Figure 3" / "d1 diff.dm3"
    source.parent.mkdir(parents=True)
    source.write_bytes(_dm3_bytes())

    payload = [
        {
            "SourceFile": str(source),
            "ExifTool:Error": "Unknown file type",
            "ExifTool:ExifToolVersion": 12.76,
            "System:FileName": source.name,
            "System:FileSize": "23 bytes",
        }
    ]

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout=json.dumps(payload),
            stderr=f"15 image files read - {source}\n",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    rows = runner.inspect_dm3_metadata_with_warning_capture(
        [source], root, "/usr/bin/exiftool"
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["member_path"] == "Figure 3/d1 diff.dm3"
    assert row["sha256"] == hashlib.sha256(_dm3_bytes()).hexdigest()
    assert row["dm3_header_version"] == 3
    assert row["dm3_header_byte_order_marker"] == 1
    assert row["embedded_microscopy_metadata_field_count"] == 0
    assert row["embedded_microscopy_metadata_keys"] == []
    assert row["exiftool_exit_code"] == 1
    assert row["exiftool_error"] == "Unknown file type"
    assert row["exiftool_stderr_line_count"] == 1
    assert all(
        str(root.resolve()) not in item for item in row["exiftool_stderr_lines"]
    )
    assert "<transient-source-root>" in row["exiftool_stderr_lines"][0]


def test_dm3_header_version_mismatch_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "not-dm3.dm3"
    source.write_bytes(
        b"\x00\x00\x00\x04"
        b"\x00\x00\x00\x0c"
        b"\x00\x00\x00\x01"
    )
    with pytest.raises(ZenodoGeDm3AuditError, match="version marker mismatch"):
        runner.probe_dm3_header(source)


def test_exiftool_exit_one_without_json_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "selected"
    source = root / "pattern.dm3"
    root.mkdir()
    source.write_bytes(_dm3_bytes())

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(
            args=args[0], returncode=1, stdout="", stderr="unsupported file"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ZenodoGeDm3AuditError, match="without JSON output"):
        runner.inspect_dm3_metadata_with_warning_capture(
            [source], root, "/usr/bin/exiftool"
        )


def test_exiftool_unexpected_exit_code_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "selected"
    source = root / "pattern.dm3"
    root.mkdir()
    source.write_bytes(_dm3_bytes())

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(
            args=args[0], returncode=2, stdout="[]", stderr="fatal error"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ZenodoGeDm3AuditError, match="unexpected code 2"):
        runner.inspect_dm3_metadata_with_warning_capture(
            [source], root, "/usr/bin/exiftool"
        )
