"""Export the persisted public DWCNT case as a cross-repository handoff bundle."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mca.handoff_bundle import write_characterization_handoff_bundle

DEFAULT_CONFIG = Path("case_studies/public_carbon_multimodal/case_config.json")
PRODUCER_REPOSITORY = "jhin0410-lgtm/materials-characterization-analyzer"


def load_json(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def export_bundle(config_path: str | Path, result_dir: str | Path) -> dict[str, Path]:
    config = load_json(config_path)
    result = Path(result_dir)
    if not result.is_dir():
        raise FileNotFoundError(f"Public carbon result directory not found: {result}")

    primary_sample = config.get("primary_sample")
    dataset = config.get("dataset")
    if not isinstance(primary_sample, dict) or not isinstance(dataset, dict):
        raise ValueError("Case config must contain primary_sample and dataset objects.")

    sample_context = {
        "sample_id": primary_sample.get("sample_id"),
        "source_label": primary_sample.get("source_label"),
        "material_class": primary_sample.get("material_class"),
        "source_description": primary_sample.get("source_description"),
        "dataset_persistent_id": dataset.get("persistent_id"),
        "dataset_version": dataset.get("version"),
        "dataset_license": dataset.get("license"),
        "identical_physical_aliquot_confirmed": False,
    }
    paths = write_characterization_handoff_bundle(
        result,
        case_id=str(config.get("case_id", "")),
        sample_context_rows=[sample_context],
        source_manifest_path=result / "case_source_manifest.json",
        analysis_manifest_path=result / "case_analysis_manifest.json",
        comparability_matrix_path=result / "comparability_matrix.csv",
        producer_repository=PRODUCER_REPOSITORY,
        evidence_level="Diagnostic",
        scientific_boundary={
            "result": "real_public_multimodal_features_exported",
            "strongest_evidence": (
                "Raman, FTIR, XPS, and TGA feature records retain original public-file "
                "checksums, preprocessing identifiers, and stable sample/measurement IDs."
            ),
            "primary_limitation": (
                "The common DWCNT source label does not establish identical physical "
                "aliquots across techniques, and TEM quantitative analysis was blocked."
            ),
            "suitable_for": [
                "cross-repository contract validation",
                "provenance demonstration",
                "descriptive multimodal feature integration",
            ],
            "unsuitable_for": [
                "process-response modeling",
                "causal attribution",
                "phase or chemical-state confirmation",
                "engineering release decisions",
            ],
        },
    )

    summary_path = result / "case_summary.json"
    summary = load_json(summary_path)
    summary["cross_repository_handoff"] = {
        "feature_table": paths["feature_table"].name,
        "sample_context": paths["sample_context"].name,
        "manifest": paths["manifest"].name,
        "consumer_repository": "jhin0410-lgtm/materials-data-analyzer",
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--result", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = export_bundle(args.config, args.result)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"public carbon handoff export failed: {exc}", file=sys.stderr)
        return 1
    print("Public DWCNT cross-repository handoff bundle exported.")
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
