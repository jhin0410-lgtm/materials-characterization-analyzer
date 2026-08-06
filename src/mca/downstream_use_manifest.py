"""Attach a validated downstream-use policy to a staged handoff manifest."""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .downstream_use_policy import validate_downstream_use_policy


def attach_downstream_use_policy(
    manifest_path: str | Path,
    policy: Mapping[str, object],
    *,
    scientific_evidence_level: str,
) -> dict[str, Any]:
    """Validate and attach policy before the staged bundle is validated/published."""
    path = Path(manifest_path)
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(f"handoff manifest not found or unsafe: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("handoff manifest root must be an object")
    if "downstream_use_policy" in payload:
        raise ValueError("handoff manifest already contains downstream_use_policy")
    normalized = validate_downstream_use_policy(
        policy,
        scientific_evidence_level=scientific_evidence_level,
    )
    payload["downstream_use_policy"] = normalized
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return normalized
