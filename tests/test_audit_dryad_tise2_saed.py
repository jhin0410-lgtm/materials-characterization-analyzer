from __future__ import annotations

import zipfile

import pytest

from scripts.audit_dryad_tise2_saed import (
    DryadTiSe2AuditError,
    _classify,
    _normalize_title,
    _safe_member,
    _title_matches,
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


def test_classifies_partition_below_archive_wrapper_directory() -> None:
    assert _classify(
        "Data_TiSe2/Fig2_Data/001_data.tif",
        CONFIG,
    ) == ("experimental", "raster_image")


def test_title_identity_normalizes_markup_and_subscripts() -> None:
    title = (
        "Data from: Revisiting the charge-density-wave superlattice "
        "of 1<em>T</em>-TiSe<sub>2</sub>"
    )
    tokens = [
        "Revisiting",
        "charge-density-wave",
        "superlattice",
        "1T-TiSe2",
    ]
    assert _title_matches(title, tokens)
    assert "1ttise2" in _normalize_title(title)


def test_safe_member_rejects_parent_traversal() -> None:
    info = zipfile.ZipInfo("../escape.tif")
    with pytest.raises(DryadTiSe2AuditError, match="unsafe ZIP member path"):
        _safe_member(info)


def test_safe_member_normalizes_windows_separator() -> None:
    info = zipfile.ZipInfo("Fig2_Data\\001_data.tif")
    assert _safe_member(info) == "Fig2_Data/001_data.tif"
