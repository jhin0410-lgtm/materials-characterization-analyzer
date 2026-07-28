"""Audit the pinned public cobalt-oxide HRTEM training-patch data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mca.tem_training_data_audit import load_config, run_training_data_audit, validate_public_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="case_studies/public_cobalt_oxide_tem_training_data_audit/case_config.json",
        help="Pinned public-case JSON configuration.",
    )
    parser.add_argument(
        "--output",
        default="outputs/public-cobalt-oxide-tem-training-data-audit",
        help="Absent or empty output directory.",
    )
    parser.add_argument(
        "--images",
        default=None,
        help="Optional local training_images.h5; exact MD5 and SHA-256 must match.",
    )
    parser.add_argument(
        "--labels",
        default=None,
        help="Optional local training_labels.h5; exact MD5 and SHA-256 must match.",
    )
    args = parser.parse_args(argv)
    config = load_config(Path(args.config))
    validate_public_config(config)
    summary = run_training_data_audit(
        config,
        Path(args.output),
        image_path=args.images,
        label_path=args.labels,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
