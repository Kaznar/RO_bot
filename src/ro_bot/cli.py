"""Command-line interface.

Single subcommand for v1: ``hunt``. Profiles are edited externally
(DB Browser for SQLite) so there are no CRUD subcommands.

Example::

    ro-bot hunt --profile default
    ro-bot hunt --profile default --db ./profiles.db
"""

from __future__ import annotations

import argparse
import sys

from ro_bot.app.runner import run_hunt_for_profile
from ro_bot.core.elevation import ensure_admin
from ro_bot.core.logging_setup import setup_hunt_logging, setup_root_logging

DEFAULT_DB_PATH = "profiles.db"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ro-bot", description="Ragnarok Online hunting bot.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    hunt = subparsers.add_parser(
        "hunt",
        help="Run the hunt loop for a configured profile.",
    )
    hunt.add_argument(
        "--profile", required=True,
        help="Profile name (column 'name' in the 'profile' table).",
    )
    hunt.add_argument(
        "--db", default=DEFAULT_DB_PATH,
        help=f"Path to profiles.db (default: {DEFAULT_DB_PATH}).",
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
        setup_root_logging()
        setup_hunt_logging()
        if not args.no_elevate:
            ensure_admin()
        return run_hunt_for_profile(db_path=args.db, profile_name=args.profile)

    return 2


if __name__ == "__main__":
    sys.exit(main())
