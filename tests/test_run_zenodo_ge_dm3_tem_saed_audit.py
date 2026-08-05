from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts import run_zenodo_ge_dm3_tem_saed_audit as runner
from scripts.audit_zenodo_ge_dm3_tem_saed import ZenodoGeDm3AuditError


def test_exiftool_exit_one_with_complete_json_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "selected"
    source = root / "Figure 3" / "d1 diff.dm3"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"dm3-placeholder")

    payload = [
        {
            "SourceFile": str(source),
            "File:FileType": "DM3",
            "File:FileSize": "15 bytes",
        }
    ]

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout=json.dumps(payload),
            stderr=f"Warning: metadata note - {source}\n    1 image files read\n",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    rows = runner.inspect_dm3_metadata_with_warning_capture(
        [source], root, "/usr/bin/exiftool"
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["member_path"] == "Figure 3/d1 diff.dm3"
    assert row["sha256"] == hashlib.sha256(b"dm3-placeholder").hexdigest()
    assert row["exiftool_exit_code"] == 1
    assert row["exiftool_warning_count"] == 2
    assert all(str(root.resolve()) not in item for item in row["exiftool_warnings"])
    assert "<transient-source-root>" in row["exiftool_warnings"][0]


def test_exiftool_exit_one_without_json_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "selected"
    source = root / "pattern.dm3"
    root.mkdir()
    source.write_bytes(b"dm3-placeholder")

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
    source.write_bytes(b"dm3-placeholder")

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(
            args=args[0], returncode=2, stdout="[]", stderr="fatal error"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ZenodoGeDm3AuditError, match="unexpected code 2"):
        runner.inspect_dm3_metadata_with_warning_capture(
            [source], root, "/usr/bin/exiftool"
        )
