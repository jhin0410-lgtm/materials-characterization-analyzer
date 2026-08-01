"""Refresh the checksum manifest after public-page and API probes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from mca.tem_mendeley_candidate_audit import (
    refresh_mendeley_candidate_audit_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = refresh_mendeley_candidate_audit_manifest(args.output)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
