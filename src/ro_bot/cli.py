"""Command-line interface.

Single subcommand for v1: ``hunt``. Configuration is read from a JSON
file (``config.json`` by default); there are no CRUD subcommands — edit
the file in any text editor.

Example::

    ro-bot hunt
    ro-bot hunt --config ./myconfig.json
"""

from __future__ import annotations

import argparse
import sys

from ro_bot.app.runner import run_hunt
from ro_bot.core.elevation import ensure_admin
from ro_bot.core.logging_setup import setup_hunt_logging, setup_root_logging

DEFAULT_CONFIG_PATH = "config.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ro-bot", description="Ragnarok Online hunting bot.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    hunt = subparsers.add_parser(
        "hunt",
        help="Run the hunt loop using the given config file.",
    )
    hunt.add_argument(
        "--config", default=DEFAULT_CONFIG_PATH,
        help=f"Path to the JSON config file (default: {DEFAULT_CONFIG_PATH}).",
    )
    hunt.add_argument(
        "--no-elevate", action="store_true",
        help=(
            "Skip the UAC admin check "
            "(memory reads will fail without admin)."
        ),
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    if args.command == "hunt":
        if not args.no_elevate:
            ensure_admin()
        setup_root_logging()
        setup_hunt_logging()
        return run_hunt(config_path=args.config)

    return 2


if __name__ == "__main__":
    sys.exit(main())
