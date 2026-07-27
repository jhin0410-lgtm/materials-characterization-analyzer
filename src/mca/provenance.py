"""Provenance helpers for characterization analysis outputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import __version__
from .contracts import AnalysisResult, FeatureRecord, PreprocessingStep


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest of a file without loading it fully into memory."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Source file does not exist: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def preprocessing_fingerprint(
    instrument: str,
    steps: Iterable[PreprocessingStep],
    length: int = 16,
) -> str:
    """Return a deterministic identifier for an ordered preprocessing history."""
    payload = {
        "instrument": instrument,
        "steps": [step.to_dict() for step in steps],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:length]


def build_analysis_result(
    *,
    measurement_id: str,
    sample_id: str,
    instrument: str,
    source_file: str | Path | None = None,
    acquisition_metadata: Mapping[str, Any] | None = None,
    preprocessing_steps: Iterable[PreprocessingStep] = (),
    tables: Mapping[str, str | Path] | None = None,
    figures: Mapping[str, str | Path] | None = None,
    features: Iterable[FeatureRecord] = (),
    warnings: Iterable[str] = (),
    limitations: Iterable[str] = (),
    software_version: str = __version__,
) -> AnalysisResult:
    """Build an AnalysisResult while recording source hash and missing provenance."""
    warning_list = list(warnings)
    source_path: str | None = None
    source_hash: str | None = None

    if source_file is None:
        warning_list.append("raw_source_file_not_provided")
    else:
        resolved_source = Path(source_file)
        source_path = str(resolved_source)
        source_hash = sha256_file(resolved_source)

    return AnalysisResult(
        measurement_id=measurement_id,
        sample_id=sample_id,
        instrument=instrument,
        source_file=source_path,
        source_sha256=source_hash,
        acquisition_metadata=dict(acquisition_metadata or {}),
        preprocessing_steps=list(preprocessing_steps),
        tables=_stringify_paths(tables),
        figures=_stringify_paths(figures),
        features=list(features),
        warnings=_deduplicate(warning_list),
        limitations=_deduplicate(limitations),
        software_version=software_version,
    )


def _stringify_paths(values: Mapping[str, str | Path] | None) -> dict[str, str]:
    if values is None:
        return {}
    return {name: str(path) for name, path in values.items()}


def _deduplicate(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
