"""CLI for fail-closed characterization handoff bundle validation."""

from __future__ import annotations

import argparse
import json
import sys

from .handoff_bundle_validation import (
    HandoffBundleValidationError,
    validate_characterization_handoff_bundle,
    write_handoff_bundle_validation,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mca validate-handoff",
        description=(
            "Verify a characterization handoff bundle's checksums, schemas, sample join "
            "contract, and claim boundary without aggregating or interpreting features."
        ),
    )
    parser.add_argument("--bundle", required=True, help="Handoff bundle directory.")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional absent or empty directory for validation evidence.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.output is None:
            summary = validate_characterization_handoff_bundle(args.bundle)
            print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
        else:
            paths = write_handoff_bundle_validation(args.bundle, args.output)
            print(f"Saved handoff validation summary: {paths['summary']}")
            print(f"Saved handoff validation report: {paths['report']}")
            print(f"Saved handoff validation artifact manifest: {paths['artifact_manifest']}")
    except (OSError, ValueError, TypeError, KeyError, HandoffBundleValidationError) as exc:
        print(f"handoff bundle validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
