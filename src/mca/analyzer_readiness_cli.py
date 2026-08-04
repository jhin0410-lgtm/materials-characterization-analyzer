"""CLI for the versioned analyzer-readiness registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analyzer_readiness import (
    AnalyzerReadinessError,
    generate_analyzer_readiness_registry,
)

DEFAULT_CONFIG = Path(
    "case_studies/analyzer_readiness_registry/readiness_registry.json"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mca analyzer-readiness",
        description=(
            "Generate a fail-closed snapshot separating software readiness, "
            "diagnostic real-data evidence, scientific validation, and engineering readiness "
            "for every public analyzer."
        ),
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Versioned readiness-registry JSON.",
    )
    parser.add_argument("--output", required=True, help="New output directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = generate_analyzer_readiness_registry(args.config, args.output)
    except (OSError, ValueError, TypeError, KeyError, AnalyzerReadinessError) as exc:
        print(f"analyzer readiness generation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
