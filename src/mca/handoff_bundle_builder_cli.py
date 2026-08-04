"""CLI for config-driven characterization handoff bundle construction."""
from __future__ import annotations

import argparse
import json
import sys

from .handoff_bundle_builder import (
    HandoffBundleBuildError,
    build_characterization_handoff_bundle_from_config,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mca build-handoff",
        description=(
            "Build a portable characterization handoff bundle from an explicit config, "
            "copy checksum-bound evidence, and validate the completed bundle."
        ),
    )
    parser.add_argument("--config", required=True, help="Build configuration JSON.")
    parser.add_argument("--output", required=True, help="New output directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = build_characterization_handoff_bundle_from_config(args.config, args.output)
    except (OSError, ValueError, TypeError, KeyError, HandoffBundleBuildError) as exc:
        print(f"handoff bundle build failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
