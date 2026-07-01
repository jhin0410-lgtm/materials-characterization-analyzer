"""EDS composition table and chart helpers."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mca_matplotlib"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .utils import ensure_output_dir, validate_columns

REQUIRED_EDS_COLUMNS = ("element", "weight_percent", "atomic_percent")


def read_eds_csv(path: str | Path) -> pd.DataFrame:
    """Read an EDS point or area analysis CSV."""
    df = pd.read_csv(path)
    validate_columns(df, REQUIRED_EDS_COLUMNS, "EDS CSV")

    eds = df.loc[:, REQUIRED_EDS_COLUMNS].copy()
    eds["element"] = eds["element"].astype(str).str.strip()
    eds["weight_percent"] = pd.to_numeric(eds["weight_percent"], errors="coerce")
    eds["atomic_percent"] = pd.to_numeric(eds["atomic_percent"], errors="coerce")
    eds = eds.dropna(subset=["element", "weight_percent", "atomic_percent"])
    eds = eds[eds["element"] != ""].reset_index(drop=True)

    if eds.empty:
        raise ValueError("EDS CSV did not contain any valid composition rows.")
    return eds


def prepare_composition_table(eds: pd.DataFrame) -> pd.DataFrame:
    """Return a clean composition table sorted by weight percent."""
    table = eds.copy()
    table = table.sort_values("weight_percent", ascending=False).reset_index(drop=True)
    table.insert(0, "rank_by_weight_percent", np.arange(1, len(table) + 1))
    return table


def top_elements(eds: pd.DataFrame, top_n: int = 3) -> pd.DataFrame:
    """Return the top elements by weight percent."""
    return prepare_composition_table(eds).head(top_n)


def summarize_eds(eds: pd.DataFrame, top_n: int = 3) -> str:
    """Create a cautious text summary for EDS results."""
    top = top_elements(eds, top_n=top_n)
    top_text = ", ".join(
        f"{row.element} ({row.weight_percent:.2f} wt%)" for row in top.itertuples(index=False)
    )
    return (
        f"Major elements by weight percent: {top_text}. "
        "EDS supports elemental composition review, but it does not confirm crystal phases by itself."
    )


def plot_eds_composition(eds: pd.DataFrame, output_path: str | Path) -> Path:
    """Save a grouped bar chart of weight and atomic percent."""
    output_path = Path(output_path)
    table = prepare_composition_table(eds)
    x = np.arange(len(table))
    width = 0.38

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(x - width / 2, table["weight_percent"], width, label="wt%", color="#2a9d8f")
    ax.bar(x + width / 2, table["atomic_percent"], width, label="at%", color="#f4a261")
    ax.set_xticks(x)
    ax.set_xticklabels(table["element"])
    ax.set_ylabel("Composition (%)")
    ax.set_title("EDS Composition Summary")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    return output_path


def analyze_eds(input_path: str | Path, output_dir: str | Path) -> dict[str, object]:
    """Run the v0.1 EDS workflow and save table/chart outputs."""
    output_dir = ensure_output_dir(output_dir)
    eds = read_eds_csv(input_path)
    composition_table = prepare_composition_table(eds)

    table_path = output_dir / "eds_composition_table.csv"
    chart_path = output_dir / "eds_composition_bar_chart.png"
    composition_table.to_csv(table_path, index=False)
    plot_eds_composition(eds, chart_path)

    return {
        "eds": eds,
        "composition_table": composition_table,
        "summary_text": summarize_eds(eds),
        "table_path": table_path,
        "chart_path": chart_path,
    }

