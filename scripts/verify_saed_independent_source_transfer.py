from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from saed_transfer_verification import (
    BLOCKED,
    CASE_ID,
    INTAKE_CASE_ID,
    READY,
    SCHEMA_VERSION,
    SOURCE_PLAN_READY,
    SOURCE_REQUEST_CASE_ID,
    SOURCE_RESPONSE_READY,
    SAEDTransferVerificationError,
    verify_transfer,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify an explicitly authorized checksum-bound SAED source transfer "
            "and generate a fail-closed intake-manifest draft."
        )
    )
    parser.add_argument("--response-bundle", required=True)
    parser.add_argument("--verification", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = verify_transfer(
        response_bundle=args.response_bundle,
        verification_path=args.verification,
        data_root=args.data_root,
        output_dir=args.output,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
