"""Backward-compatible console entry point with Raman, TEM, and SAED dispatch."""

from __future__ import annotations

import sys

from .cli import main as legacy_main
from .raman_cli import main as raman_main
from .saed_cli import main as saed_main
from .tem_cli import main as tem_main


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "raman":
        return raman_main(args[1:])
    if args and args[0] == "tem":
        return tem_main(args[1:])
    if args and args[0] == "saed":
        return saed_main(args[1:])
    if args in (["--help"], ["-h"]):
        print(
            "Additional commands: raman, tem, saed "
            "(run 'mca <command> --help' for options)\n"
        )
    return legacy_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
