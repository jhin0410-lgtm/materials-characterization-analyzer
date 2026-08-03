from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import shutil
import struct
import tempfile
import urllib.request
import zlib
from pathlib import Path
from typing import Any, Mapping

import h5py
import numpy as np

USER_AGENT = "materials-characterization-analyzer-source-audit/1.0"
SCHEMA_VERSION = "1.0"
CASE_ID = "zenodo_8132804_co3o4_mn3o4_audit"
RECORD_API = "https://zenodo.org/api/records/{record_id}"


class AuditContractError(ValueError):
    """Raised when the pinned audit contract or live source changes."""


def _json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AuditContractError("case config must contain a JSON object")
    return payload


def _require_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise AuditContractError(f"{key} must be an object")
    return value


def _require_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AuditContractError(f"{key} must be non-empty text")
    return value.strip()


def _require_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise AuditContractError(f"{key} must be an integer")
    return value


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("case_id") != CASE_ID:
        raise AuditContractError("case_id mismatch")
    source = _require_mapping(config, "source")
    bounded = _require_mapping(config, "bounded_transfer")
    members = config.get("members")
    expected = _require_mapping(config, "expected_disposition")
    if source.get("record_id") != "8132804":
        raise AuditContractError("record_id mismatch")
    if source.get("doi") != "10.5281/zenodo.8132804":
        raise AuditContractError("DOI mismatch")
    if source.get("archive_name") != "Multi_Modal_Data_Fusion_Chemical_Tomography.zip":
        raise AuditContractError("archive name mismatch")
    if _require_int(source, "archive_bytes") <= 0:
        raise AuditContractError("archive_bytes must be positive")
    archive_md5 = _require_text(source, "archive_md5").casefold()
    if len(archive_md5) != 32 or any(ch not in "0123456789abcdef" for ch in archive_md5):
        raise AuditContractError("archive_md5 must be hexadecimal")
    if bounded.get("full_archive_download_permitted") is not False:
        raise AuditContractError("full archive download must remain prohibited")
    if _require_int(bounded, "maximum_compressed_member_bytes") <= 0:
        raise AuditContractError("member transfer budget must be positive")
    if not isinstance(members, list) or len(members) != 2:
        raise AuditContractError("exactly two bounded HDF5 members are required")
    seen: set[str] = set()
    for index, raw_member in enumerate(members):
        if not isinstance(raw_member, Mapping):
            raise AuditContractError(f"members[{index}] must be an object")
        path = _require_text(raw_member, "path")
        if path in seen or path.startswith("/") or ".." in Path(path).parts:
            raise AuditContractError(f"unsafe or duplicate member path: {path}")
        seen.add(path)
        if not path.endswith(".h5"):
            raise AuditContractError("bounded member must be HDF5")
        for key in ("local_header_offset", "compressed_bytes", "uncompressed_bytes"):
            if _require_int(raw_member, key) <= 0:
                raise AuditContractError(f"{key} must be positive")
        crc32 = _require_text(raw_member, "crc32").casefold()
        sha256 = _require_text(raw_member, "uncompressed_sha256").casefold()
        if len(crc32) != 8 or any(ch not in "0123456789abcdef" for ch in crc32):
            raise AuditContractError("member crc32 must be hexadecimal")
        if len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256):
            raise AuditContractError("member sha256 must be hexadecimal")
        expected_datasets = _require_mapping(raw_member, "expected_datasets")
        if not expected_datasets:
            raise AuditContractError("expected_datasets must be non-empty")
    total_compressed = sum(int(item["compressed_bytes"]) for item in members)
    if total_compressed > int(bounded["maximum_compressed_member_bytes"]):
        raise AuditContractError("bounded members exceed transfer budget")
    if expected.get("external_validation_ready") is not False:
        raise AuditContractError("expected disposition must remain fail closed")
    if expected.get("model_inference_permitted") is not False:
        raise AuditContractError("model inference must remain prohibited")


def _fetch_record(record_id: str) -> tuple[dict[str, Any], bytes]:
    request = urllib.request.Request(
        RECORD_API.format(record_id=record_id),
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        if int(response.status) != 200:
            raise RuntimeError(f"unexpected Zenodo API status: {response.status}")
        raw = response.read()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError("Zenodo API response is not an object")
    return payload, raw


def _archive_content_url(record: Mapping[str, Any], source: Mapping[str, Any]) -> str:
    if str(record.get("id")) != str(source["record_id"]):
        raise RuntimeError("Zenodo record identity mismatch")
    if str(record.get("doi", "")).casefold() != str(source["doi"]).casefold():
        raise RuntimeError("Zenodo DOI mismatch")
    if str(record.get("conceptdoi", "")).casefold() != str(source["concept_doi"]).casefold():
        raise RuntimeError("Zenodo concept DOI mismatch")
    metadata = record.get("metadata")
    if not isinstance(metadata, Mapping):
        raise RuntimeError("Zenodo metadata missing")
    if str(metadata.get("version", "")) != str(source["version"]):
        raise RuntimeError("Zenodo version mismatch")
    metadata_text = json.dumps(metadata, ensure_ascii=False).casefold()
    if not any(marker in metadata_text for marker in ("cc-by-4.0", "creativecommons.org/licenses/by/4.0")):
        raise RuntimeError("CC BY 4.0 licence not resolved")
    files = record.get("files")
    if not isinstance(files, list) or len(files) != 1:
        raise RuntimeError("unexpected Zenodo file inventory")
    item = files[0]
    if not isinstance(item, Mapping):
        raise RuntimeError("invalid Zenodo file record")
    if item.get("key") != source["archive_name"]:
        raise RuntimeError