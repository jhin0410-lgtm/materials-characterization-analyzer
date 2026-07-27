from pathlib import Path

import pytest

from scripts.run_public_carbon_four_materials_case import load_json


DWCNT_CONFIG = Path("case_studies/public_carbon_multimodal/case_config.json")


def test_single_sample_dwcnt_config_preserves_source_tga_mass_meanings() -> None:
    config = load_json(DWCNT_CONFIG)
    metadata = config["acquisition_metadata"]["tga"]

    assert metadata["sample_mass_mg"] == pytest.approx(3.531)
    assert metadata["sample_mass_definition"].startswith("W_sa")
    assert metadata["dry_air_purge_mass_change_mg"] == pytest.approx(0.0247)
    assert metadata["dry_air_purge_mass_change_definition"].startswith("W_sp")
    assert metadata["helium_purge_starting_sample_mass_mg"] == pytest.approx(3.605)
    assert metadata["helium_purge_starting_sample_mass_definition"].startswith("W_sm")
    assert metadata["empty_crucible_mass_inferred"] is False
    assert metadata["sample_plus_crucible_mass_inferred"] is False
    assert "reported_empty_crucible_mass_mg" not in metadata
    assert "reported_sample_plus_crucible_mass_mg" not in metadata
