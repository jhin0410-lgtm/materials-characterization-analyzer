from pathlib import Path

import pytest

from mca.importers import load_eds_composition_table, load_xrd_file


DATA = Path(__file__).resolve().parents[1] / "data" / "demo"


def _write_text(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_load_xrd_demo_csv_succeeds():
    xrd = load_xrd_file(DATA / "synthetic_xrd.csv")
    assert list(xrd.columns) == ["two_theta", "intensity"]
    assert len(xrd) > 3


def test_load_xrd_header_csv_succeeds(tmp_path):
    path = _write_text(
        tmp_path / "pattern.csv",
        "2 theta,counts\n10,100\n20,200\n30,150\n",
    )
    xrd = load_xrd_file(path)
    assert list(xrd.columns) == ["two_theta", "intensity"]
    assert xrd["two_theta"].tolist() == [10, 20, 30]


def test_load_xrd_header_whitespace_txt_succeeds(tmp_path):
    path = _write_text(
        tmp_path / "pattern.txt",
        "2theta intensity\n10 100\n20 200\n30 150\n",
    )
    xrd = load_xrd_file(path)
    assert list(xrd.columns) == ["two_theta", "intensity"]
    assert xrd["intensity"].tolist() == [100, 200, 150]


def test_load_xrd_headerless_xy_succeeds(tmp_path):
    path = _write_text(tmp_path / "pattern.xy", "10 100\n20 200\n30 150\n")
    xrd = load_xrd_file(path)
    assert list(xrd.columns) == ["two_theta", "intensity"]
    assert xrd["two_theta"].tolist() == [10, 20, 30]


def test_load_xrd_headerless_comma_txt_succeeds(tmp_path):
    path = _write_text(tmp_path / "pattern.txt", "10,100\n20,200\n30,150\n")
    xrd = load_xrd_file(path)
    assert list(xrd.columns) == ["two_theta", "intensity"]
    assert xrd["intensity"].tolist() == [100, 200, 150]


def test_load_xrd_unsupported_extension_raises_value_error(tmp_path):
    path = _write_text(tmp_path / "pattern.xlsx", "10,100\n20,200\n30,150\n")
    with pytest.raises(ValueError, match="unsupported extension"):
        load_xrd_file(path)


def test_load_xrd_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError, match="does not exist"):
        load_xrd_file(tmp_path / "missing.csv")


def test_load_xrd_one_column_file_raises_clear_value_error(tmp_path):
    path = _write_text(tmp_path / "pattern.csv", "two_theta\n10\n20\n30\n")
    with pytest.raises(ValueError, match="exactly 2 columns"):
        load_xrd_file(path)


def test_load_xrd_non_numeric_intensity_raises_clear_value_error(tmp_path):
    path = _write_text(
        tmp_path / "pattern.csv",
        "two_theta,intensity\n10,100\n20,bad\n30,150\n",
    )
    with pytest.raises(ValueError, match="intensity.*non-numeric"):
        load_xrd_file(path)


def test_load_xrd_too_small_dataset_raises_clear_value_error(tmp_path):
    path = _write_text(tmp_path / "pattern.csv", "two_theta,intensity\n10,100\n20,200\n")
    with pytest.raises(ValueError, match="at least 3 valid numeric XRD rows"):
        load_xrd_file(path)


def test_load_eds_demo_csv_succeeds():
    eds = load_eds_composition_table(DATA / "synthetic_eds.csv")
    assert list(eds.columns) == ["element", "weight_percent", "atomic_percent"]
    assert len(eds) > 0


def test_load_eds_short_aliases_succeed(tmp_path):
    path = _write_text(tmp_path / "eds.csv", "Element,Wt%,At%\nFe,70,60\nO,30,40\n")
    eds = load_eds_composition_table(path)
    assert list(eds.columns) == ["element", "weight_percent", "atomic_percent"]
    assert eds["element"].tolist() == ["Fe", "O"]


def test_load_eds_long_aliases_succeed(tmp_path):
    path = _write_text(
        tmp_path / "eds.csv",
        "ELEMENT,Weight %,Atomic Percent\nFe,70,60\nO,30,40\n",
    )
    eds = load_eds_composition_table(path)
    assert list(eds.columns) == ["element", "weight_percent", "atomic_percent"]
    assert eds["weight_percent"].tolist() == [70, 30]


def test_load_eds_missing_required_column_raises_value_error(tmp_path):
    path = _write_text(tmp_path / "eds.csv", "Element,Wt%\nFe,70\n")
    with pytest.raises(ValueError, match="atomic_percent"):
        load_eds_composition_table(path)


def test_load_eds_duplicate_alias_raises_value_error(tmp_path):
    path = _write_text(tmp_path / "eds.csv", "Element,Wt%,weight_percent,At%\nFe,70,71,60\n")
    with pytest.raises(ValueError, match="Duplicate alias"):
        load_eds_composition_table(path)


def test_load_eds_non_numeric_composition_raises_value_error(tmp_path):
    path = _write_text(tmp_path / "eds.csv", "Element,Wt%,At%\nFe,bad,60\n")
    with pytest.raises(ValueError, match="weight_percent.*non-numeric"):
        load_eds_composition_table(path)


def test_load_eds_blank_element_rows_are_ignored(tmp_path):
    path = _write_text(
        tmp_path / "eds.csv",
        "Element,Wt%,At%\nFe,70,60\n,10,9\nO,20,31\n",
    )
    eds = load_eds_composition_table(path)
    assert eds["element"].tolist() == ["Fe", "O"]
