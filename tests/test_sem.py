from pathlib import Path

from mca.sem import analyze_sem


DATA = Path(__file__).resolve().parents[1] / "data" / "demo" / "synthetic_sem.png"


def test_sem_analysis_runs_without_empty_measurements(tmp_path):
    result = analyze_sem(DATA, tmp_path, microns_per_pixel=0.05, min_area_pixels=10)
    assert result["overlay_path"].exists()
    assert result["histogram_path"].exists()
    assert result["measurements_path"].exists()
    assert len(result["measurements"]) > 0
    assert result["measurements"]["equivalent_diameter_microns"].max() > 0
