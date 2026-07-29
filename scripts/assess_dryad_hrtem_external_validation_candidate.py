"""Assess the Dryad HRTEM source as an external-validation candidate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from mca.tem_external_validation_candidate_assessment import (
    load_config,
    run_candidate_assessment,
    validate_public_config,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=(
            "case_studies/dryad_hrtem_external_validation_candidate_assessment/"
            "case_config.json"
        ),
        help="Pinned source-assessment JSON configuration.",
    )
    parser.add_argument(
        "--output",
        default="outputs/dryad-hrtem-external-validation-candidate-assessment",
        help="Absent or empty output directory.",
    )
    args = parser.parse_args(argv)
    config = load_config(Path(args.config))
    validate_public_config(config)
    summary = run_candidate_assessment(config, Path(args.output))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
