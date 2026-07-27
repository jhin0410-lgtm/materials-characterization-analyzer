from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.run_public_carbon_four_materials_case import (
    _aggregate_case,
    _require_unique_samples,
    build_sample_config,
    load_json,
    run_case,
    select_exact_record,
)

CONFIG_PATH = Path("case_studies/public_carbon_four_materials/case_config.json")


def test_four_material_config_uses_unique_samples_and_exact_public_files() -> None:
    config = load_json(CONFIG_PATH)
    samples = _require_unique_samples(config)

    assert [sample["sample_id"] for sample in samples] == [
        "public-dwcnt",
        "public-mwcnt",
        "public-flg",
        "public-gnp",
    ]
    datafile_ids = []
    for sample in samples:
        assert set(sample["files"]) == {"raman", "ftir", "xps", "tga", "tem"}
        for record in sample["files"].values():
            assert isinstance(record["datafile_id"], int)
            assert record["expected_filename"]
            datafile_ids.append(record["datafile_id"])
        mass = sample["tga_mass_metadata"]
        assert mass["sample_mass_definition"].startswith("W_sa")
        assert mass["dry_air_purge_mass_change_definition"].startswith("W_sp")
        assert mass["helium_purge_starting_sample_mass_definition"].startswith("W_sm")
        assert "reported_empty_crucible_mass_mg" not in mass
        assert "reported_sample_plus_crucible_mass_mg" not in mass
    assert len(datafile_ids) == len(set(datafile_ids)) == 20
    assert config["readme_file"] == {
        "datafile_id": 184621,
        "expected_filename": "ReadMe_Raw.pdf",
    }


def test_select_exact_record_requires_matching_id_filename_and_access() -> None:
    inventory = [
        {
            "datafile_id": 101,
            "filename": "expected.tab",
            "restricted": False,
        }
    ]
    selected = select_exact_record(
        inventory,
        {"datafile_id": 101, "expected_filename": "expected.tab"},
        label="sample/raman",
    )
    assert selected["datafile_id"] == 101

    with pytest.raises(ValueError, match="filename mismatch"):
        select_exact_record(
            inventory,
            {"datafile_id": 101, "expected_filename": "changed.tab"},
            label="sample/raman",
        )
    with pytest.raises(ValueError, match="found 0"):
        select_exact_record(
            inventory,
            {"datafile_id": 999, "expected_filename": "expected.tab"},
            label="sample/raman",
        )
    inventory[0]["restricted"] = True
    with pytest.raises(ValueError, match="restricted"):
        select_exact_record(
            inventory,
            {"datafile_id": 101, "expected_filename": "expected.tab"},
            label="sample/raman",
        )


def test_build_sample_config_preserves_mass_semantics_and_tem_voltage() -> None:
    config = load_json(CONFIG_PATH)
    flg = next(sample for sample in config["samples"] if sample["sample_id"] == "public-flg")

    resolved = build_sample_config(config, flg)

    assert resolved["primary_sample"]["source_label"] == "FLG"
    assert resolved["modalities"]["xps"]["datafile_id"] == 184437
    assert resolved["modalities"]["xps"]["expected_filename"] == "20230710_XPS_WideScan_FLG.tab"
    assert resolved["acquisition_metadata"]["tem"]["accelerating_voltage_kv"] == 200.0
    tga = resolved["acquisition_metadata"]["tga"]
    assert tga["sample_mass_mg"] == pytest.approx(4.13)
    assert tga["dry_air_purge_mass_change_mg"] == pytest.approx(0.0027)
    assert tga["helium_purge_starting_sample_mass_mg"] == pytest.approx(4.404)
    assert resolved["suitability_gates"]["tem_quantitative_segmentation"]["allowed"] is False


def _feature(sample_id: str, instrument: str) -> dict[str, object]:
    hash_characters = {"raman": "a", "ftir": "b", "xps": "c", "tga": "d"}
    return {
        "sample_id": sample_id,
        "measurement_id": f"{sample_id}-{instrument}-public",
        "instrument": instrument,
        "feature_name": "candidate_count",
        "feature_label": None,
        "value": 1.0,
        "unit": "count",
        "method": "test_method",
        "source_file": f"source/{sample_id}/{instrument}.tab",
        "source_sha256": hash_characters[instrument] * 64,
        "preprocessing_id": f"{sample_id}-{instrument}-preprocessing",
        "quality_flag": "review_required",
    }


def test_aggregate_case_writes_four_sample_bundle_from_persisted_manifests(
    tmp_path: Path,
) -> None:
    config = load_json(CONFIG_PATH)
    sample_records = []
    for sample in config["samples"]:
        result_dir = tmp_path / "samples" / sample["sample_id"] / "result"
        result_dir.mkdir(parents=True)
        analyses = []
        for instrument in ("raman", "ftir", "xps", "tga"):
            feature = _feature(sample["sample_id"], instrument)
            analyses.append(
                {
                    "schema_version": "1.0",
                    "measurement_id": f"{sample['sample_id']}-{instrument}-public",
                    "sample_id": sample["sample_id"],
                    "instrument": instrument,
                    "source_file": feature["source_file"],
                    "source_sha256": feature["source_sha256"],
                    "acquisition_metadata": {},
                    "preprocessing_steps": [],
                    "tables": {},
                    "figures": {},
                    "features": [feature],
                    "warnings": ["review_required"],
                    "limitations": ["test limitation"],
                    "software_version": "test",
                }
            )
        (result_dir / "case_analysis_manifest.json").write_text(
            json.dumps({"schema_version": "1.0", "analysis_count": 4, "analyses": analyses}),
            encoding="utf-8",
        )
        (result_dir / "case_source_manifest.json").write_text(
            json.dumps({"sample_id": sample["sample_id"], "exact_selection": True}),
            encoding="utf-8",
        )
        pd.DataFrame(
            {
                "modality": ["raman", "ftir", "xps", "tga", "tem", "saed", "dsc"],
                "comparability_status": [
                    "conditionally_comparable",
                    "conditionally_comparable",
                    "conditionally_comparable",
                    "conditionally_comparable",
                    "source_available_analysis_blocked",
                    "not_available_not_comparable",
                    "not_available_not_comparable",
                ],
            }
        ).to_csv(result_dir / "comparability_matrix.csv", index=False)
        sample_records.append(
            {
                "sample_id": sample["sample_id"],
                "source_label": sample["source_label"],
                "material_class": sample["material_class"],
                "result_dir": str(result_dir),
            }
        )

    outputs = _aggregate_case(config, tmp_path, sample_records)

    bundle = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    assert bundle["feature_table"]["sample_count"] == 4
    assert bundle["feature_table"]["measurement_count"] == 16
    assert bundle["feature_table"]["row_count"] == 16
    assert bundle["feature_table"]["instruments"] == ["ftir", "raman", "tga", "xps"]
    context = pd.read_csv(outputs["sample_context"])
    assert set(context["sample_id"]) == {
        "public-dwcnt",
        "public-mwcnt",
        "public-flg",
        "public-gnp",
    }
    assert not context["controlled_process_variable_confirmed"].astype(bool).any()
    assert not context["process_response_model_allowed"].astype(bool).any()


def test_run_case_rejects_nonempty_output_before_network_access(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError, match="existing files were preserved"):
        run_case(CONFIG_PATH, output)

    assert sentinel.read_text(encoding="utf-8") == "preserve"
