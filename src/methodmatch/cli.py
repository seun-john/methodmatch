"""Command line for MethodMatch."""

from __future__ import annotations

import argparse
from typing import Any

from .align import methodmatch
from .runner import Command, main_wrapper, run


def _check(args: argparse.Namespace, data: Any) -> dict[str, Any]:
    return methodmatch(data)


COMMANDS = {
    "check": Command(
        _check,
        "Check the links between objectives, questions, methods and findings",
        frozenset({"LINKS_COMPLETE"}),
    ),
}


def main(argv: list[str] | None = None) -> int:
    return run("methodmatch", "Check that a study's parts line up.", COMMANDS, argv)


if __name__ == "__main__":
    main_wrapper(main)
