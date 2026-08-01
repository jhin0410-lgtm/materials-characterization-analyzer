#!/usr/bin/env python3
"""Audit the checksum-bound PhaseT3M Co3O4 processed tilt-series candidate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from mca.phaset3m_candidate_audit import audit_phaset3m_candidate, load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary = audit_phaset3m_candidate(
        load_config(args.config), args.archive, args.output
    )
    print(
        json.dumps(
            {
                "status": summary["scientific_closeout"]["result"],
                "archive_sha256": summary["source"]["archive_sha256"],
                "target_member": summary["source"]["target_member"],
                "dataset_count": summary["hdf5_audit"]["dataset_count"],
                "ready_for_external_evaluation": summary["scientific_gates"][
                    "ready_for_predeclared_external_evaluation"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
