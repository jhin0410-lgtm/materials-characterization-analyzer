"""CLI for the Mendeley CoP/Co2P/Co3O4 TEM candidate audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .tem_mendeley_candidate_audit import load_config, run_mendeley_candidate_audit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mca tem-mendeley-audit",
        description=(
            "Resolve public Mendeley dataset and file metadata for the pinned "
            "CoP/Co2P/Co3O4 TEM candidate without downloading source arrays."
        ),
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_mendeley_candidate_audit(
        load_config(args.config),
        args.output,
    )
    print(
        json.dumps(
            {
                "status": summary["inventory_readiness"]["status"],
                "file_count": summary["result_counts"]["file_count"],
                "primary_tem_candidate_file_count": summary["result_counts"][
                    "primary_tem_candidate_file_count"
                ],
                "annotation_pilot_ready": summary["lineage_and_annotation_gates"][
                    "annotation_pilot_ready"
                ],
                "next_action": summary["next_action"],
                "output": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
