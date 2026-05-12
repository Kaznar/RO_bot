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

from ro_bot.app.runner import (
    run_hunt,
    run_home_prep,
    run_home_prep_dev,
    run_input_capture,
)
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
    target_group = hunt.add_mutually_exclusive_group()
    target_group.add_argument(
        "--all",
        action="store_true",
        help=(
            "Attack every visible mob (ignore mobs whitelist), track all "
            "spawns in memory, heal/buff on any map, disable return-to-farm."
        ),
    )
    target_group.add_argument(
        "--mobs",
        nargs="+",
        metavar="NAME",
        help=(
            "Target only these mob names for this run "
            "(overrides profile.mobs.allowed)."
        ),
    )

    home_prep = subparsers.add_parser(
        "home-prep",
        help="Run return_to_farm.home_prep only (stand on home_map; F9 stops).",
    )
    home_prep.add_argument(
        "--config", default=DEFAULT_CONFIG_PATH,
        help=f"Path to the JSON config file (default: {DEFAULT_CONFIG_PATH}).",
    )
    home_prep.add_argument(
        "--no-elevate", action="store_true",
        help="Skip the UAC admin check (memory reads will fail without admin).",
    )

    home_prep_dev = subparsers.add_parser(
        "home-prep-dev",
        help=(
            "[DEV] After manual h to home_map, wait then run home_prep once "
            "(ignores home_prep.enabled; F9 exits)."
        ),
    )
    home_prep_dev.add_argument(
        "--config", default=DEFAULT_CONFIG_PATH,
        help=f"Path to the JSON config file (default: {DEFAULT_CONFIG_PATH}).",
    )
    home_prep_dev.add_argument(
        "--settle", type=float, default=3.0,
        help="Seconds on home_map before first prep action (default: 3).",
    )
    home_prep_dev.add_argument(
        "--no-elevate", action="store_true",
        help="Skip the UAC admin check (memory reads will fail without admin).",
    )

    input_capture = subparsers.add_parser(
        "input-capture",
        help=(
            "Log mouse clicks + keys (pynput) to input_capture.log while the "
            "game window title matches profile.server.window_title."
        ),
    )
    input_capture.add_argument(
        "--config", default=DEFAULT_CONFIG_PATH,
        help=f"Path to the JSON config file (default: {DEFAULT_CONFIG_PATH}).",
    )
    input_capture.add_argument(
        "--log", default="input_capture.log",
        help="Output log path (default: input_capture.log in cwd).",
    )
    input_capture.add_argument(
        "--skip-in-world-wait", action="store_true",
        help="Do not wait for map + player memory before starting hooks.",
    )
    input_capture.add_argument(
        "--world-ready-timeout", type=float, default=300.0,
        help="Max seconds to wait for in-world state (default: 300).",
    )
    input_capture.add_argument(
        "--no-elevate", action="store_true",
        help="Skip the UAC admin check (memory reads will fail without admin).",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    if args.command == "hunt":
        if not args.no_elevate:
            ensure_admin()
        setup_root_logging()
        setup_hunt_logging()
        return run_hunt(
            config_path=args.config,
            hunt_all=args.all,
            selected_mobs=args.mobs,
        )

    if args.command == "home-prep":
        if not args.no_elevate:
            ensure_admin()
        setup_root_logging()
        setup_hunt_logging()
        return run_home_prep(config_path=args.config)

    if args.command == "home-prep-dev":
        if not args.no_elevate:
            ensure_admin()
        setup_root_logging()
        setup_hunt_logging()
        return run_home_prep_dev(
            config_path=args.config,
            settle_after_home_sec=args.settle,
        )

    if args.command == "input-capture":
        if not args.no_elevate:
            ensure_admin()
        return run_input_capture(
            config_path=args.config,
            log_path=args.log,
            skip_in_world_wait=args.skip_in_world_wait,
            world_ready_timeout_sec=args.world_ready_timeout,
        )

    return 2


if __name__ == "__main__":
    sys.exit(main())
