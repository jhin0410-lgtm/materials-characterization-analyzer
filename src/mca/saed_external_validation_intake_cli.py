"""CLI for checksum-bound external SAED dataset intake."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .saed_external_validation_intake import (
    load_intake_manifest,
    run_saed_external_validation_intake,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mca saed-validation-intake",
        description=(
            "Verify a proposed external SAED dataset manifest, provenance, "
            "calibration declarations, and local file SHA-256 values without "
            "decoding patterns, tuning parameters, or performing indexing."
        ),
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_saed_external_validation_intake(
        load_intake_manifest(args.manifest),
        data_root=args.data_root,
        output_dir=args.output,
    )
    print(
        json.dumps(
            {
                "status": summary["decision"]["status"],
                "active_pattern_count": summary["result_counts"][
                    "active_pattern_count"
                ],
                "sample_count": summary["result_counts"]["sample_count"],
                "acquisition_count": summary["result_counts"][
                    "acquisition_count"
                ],
                "saed_protocol_freeze_ready": summary["decision"][
                    "saed_protocol_freeze_ready"
                ],
                "predeclared_saed_external_evaluation_ready": summary[
                    "decision"
                ]["predeclared_saed_external_evaluation_ready"],
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
