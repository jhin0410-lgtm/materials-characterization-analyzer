"""CLI for the source-backed TEM external-validation candidate registry."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .tem_external_validation_candidate_registry import (
    load_registry_config,
    run_candidate_registry,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mca tem-candidates",
        description=(
            "Build a dated, fail-closed registry of public TEM external-validation "
            "candidates without downloading arrays or evaluating a model."
        ),
    )
    parser.add_argument("--config", type=Path, required=True, help="pinned registry JSON")
    parser.add_argument(
        "--output", type=Path, required=True, help="absent or empty output directory"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_candidate_registry(load_registry_config(args.config), args.output)
    print(
        json.dumps(
            {
                "status": summary["readiness"]["status"],
                "candidate_count": summary["result_counts"]["candidate_count"],
                "in_domain_external_validation_ready_count": summary["result_counts"][
                    "in_domain_external_validation_ready_count"
                ],
                "recommended_candidate_id": summary["readiness"][
                    "recommended_candidate_id"
                ],
                "recommended_next_action": summary["readiness"][
                    "recommended_next_action"
                ],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
