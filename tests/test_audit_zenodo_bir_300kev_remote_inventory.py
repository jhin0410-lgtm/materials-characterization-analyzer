from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from scripts import audit_zenodo_bir_300kev_remote_inventory as audit


def _zip_bytes(names: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, name in enumerate(names):
            archive.writestr(name, f"fixture-{index}".encode())
    return buffer.getvalue()


def _parse_fixture(names: list[str]) -> tuple[dict[str, int], list[dict[str, Any]]]:
    payload = _zip_bytes(names)
    tail_size = min(131072, len(payload))
    eocd = audit.parse_eocd(payload[-tail_size:], archive_size=len(payload))
    start = eocd["central_directory_offset"]
    end = start + eocd["central_directory_bytes"]
    records = audit.parse_central_directory(
        payload[start:end],
        expected_entries=eocd["entries_total"],
        limits={
            "maximum_member_count": 200000,
            "maximum_filename_bytes": 4096,
            "maximum_extra_bytes": 65535,
            "maximum_comment_bytes": 65535,
        },
    )
    return eocd, records


def test_zip_inventory_detects_conventional_tvips_split_stream_and_main_file() -> None:
    eocd, records = _parse_fixture(
        [
            "AVAAGA/crystalA_000.tvips",
            "AVAAGA/crystalA_001.tvips",
            "AVAAGA/crystalA_002.tvips",
            "README.txt",
        ]
    )
    summary = audit.summarize_inventory(records, central_sha256="a" * 64)

    assert eocd["entries_total"] == 4
    assert summary["member_count"] == 4
    assert summary["tvips_member_count"] == 3
    assert summary["tvips_split_stream_member_count"] == 3
    assert summary["tvips_split_stream_series_count"] == 1
    assert summary["tvips_split_stream_main_file_count"] == 1
    assert summary["tvips_split_series_missing_main_count"] == 0
    assert summary["tvips_split_main_paths"] == ["AVAAGA/crystalA_000.tvips"]


def test_tvips_split_stream_without_zero_file_is_reported_not_inferred() -> None:
    _, records = _parse_fixture(
        [
            "AVAAGA/crystalB_001.tvips",
            "AVAAGA/crystalB_002.tvips",
        ]
    )
    summary = audit.summarize_inventory(records, central_sha256="b" * 64)

    assert summary["tvips_split_stream_series_count"] == 1
    assert summary["tvips_split_stream_main_file_count"] == 0
    assert summary["tvips_split_series_missing_main_count"] == 1
    assert summary["tvips_split_series_missing_main"] == ["crystalB"]


def test_standalone_named_tvips_members_are_not_promoted_to_split_stream_series() -> None:
    _, records = _parse_fixture(
        [
            "AVAAGA/static_series1.tvips",
            "AVAAGA/static_series2.tvips",
            "AVAAGA/static_series3.tvips",
        ]
    )
    summary = audit.summarize_inventory(records, central_sha256="c" * 64)

    assert summary["tvips_member_count"] == 3
    assert summary["tvips_nonstandard_filename_count"] == 3
    assert summary["tvips_split_stream_member_count"] == 0
    assert summary["tvips_split_stream_series_count"] == 0
    assert summary["tvips_split_stream_main_file_count"] == 0


def test_central_directory_preserves_unsafe_path_as_flag() -> None:
    _, records = _parse_fixture(["../unsafe_000.tvips", "safe_000.tvips"])
    assert sum(record["unsafe_path"] for record in records) == 1


def test_fetch_range_refuses_http_200_without_reading_full_payload(monkeypatch) -> None:
    class FakeResponse:
        status = 200
        headers: dict[str, str] = {}
        read_called = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def getcode(self):
            return self.status

        def geturl(self):
            return "https://zenodo.org/api/records/10995139/files/x/content"

        def read(self, _size=-1):
            self.read_called = True
            return b"x" * 100

    response = FakeResponse()
    monkeypatch.setattr(audit.urllib.request, "urlopen", lambda *_args, **_kwargs: response)

    with pytest.raises(audit.Bir300RemoteInventoryError, match="full-download fallback"):
        audit.fetch_range(
            "https://zenodo.org/api/records/10995139/files/x/content",
            start=0,
            end=9,
            expected_total=100,
        )
    assert response.read_called is False


def test_fetch_range_accepts_exact_http_206(monkeypatch) -> None:
    class FakeResponse:
        status = 206
        headers = {"Content-Range": "bytes 10-19/100"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def getcode(self):
            return self.status

        def geturl(self):
            return "https://zenodo.org/api/records/10995139/files/x/content"

        def read(self, size=-1):
            assert size == 11
            return b"0123456789"

    monkeypatch.setattr(
        audit.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    result = audit.fetch_range(
        "https://zenodo.org/api/records/10995139/files/x/content",
        start=10,
        end=19,
        expected_total=100,
    )
    assert result == b"0123456789"


def test_repository_config_is_bounded_to_smallest_archive() -> None:
    path = Path("case_studies/zenodo_bir_300kev_saed_remote_inventory/case_config.json")
    config = audit.validate_config(json.loads(path.read_text(encoding="utf-8")))
    assert config["target_archive"]["key"] == "AVAAGA_300kV_293K.zip"
    assert config["target_archive"]["expected_bytes"] == 3527509304
    assert config["scientific_boundary"]["full_archive_download_authorized"] is False
    assert config["scientific_boundary"]["archive_member_payload_download_authorized"] is False
