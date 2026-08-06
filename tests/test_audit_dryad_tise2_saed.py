from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.audit_dryad_tise2_saed import (
    DryadTiSe2AuditError,
    _classify,
    _safe_member,
)


CONFIG = {
    "required_experimental_prefixes": ["Fig2_Data/"],
    "required_simulation_prefixes": ["Fig3_Data/", "Fig4_Data/"],
    "supplementary_prefixes": ["S1_Data/"],
    "allowed_image_suffixes": [".tif", ".bmp"],
    "allowed_table_suffixes": [".xlsx", ".txt"],
}


def test_classifies_experiment_and_simulation_separately() -> None:
    assert _classify("Fig2_Data/001_data.tif", CONFIG) == (
        "experimental",
        "raster_image",
    )
    assert _classify("Fig3_Data/model_data.bmp", CONFIG) == (
        "simulation",
        "raster_image",
    )
    assert _classify("S1_Data/ReadMe.txt", CONFIG) == (
        "supplementary_or_mixed",
        "table_or_text",
    )


def test_safe_member_rejects_parent_traversal() -> None:
    info = zipfile.ZipInfo("../escape.tif")
    with pytest.raises(DryadTiSe2AuditError, match="unsafe ZIP member path"):
        _safe_member(info)


def test_safe_member_normalizes_windows_separator() -> None:
    info = zipfile.ZipInfo("Fig2_Data\\001_data.tif")
    assert _safe_member(info) == "Fig2_Data/001_data.tif"
