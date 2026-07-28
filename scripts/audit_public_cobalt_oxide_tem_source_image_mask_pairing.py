"""Audit the pinned public cobalt-oxide source HRTEM image and mask pairing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mca.tem_source_image_mask_pairing import (
    load_config,
    run_pairing_audit,
    validate_public_config,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="case_studies/public_cobalt_oxide_tem_source_image_mask_pairing/case_config.json",
        help="Pinned public-case JSON configuration.",
    )
    parser.add_argument(
        "--output",
        default="outputs/public-cobalt-oxide-tem-source-image-mask-pairing",
        help="Absent or empty output directory.",
    )
    parser.add_argument(
        "--image-archive",
        default=None,
        help="Optional local TEM_images.zip source-image archive; exact MD5 and SHA-256 must match.",
    )
    parser.add_argument(
        "--mask-archive",
        default=None,
        help="Optional local Segmented_images.zip; exact MD5 and SHA-256 must match.",
    )
    args = parser.parse_args(argv)

    config = load_config(Path(args.config))
    validate_public_config(config)
    summary = run_pairing_audit(
        config,
        Path(args.output),
        image_archive_path=args.image_archive,
        mask_archive_path=args.mask_archive,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
