#!/usr/bin/env python3
"""Run the checksum-bound Dryad HRTEM pilot-pair audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from mca.tem_external_validation_pilot_audit import run_pilot_pair_audit
from mca.tem_external_validation_pilot_contract import load_config, validate_public_config


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--images", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--processed-metadata", type=Path)
    parser.add_argument("--training-images", type=Path)
    parser.add_argument("--images-api-metadata", type=Path)
    parser.add_argument("--labels-api-metadata", type=Path)
    parser.add_argument("--processed-metadata-api", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    config = load_config(args.config)
    validate_public_config(config)
    summary = run_pilot_pair_audit(
        config,
        args.output,
        image_path=args.images,
        label_path=args.labels,
        processed_metadata_path=args.processed_metadata,
        training_path=args.training_images,
        image_api_metadata_path=args.images_api_metadata,
        label_api_metadata_path=args.labels_api_metadata,
        processed_metadata_api_path=args.processed_metadata_api,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
