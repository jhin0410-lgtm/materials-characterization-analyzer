from pathlib import Path

from mca.eds import analyze_eds, prepare_composition_table, read_eds_csv, summarize_eds


DATA = Path(__file__).resolve().parents[1] / "data" / "demo" / "synthetic_eds.csv"


def test_eds_csv_can_be_read_and_sorted():
    eds = read_eds_csv(DATA)
    table = prepare_composition_table(eds)
    assert {"element", "weight_percent", "atomic_percent"}.issubset(table.columns)
    assert table.iloc[0]["weight_percent"] >= table.iloc[-1]["weight_percent"]


def test_eds_summary_is_cautious():
    eds = read_eds_csv(DATA)
    summary = summarize_eds(eds)
    assert "does not confirm crystal phases" in summary


def test_eds_output_files_are_created(tmp_path):
    result = analyze_eds(DATA, tmp_path)
    assert result["table_path"].exists()
    assert result["chart_path"].exists()
    assert len(result["composition_table"]) > 0
