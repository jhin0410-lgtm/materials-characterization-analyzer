from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from mca.tem_parent_overlap_io import _validate_zip


def test_zip_contract_accepts_safe_metadata_and_member_order(tmp_path: Path) -> None:
    archive_path = tmp_path / "source.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("b_TEM_images.h5", b"b")
        archive.writestr("__MACOSX/._b_TEM_images.h5", b"metadata")
        archive.writestr("a_TEM_images.h5", b"a")

    inventory = _validate_zip(
        archive_path,
        ("a_TEM_images.h5", "b_TEM_images.h5"),
    )

    assert inventory["members"] == ["a_TEM_images.h5", "b_TEM_images.h5"]
    assert inventory["member_count"] == 2
    assert inventory["metadata_member_count"] == 1
    assert inventory["metadata_members"] == ["__MACOSX/._b_TEM_images.h5"]
    assert inventory["safe_paths_verified"]
    assert inventory["symlinks_absent"]


def test_zip_contract_rejects_unexpected_data_member(tmp_path: Path) -> None:
    archive_path = tmp_path / "source.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("a_TEM_images.h5", b"a")
        archive.writestr("unexpected_TEM_images.h5", b"unexpected")

    with pytest.raises(ValueError, match="unexpected"):
        _validate_zip(archive_path, ("a_TEM_images.h5",))
