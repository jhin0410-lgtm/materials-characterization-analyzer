"""CLI for validating and evaluating a scientific evidence-ladder declaration."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .evidence_ladder import EvidenceLadderError, evaluate_evidence_ladder


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceLadderError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    try:
        value = json.loads(
            resolved.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceLadderError(f"could not load evidence ladder declaration: {resolved}") from exc
    if not isinstance(value, dict):
        raise EvidenceLadderError("evidence ladder declaration root must be an object")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mca.evidence_ladder_cli",
        description=(
            "Evaluate where a characterization source/result sits on the L0-L8 scientific "
            "evidence ladder without authorizing downstream use or promoting scientific status."
        ),
    )
    parser.add_argument("--declaration", required=True, type=Path)
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="New immutable JSON assessment path. Existing files are rejected.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = evaluate_evidence_ladder(_load_json(args.declaration))
        output = args.output.expanduser().resolve()
        if output.exists():
            raise EvidenceLadderError(f"output already exists: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        output.write_text(rendered, encoding="utf-8")
        sys.stdout.write(rendered)
        return 0
    except (EvidenceLadderError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
