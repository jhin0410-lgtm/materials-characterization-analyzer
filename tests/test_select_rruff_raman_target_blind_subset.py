from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import select_rruff_raman_target_blind_subset as select


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "case_studies" / "rruff_raman_target_blind_subset_v1" / "selection_contract.json"


def _contract_payload() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_allows_only_rruff_ids_as_selection_input() -> None:
    config = select._validate_contract(_contract_payload())
    inputs = config["authorized_selection_inputs"]

    assert inputs["rruff_id_strings_only"] is True
    assert all(value is False for key, value in inputs.items() if key != "rruff_id_strings_only")
    operations = config["authorized_operations"]
    assert operations["compute_deterministic_hash_ranking"] is True
    assert operations["download_rruff_spectra"] is False
    assert operations["inspect_rruff_spectrum_metadata"] is False
    assert operations["run_mca_raman"] is False
    assert operations["tune_parameters_or_matching_tolerance"] is False
    assert operations["score_selected_ids"] is False
    assert operations["replace_selected_ids_from_performance"] is False


def test_pinned_inventory_contains_exact_55_unique_sorted_ids() -> None:
    config = select._validate_contract(_contract_payload())
    _, ids = select._load_eligible_ids(config)

    assert len(ids) == 55
    assert len(set(ids)) == 55
    assert ids == sorted(ids)


def test_hash_ranking_is_deterministic_and_uses_seed_plus_id_only() -> None:
    ids = ["R000003", "R000001", "R000002"]
    seed = "mca-rruff-peak-localization-v1"
    first = select._rank_ids(ids, seed)
    second = select._rank_ids(list(reversed(ids)), seed)

    assert first == second
    expected = sorted(
        (
            hashlib.sha256(f"{seed}:{rruff_id}".encode("utf-8")).hexdigest(),
            rruff_id,
        )
        for rruff_id in ids
    )
    assert [(row["sha256_rank_key"], row["rruff_id"]) for row in first] == expected
    assert [row["rank"] for row in first] == [1, 2, 3]


def test_run_selection_freezes_first_ten_and_remaining_replacement_order(tmp_path: Path) -> None:
    output = tmp_path / "selection.json"
    result = select.run_selection(config_path=CONTRACT, output_path=output)

    assert result["execution_status"] == "target_blind_rruff_subset_selected"
    assert result["source_inventory"]["eligible_id_count"] == 55
    assert result["selection_size"] == 10
    assert len(result["selected_ids"]) == 10
    assert len(result["replacement_order"]) == 45
    assert len(result["full_ranking"]) == 55
    assert result["selected_ids"] == [row["rruff_id"] for row in result["full_ranking"][:10]]
    assert result["replacement_order"] == [row["rruff_id"] for row in result["full_ranking"][10:]]
    assert set(result["selection_inputs_used"]) == {"rruff_id"}
    assert "peak_counts" in result["selection_inputs_not_used"]
    readiness = result["readiness"]
    assert readiness["target_blind_subset_frozen"] is True
    assert readiness["source_spectrum_download_authorized"] is False
    assert readiness["source_metadata_inspection_authorized"] is False
    assert readiness["raman_analyzer_execution_authorized"] is False
    assert readiness["parameter_or_tolerance_tuning_authorized"] is False
    assert readiness["validation_scoring_authorized"] is False
    assert readiness["external_validation_ready"] is False
    assert output.is_file()


def test_contract_rejects_peak_count_as_selection_input(tmp_path: Path) -> None:
    payload = _contract_payload()
    payload["authorized_selection_inputs"]["peak_counts"] = True
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(select.RruffTargetBlindSelectionError, match="non-ID inputs"):
        select._validate_contract(select._load_json(path))


def test_output_is_never_overwritten(tmp_path: Path) -> None:
    output = tmp_path / "selection.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(select.RruffTargetBlindSelectionError, match="overwrite"):
        select.run_selection(config_path=CONTRACT, output_path=output)
