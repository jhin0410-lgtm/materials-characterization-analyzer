from __future__ import annotations

import json
from pathlib import Path

from scripts.export_nist_ambench_2018_02_optical_metrology_bundle import (
    DEFAULT_CONFIG,
    export_bundle,
)


def test_nist_bundle_is_explicitly_diagnostic_and_descriptive_only(
    tmp_path: Path,
) -> None:
    paths = export_bundle(DEFAULT_CONFIG, tmp_path / "bundle")
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    policy = manifest["downstream_use_policy"]

    assert policy["evidence_level"] == "Diagnostic"
    assert policy["maximum_allowed_use"] == "descriptive"
    assert policy["independence_group_field"] is None
    assert policy["measurement_timing"] == "unknown"
    assert policy["causal_design_validated"] is False
    assert policy["operational_validation_validated"] is False
