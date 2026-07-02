"""Input file import and validation helpers for XRD and EDS data."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd
from pandas.errors import EmptyDataError, ParserError

from .utils import validate_columns

SUPPORTED_XRD_EXTENSIONS = {".csv", ".txt", ".xy"}
SUPPORTED_EDS_EXTENSIONS = {".csv"}

XRD_REQUIRED_COLUMNS = ("two_theta", "intensity")
EDS_REQUIRED_COLUMNS = ("element", "weight_percent", "atomic_percent")


def validate_input_file(path, allowed_extensions, source_name) -> Path:
    """Validate that the input path is an existing file with an allowed extension."""
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"{source_name} file does not exist: {input_path}")
    if not input_path.is_file():
        raise ValueError(f"{source_name} path is not a file: {input_path}")

    extension = input_path.suffix.lower()
    allowed = {ext.lower() for ext in allowed_extensions}
    if extension not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise ValueError(
            f"{source_name} file has unsupported extension '{extension}'. "
            f"Supported extensions: {allowed_text}."
        )
    return input_path


def load_xrd_file(path: str | Path) -> pd.DataFrame:
    """Load XRD 2-column data from .csv, .txt, or .xy files."""
    input_path = validate_input_file(path, SUPPORTED_XRD_EXTENSIONS, "XRD")
    source_name = f"XRD file '{input_path}'"

    for separator in _xrd_separators(input_path):
        try:
            df = _read_table(input_path, separator=separator, header=0, source_name=source_name)
        except ValueError:
            raise
        except ParserError:
            continue

        try:
            normalized = normalize_xrd_columns(df)
        except ValueError:
            continue
        return validate_xrd_dataframe(normalized, source_name)

    shape_errors: list[str] = []
    for separator in _xrd_separators(input_path):
        try:
            df = _read_table(input_path, separator=separator, header=None, source_name=source_name)
        except ValueError:
            raise
        except ParserError:
            continue

        if df.shape[1] != 2:
            shape_errors.append(f"found {df.shape[1]} column(s)")
            continue

        headerless = df.copy()
        headerless.columns = list(XRD_REQUIRED_COLUMNS)
        return validate_xrd_dataframe(headerless, source_name)

    detail = f" Last parsed shape: {shape_errors[-1]}." if shape_errors else ""
    raise ValueError(
        f"{source_name} could not be interpreted as supported XRD data. "
        "Expected exactly 2 columns: two_theta and intensity. "
        "Header aliases are supported, or headerless files may provide numeric "
        "2theta/intensity values in the first two columns."
        f"{detail}"
    )


def normalize_xrd_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize supported XRD column aliases to two_theta and intensity."""
    matches = _find_alias_matches(
        df.columns,
        {
            "two_theta": {"two_theta", "2theta", "2 theta", "two theta"},
            "intensity": {"intensity", "counts"},
        },
    )
    missing = [column for column in XRD_REQUIRED_COLUMNS if column not in matches]
    if missing:
        missing_text = ", ".join(missing)
        raise ValueError(
            f"XRD file is missing required column alias(es): {missing_text}. "
            "Supported aliases: two_theta/2theta/2 theta/two theta and intensity/counts."
        )

    rename_map = {source: target for target, source in matches.items()}
    return df.rename(columns=rename_map)


def validate_xrd_dataframe(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    """Validate XRD columns, numeric conversion, and minimum row count."""
    if df.shape[1] != 2:
        raise ValueError(
            f"{source_name} must contain exactly 2 columns: two_theta and intensity. "
            f"Found {df.shape[1]} column(s)."
        )

    validate_columns(df, XRD_REQUIRED_COLUMNS, source_name)
    xrd = df.loc[:, XRD_REQUIRED_COLUMNS].copy()
    for column in XRD_REQUIRED_COLUMNS:
        xrd[column] = _convert_numeric_column(xrd[column], column, source_name)

    xrd = xrd.dropna(subset=list(XRD_REQUIRED_COLUMNS)).sort_values("two_theta").reset_index(drop=True)
    if len(xrd) < 3:
        raise ValueError(f"{source_name} must contain at least 3 valid numeric XRD rows.")
    return xrd


def load_eds_composition_table(path: str | Path) -> pd.DataFrame:
    """Load an EDS composition table and return standardized columns."""
    input_path = validate_input_file(path, SUPPORTED_EDS_EXTENSIONS, "EDS")
    source_name = f"EDS composition table '{input_path}'"

    try:
        df = pd.read_csv(input_path)
    except EmptyDataError as exc:
        raise ValueError(f"{source_name} is empty.") from exc

    normalized = normalize_eds_columns(df)
    return validate_eds_dataframe(normalized, source_name)


def normalize_eds_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize supported EDS composition column aliases."""
    matches = _find_alias_matches(
        df.columns,
        {
            "element": {"element"},
            "weight_percent": {"weight_percent", "wt_percent", "Wt%", "Weight %", "Weight Percent"},
            "atomic_percent": {"atomic_percent", "at_percent", "At%", "Atomic %", "Atomic Percent"},
        },
    )
    rename_map = {source: target for target, source in matches.items()}
    return df.rename(columns=rename_map)


def validate_eds_dataframe(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    """Validate element, weight_percent, and atomic_percent columns."""
    validate_columns(df, EDS_REQUIRED_COLUMNS, source_name)

    eds = df.loc[:, EDS_REQUIRED_COLUMNS].copy()
    eds["element"] = eds["element"].where(eds["element"].notna(), "").astype(str).str.strip()
    eds["weight_percent"] = _convert_numeric_column(eds["weight_percent"], "weight_percent", source_name)
    eds["atomic_percent"] = _convert_numeric_column(eds["atomic_percent"], "atomic_percent", source_name)
    eds = eds.dropna(subset=["weight_percent", "atomic_percent"])
    eds = eds[eds["element"] != ""].reset_index(drop=True)

    if eds.empty:
        raise ValueError(f"{source_name} did not contain any valid EDS composition rows.")
    return eds


def _xrd_separators(path: Path) -> list[str]:
    extension = path.suffix.lower()
    if extension == ".csv":
        return [","]
    if extension == ".txt":
        return [",", r"\s+"]
    return [r"\s+"]


def _read_table(path: Path, separator: str, header: int | None, source_name: str) -> pd.DataFrame:
    try:
        return pd.read_csv(
            path,
            sep=separator,
            header=header,
            engine="python",
            comment="#",
            skip_blank_lines=True,
        )
    except EmptyDataError as exc:
        raise ValueError(f"{source_name} is empty.") from exc


def _find_alias_matches(columns: Iterable[object], aliases: dict[str, set[str]]) -> dict[str, object]:
    lookup = {
        _normalize_label(alias): standard
        for standard, alias_set in aliases.items()
        for alias in alias_set
    }
    matches: dict[str, list[object]] = {}
    for column in columns:
        standard = lookup.get(_normalize_label(column))
        if standard is not None:
            matches.setdefault(standard, []).append(column)

    duplicates = {standard: found for standard, found in matches.items() if len(found) > 1}
    if duplicates:
        details = "; ".join(
            f"{standard}: {', '.join(str(column) for column in found)}"
            for standard, found in sorted(duplicates.items())
        )
        raise ValueError(f"Duplicate alias columns were found: {details}.")

    return {standard: found[0] for standard, found in matches.items()}


def _normalize_label(label: object) -> str:
    return str(label).strip().casefold()


def _convert_numeric_column(series: pd.Series, column_name: str, source_name: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    text = series.astype(str).str.strip()
    invalid = numeric.isna() & series.notna() & (text != "")
    if invalid.any():
        bad_value = series[invalid].iloc[0]
        raise ValueError(
            f"{source_name} column '{column_name}' contains non-numeric value "
            f"{bad_value!r}. Please provide numeric values."
        )
    return numeric
