from pathlib import Path

from mca.xrd import analyze_xrd, detect_peaks, read_xrd_csv, smooth_intensity


DATA = Path(__file__).resolve().parents[1] / "data" / "demo" / "synthetic_xrd.csv"


def test_xrd_csv_can_be_read():
    xrd = read_xrd_csv(DATA)
    assert {"two_theta", "intensity"}.issubset(xrd.columns)
    assert len(xrd) > 0


def test_peak_detection_finds_synthetic_peaks():
    xrd = read_xrd_csv(DATA)
    smoothed = smooth_intensity(xrd["intensity"], window_length=7, polyorder=2)
    peaks = detect_peaks(
        xrd["two_theta"],
        xrd["intensity"],
        smoothed,
        prominence_fraction=0.1,
        min_distance=4,
    )
    assert len(peaks) >= 3
    assert "fwhm_deg_2theta" in peaks.columns


def test_xrd_output_files_are_created(tmp_path):
    result = analyze_xrd(
        DATA,
        tmp_path,
        smoothing_window=7,
        smoothing_polyorder=2,
        prominence_fraction=0.1,
        min_distance=4,
    )
    assert result["plot_path"].exists()
    assert result["peak_table_path"].exists()
    assert len(result["peak_table"]) >= 3
