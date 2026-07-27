"""Stable public contracts for characterization results and feature records.

The contracts in this module store provenance, preprocessing history, generated
artifacts, quality flags, and scientific limitations without interpreting the
material identity or mechanism.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class PreprocessingStep:
    """One explicitly recorded preprocessing or analysis operation."""

    step_id: str
    operation: str
    parameters: dict[str, Any] = field(default_factory=dict)
    notes: str | None = None

    def __post_init__(self) -> None:
        if not self.step_id.strip():
            raise ValueError("step_id must not be empty.")
        if not self.operation.strip():
            raise ValueError("operation must not be empty.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FeatureRecord:
    """One sample-level numeric feature with scientific and provenance context."""

    sample_id: str
    measurement_id: str
    instrument: str
    feature_name: str
    value: int | float
    unit: str
    method: str
    feature_label: str | None = None
    source_file: str | None = None
    source_sha256: str | None = None
    preprocessing_id: str | None = None
    quality_flag: str = "ok"

    def __post_init__(self) -> None:
        required = {
            "sample_id": self.sample_id,
            "measurement_id": self.measurement_id,
            "instrument": self.instrument,
            "feature_name": self.feature_name,
            "unit": self.unit,
            "method": self.method,
            "quality_flag": self.quality_flag,
        }
        empty = [name for name, value in required.items() if not value.strip()]
        if empty:
            raise ValueError(f"FeatureRecord fields must not be empty: {', '.join(empty)}")
        _validate_sha256(self.source_sha256)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisResult:
    """Serializable result contract for one instrument measurement."""

    measurement_id: str
    sample_id: str
    instrument: str
    source_file: str | None = None
    source_sha256: str | None = None
    acquisition_metadata: dict[str, Any] = field(default_factory=dict)
    preprocessing_steps: list[PreprocessingStep] = field(default_factory=list)
    tables: dict[str, str] = field(default_factory=dict)
    figures: dict[str, str] = field(default_factory=dict)
    features: list[FeatureRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    software_version: str = "unknown"
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        required = {
            "measurement_id": self.measurement_id,
            "sample_id": self.sample_id,
            "instrument": self.instrument,
            "software_version": self.software_version,
            "schema_version": self.schema_version,
        }
        empty = [name for name, value in required.items() if not value.strip()]
        if empty:
            raise ValueError(f"AnalysisResult fields must not be empty: {', '.join(empty)}")
        if self.source_sha256 is not None and self.source_file is None:
            raise ValueError("source_file is required when source_sha256 is provided.")
        _validate_sha256(self.source_sha256)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "measurement_id": self.measurement_id,
            "sample_id": self.sample_id,
            "instrument": self.instrument,
            "source_file": self.source_file,
            "source_sha256": self.source_sha256,
            "acquisition_metadata": self.acquisition_metadata,
            "preprocessing_steps": [step.to_dict() for step in self.preprocessing_steps],
            "tables": dict(self.tables),
            "figures": dict(self.figures),
            "features": [feature.to_dict() for feature in self.features],
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
            "software_version": self.software_version,
        }


def write_analysis_manifest(results: list[AnalysisResult], output_path: str | Path) -> Path:
    """Write a versioned JSON manifest containing one or more analysis results."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "analysis_count": len(results),
        "analyses": [result.to_dict() for result in results],
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def _validate_sha256(value: str | None) -> None:
    if value is None:
        return
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value.lower()):
        raise ValueError("source_sha256 must be a 64-character hexadecimal digest.")
