"""Run the pinned public cobalt-oxide TEM source-mask diagnostic case."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mca.tem_mask_import import load_config, run_case, validate_public_case_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="case_studies/public_cobalt_oxide_tem_masks/case_config.json",
        help="Pinned public-case JSON configuration.",
    )
    parser.add_argument(
        "--output",
        default="outputs/public-cobalt-oxide-tem-masks",
        help="Absent or empty output directory.",
    )
    parser.add_argument(
        "--archive",
        default=None,
        help=(
            "Optional local copy of Segmented_images.zip. The published MD5 and "
            "tracked SHA-256 are still required to match exactly."
        ),
    )
    args = parser.parse_args(argv)

    config = load_config(Path(args.config))
    validate_public_case_config(config)
    summary = run_case(config, Path(args.output), archive_path=args.archive)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
