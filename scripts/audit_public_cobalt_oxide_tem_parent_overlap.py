"""Audit public cobalt-oxide TEM source frames for training-parent overlap."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mca.tem_parent_overlap_audit import (
    load_config,
    run_parent_overlap_audit,
    validate_public_config,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="case_studies/public_cobalt_oxide_tem_parent_overlap_audit/case_config.json",
        help="Pinned public-case JSON configuration.",
    )
    parser.add_argument(
        "--output",
        default="outputs/public-cobalt-oxide-tem-parent-overlap-audit",
        help="Absent or empty output directory.",
    )
    parser.add_argument(
        "--training-images",
        default=None,
        help="Optional local training_images.h5; exact MD5 and SHA-256 must match.",
    )
    parser.add_argument(
        "--source-archive",
        default=None,
        help="Optional local TEM_images.zip; exact MD5 and SHA-256 must match.",
    )
    args = parser.parse_args(argv)
    config = load_config(Path(args.config))
    validate_public_config(config)
    summary = run_parent_overlap_audit(
        config,
        Path(args.output),
        training_path=args.training_images,
        source_archive_path=args.source_archive,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
