from __future__ import annotations

import hashlib
import zipfile
from io import BytesIO

import pytest

from scripts.discover_public_rwgs_xrd_sem_eds import (
    digest,
    extract_docx_text,
    extract_zip_safely,
    inventory_zip,
    summarize_archive,
    verify_md5,
)


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _docx_bytes(paragraphs: list[str]) -> bytes:
    body = "".join(
        f'<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>' for paragraph in paragraphs
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    ).encode("utf-8")
    return _zip_bytes({"word/document.xml": document})


def test_digest_and_md5_verification() -> None:
    payload = b"public-source"
    expected_md5 = hashlib.md5(payload).hexdigest()
    assert verify_md5(payload, expected_md5) == expected_md5
    assert digest(payload, "sha256") == hashlib.sha256(payload).hexdigest()


def test_md5_mismatch_is_fatal() -> None:
    with pytest.raises(RuntimeError, match="MD5 mismatch"):
        verify_md5(b"payload", "0" * 32)


def test_zip_inventory_and_safe_extraction(tmp_path) -> None:
    payload = _zip_bytes(
        {
            "sample/A.xy": b"10 100\n20 200\n",
            "sample/image.tif": b"II*\x00fake",
            "sample/eds.dat": b"Element wt at\n",
        }
    )
    inventory = inventory_zip(payload)
    assert {record["suffix"] for record in inventory} == {".xy", ".tif", ".dat"}
    summary = summarize_archive(inventory)
    assert summary["file_count"] == 3
    assert summary["suffix_counts"] == {".dat": 1, ".tif": 1, ".xy": 1}

    extracted = tmp_path / "extracted"
    extract_zip_safely(payload, extracted)
    assert (extracted / "sample" / "A.xy").read_text(encoding="utf-8").startswith("10")


def test_zip_path_traversal_is_rejected(tmp_path) -> None:
    payload = _zip_bytes({"../escape.txt": b"no"})
    with pytest.raises(ValueError, match="Unsafe ZIP member"):
        extract_zip_safely(payload, tmp_path)


def test_docx_plain_text_extraction() -> None:
    payload = _docx_bytes(["Catalyst A", "Calcined at 700 C"])
    assert extract_docx_text(payload) == "Catalyst A\nCalcined at 700 C"
