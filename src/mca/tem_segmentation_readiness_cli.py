"""Command-line interface for consolidated TEM segmentation readiness."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .tem_candidate_registry_readiness import (
    build_tem_segmentation_readiness_with_registry,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mca tem-readiness",
        description=(
            "Consolidate existing TEM training, leakage, public-candidate, and "
            "external-validation audit summaries without training or evaluating a model."
        ),
    )
    parser.add_argument(
        "--training-summary",
        type=Path,
        required=True,
        help="training_data_readiness_summary.json from the cobalt-oxide training audit",
    )
    parser.add_argument(
        "--parent-overlap-summary",
        type=Path,
        required=True,
        help="parent_overlap_audit_summary.json from the source-frame overlap audit",
    )
    parser.add_argument(
        "--external-candidate-summary",
        type=Path,
        help="optional external_validation_candidate_summary.json",
    )
    parser.add_argument(
        "--candidate-registry-summary",
        type=Path,
        help="optional tem_external_validation_candidate_summary.json",
    )
    parser.add_argument(
        "--pilot-readiness",
        type=Path,
        help="optional dryad-acquisition-readiness.json",
    )
    parser.add_argument(
        "--pilot-summary",
        type=Path,
        help="optional authenticated pilot_pair_audit_summary.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="absent or empty output directory",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = build_tem_segmentation_readiness_with_registry(
        training_summary_path=args.training_summary,
        parent_overlap_summary_path=args.parent_overlap_summary,
        external_candidate_summary_path=args.external_candidate_summary,
        candidate_registry_summary_path=args.candidate_registry_summary,
        pilot_readiness_path=args.pilot_readiness,
        pilot_summary_path=args.pilot_summary,
        output_dir=args.output,
    )
    print(
        json.dumps(
            {
                "status": summary["decision"]["status"],
                "software_experiment_training_allowed": summary["decision"][
                    "software_experiment_training_allowed"
                ],
                "scientific_in_domain_performance_evaluation_ready": summary[
                    "decision"
                ]["scientific_in_domain_performance_evaluation_ready"],
                "next_action": summary["decision"]["next_action"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
