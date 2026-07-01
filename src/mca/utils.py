"""Shared utility helpers for the materials characterization CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


def ensure_output_dir(output_dir: str | Path) -> Path:
    """Create and return an output directory path."""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_columns(df: pd.DataFrame, required_columns: Iterable[str], source: str) -> None:
    """Raise a clear error when a CSV file is missing required columns."""
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        required = ", ".join(required_columns)
        missing_text = ", ".join(missing)
        raise ValueError(
            f"{source} is missing required column(s): {missing_text}. "
            f"Required columns: {required}."
        )


def write_markdown(path: str | Path, content: str) -> Path:
    """Write Markdown content using UTF-8 encoding."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path
