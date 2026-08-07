from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import audit_zenodo_srtio3_notebook_provenance as audit


def _config_payload() -> dict:
    return json.loads(
        Path("case_studies/zenodo_srtio3_notebook_provenance/case_config.json").read_text(
            encoding="utf-8"
        )
    )


def test_repository_contract_is_bounded_to_verified_notebook() -> None:
    config = audit._validate_config(_config_payload())
    source = config["source_file"]
    assert source["key"] == "Kikuchi_COM.ipynb"
    assert source["expected_bytes"] == 1711932
    assert source["expected_md5"] == "56383d23c198347220ed751ddb3dbae5"
    assert source["maximum_download_bytes"] <= 2_000_000
    assert config["scientific_boundary"]["inspect_notebook_outputs_authorized"] is False
    assert config["scientific_boundary"]["four_d_stem_download_authorized"] is False
    assert config["scientific_boundary"]["saed_tiff_pixel_access_authorized"] is False


def test_search_uses_only_markdown_and_code_sources() -> None:
    config = audit._validate_config(_config_payload())
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "source": ["SAED at 23 K is discussed here.\n"],
            },
            {
                "cell_type": "code",
                "source": ["background = image.mean()\n", "# camera length calibration\n"],
                "outputs": [{"text": ["172K hidden only in output"]}],
            },
            {
                "cell_type": "raw",
                "source": ["91K hidden in raw cell"],
            },
        ]
    }
    hits, categories, terms, inventory = audit._search_cells(notebook, config["search_terms"])
    assert categories["saed_identity"] >= 2
    assert categories["preprocessing"] >= 1
    assert categories["calibration"] >= 1
    assert terms["saed_identity:172K"] == 0
    assert terms["saed_identity:91K"] == 0
    assert inventory["code_cells_with_ignored_outputs"] == 1
    assert inventory["notebook_outputs_inspected"] is False
    assert all(hit["cell_type"] in {"markdown", "code"} for hit in hits)


def test_non_string_cell_source_is_rejected() -> None:
    with pytest.raises(audit.SrTiO3NotebookProvenanceError, match="cell source"):
        audit._cell_source_text({"source": ["ok", 3]})


def test_config_rejects_output_inspection_authorization() -> None:
    payload = _config_payload()
    payload["scientific_boundary"]["inspect_notebook_outputs_authorized"] = True
    with pytest.raises(audit.SrTiO3NotebookProvenanceError, match="must remain disabled"):
        audit._validate_config(payload)


def test_ascii_excerpt_is_bounded() -> None:
    line = "x" * 300 + " SAED " + "y" * 300
    excerpt = audit._excerpt(line, "SAED")
    assert "SAED" in excerpt
    assert len(excerpt) <= 242
