from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.execute_public_carbon_multimodal_case import adapt_public_tga_air_source


def test_cp1252_tga_adapter_excludes_only_initial_stabilization(tmp_path: Path) -> None:
    source = tmp_path / "tga_cp1252.tab"
    frame = pd.DataFrame(
        {
            "Temperature (°C)": [20.90, 20.91, 20.88, 20.89, 21.00, 21.20, 21.40, 21.60, 21.80, 22.00],
            "Time (s)": [0, 3, 6, 9, 12, 15, 18, 21, 24, 27],
            "TG (mg)": [0] * 10,
            "TG blank (mg)": [0] * 10,
            "TG Corb (mg)": [0] * 10,
            "TG DWCNT (%)": [100, 100, 100, 100, 99.9, 99.8, 99.7, 99.6, 99.5, 99.4],
            "dTG DWCNT (% min-1)": [0] * 10,
        }
    )
    frame.to_csv(source, sep=";", index=False, encoding="cp1252")
    destination = tmp_path / "canonical.csv"
    record = adapt_public_tga_air_source(source, destination)
    canonical = pd.read_csv(destination)
    assert record["source_encoding"] == "cp1252"
    assert record["initial_stabilization_rows_excluded"] == 3
    assert canonical["temperature_c"].is_monotonic_increasing
    assert canonical.iloc[0]["temperature_c"] == 20.89
    assert "no sorting or interpolation" in record["heating_segment_rule"]
