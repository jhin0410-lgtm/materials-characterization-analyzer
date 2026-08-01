"""Backward-compatible console entry point with standalone analyzer dispatch."""

from __future__ import annotations

import sys

from . import __version__
from .cli import main as legacy_main
from .ftir_cli import main as ftir_main
from .raman_cli import main as raman_main
from .saed_cli import main as saed_main
from .saed_external_validation_intake_cli import (
    main as saed_validation_intake_main,
)
from .tem_cli import main as tem_main
from .tem_external_validation_candidate_registry_cli import main as tem_candidates_main
from .tem_external_validation_intake_cli import main as tem_validation_intake_main
from .tem_mendeley_candidate_audit_cli import main as tem_mendeley_audit_main
from .tem_segmentation_readiness_cli import main as tem_readiness_main
from .thermal_cli import main as thermal_main
from .xps_cli import main as xps_main


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args in (["--version"], ["-V"]):
        print(f"materials-characterization-analyzer {__version__}")
        return 0
    if args and args[0] == "raman":
        return raman_main(args[1:])
    if args and args[0] == "tem":
        return tem_main(args[1:])
    if args and args[0] == "tem-candidates":
        return tem_candidates_main(args[1:])
    if args and args[0] == "tem-mendeley-audit":
        return tem_mendeley_audit_main(args[1:])
    if args and args[0] == "tem-readiness":
        return tem_readiness_main(args[1:])
    if args and args[0] == "tem-validation-intake":
        return tem_validation_intake_main(args[1:])
    if args and args[0] == "saed":
        return saed_main(args[1:])
    if args and args[0] == "saed-validation-intake":
        return saed_validation_intake_main(args[1:])
    if args and args[0] == "xps":
        return xps_main(args[1:])
    if args and args[0] == "ftir":
        return ftir_main(args[1:])
    if args and args[0] == "thermal":
        return thermal_main(args[1:])
    if args in (["--help"], ["-h"]):
        print(
            "Additional commands: raman, tem, tem-candidates, tem-mendeley-audit, "
            "tem-readiness, tem-validation-intake, saed, saed-validation-intake, "
            "xps, ftir, thermal "
            "(run 'mca <command> --help' for options).\n"
            "Version: mca --version"
        )
    return legacy_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
